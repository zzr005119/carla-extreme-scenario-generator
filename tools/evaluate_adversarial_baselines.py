"""Evaluate non-learning adversarial candidate baselines offline."""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    canonical_parameter_fingerprint,
    load_agent_config,
)
from core.adversarial_loop import (  # noqa: E402
    FixedActionStrategy,
    LatinHypercubeActionStrategy,
    RandomActionStrategy,
    RuleGuidedLhsActionStrategy,
    propose_with_retries,
)
from core.adversarial_sampling import ScenarioLibrarySampler  # noqa: E402
from core.scenario_features import normalize_vector, parameter_vector  # noqa: E402
from core.scenario_validator import load_json, validate_schema_value  # noqa: E402


DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_baselines_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_baselines_v1.schema.json",
)


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def load_baseline_config(path=DEFAULT_CONFIG_PATH, schema_path=DEFAULT_SCHEMA_PATH):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    return config


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_jsonl(path, values):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for value in values:
            file.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _default_output_root(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(root, config["output_subdirectory"], timestamp)


def git_state():
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    return {"commit": commit, "worktree_dirty": bool(status)}


def _count_values(samples, path):
    values = Counter()
    for sample in samples:
        value = sample
        for part in path:
            value = value[part]
        if isinstance(value, list):
            values.update(value)
        else:
            values[value] += 1
    return dict(sorted(values.items(), key=lambda item: str(item[0])))


def _sample_coverage(sample_rows):
    info_rows = [row["sampling"] for row in sample_rows]
    strata = {
        (row["generator"], row["target_risk_level"])
        for row in info_rows
    }
    return {
        "sample_count": len(sample_rows),
        "unique_library_entry_count": len(
            {row["library_id"] for row in info_rows}
        ),
        "generator_target_stratum_count": len(strata),
        "generator_counts": _count_values(sample_rows, ("sampling", "generator")),
        "target_risk_level_counts": _count_values(
            sample_rows,
            ("sampling", "target_risk_level"),
        ),
        "weather_tag_counts": _count_values(
            sample_rows,
            ("sampling", "weather_tags"),
        ),
        "hazard_tag_counts": _count_values(
            sample_rows,
            ("sampling", "hazard_tags"),
        ),
        "traffic_manager_seed_counts": _count_values(
            sample_rows,
            ("sampling", "traffic_manager_seed"),
        ),
    }


def _strategy_summary(rows):
    selected = [row for row in rows if row["valid"]]
    fingerprints = [row["candidate_fingerprint"] for row in selected]
    invalid_attempt_reasons = Counter()
    for row in rows:
        invalid_attempt_reasons.update(
            attempt["error"]
            for attempt in row["attempts"]
            if not attempt["valid"] and attempt["error"]
        )
    return {
        "proposal_count": len(rows),
        "raw_first_attempt_valid_count": sum(
            row["first_attempt_valid"] for row in rows
        ),
        "raw_first_attempt_valid_rate": (
            sum(row["first_attempt_valid"] for row in rows) / len(rows)
            if rows
            else 0.0
        ),
        "selected_valid_count": len(selected),
        "selected_valid_rate": len(selected) / len(rows) if rows else 0.0,
        "retry_exhausted_count": sum(row["retry_exhausted"] for row in rows),
        "retried_sample_count": sum(row["attempt_count"] > 1 for row in rows),
        "total_attempt_count": sum(row["attempt_count"] for row in rows),
        "invalid_attempt_count": sum(
            row["invalid_attempt_count"] for row in rows
        ),
        "mean_attempt_count": (
            statistics.fmean(row["attempt_count"] for row in rows)
            if rows
            else 0.0
        ),
        "unique_candidate_count": len(set(fingerprints)),
        "unique_rate_among_valid": (
            len(set(fingerprints)) / len(selected) if selected else 0.0
        ),
        "unchanged_candidate_count": sum(
            row["unchanged_from_baseline"] for row in selected
        ),
        "clipped_attempt_count": sum(
            attempt["clipped"]
            for row in rows
            for attempt in row["attempts"]
        ),
        "mean_absolute_action": (
            statistics.fmean(
                row["mean_absolute_action"] for row in selected
            )
            if selected
            else 0.0
        ),
        "mean_normalized_parameter_shift": (
            statistics.fmean(
                row["normalized_parameter_shift"] for row in selected
            )
            if selected
            else 0.0
        ),
        "invalid_attempt_reasons": dict(
            sorted(invalid_attempt_reasons.items())
        ),
    }


def sample_scenarios(config, sample_count=None):
    seed = int(config["random_seed"])
    sampler = ScenarioLibrarySampler(
        entries_path=_project_path(config["scenario_library_path"]),
        manifest_path=_project_path(config["scenario_library_manifest_path"]),
        seed=seed,
    )
    options = dict(config["filters"])
    sample_rows = []
    count = int(sample_count if sample_count is not None else config["sample_count"])
    for index in range(count):
        record, sampling = sampler(seed if index == 0 else None, options)
        sample_rows.append({"sampling": sampling, "record": record})
    return sample_rows


def build_baseline_strategies(config, lhs_batch_size=None, seed=None):
    seed = int(config["random_seed"] if seed is None else seed)
    batch_size = int(lhs_batch_size or config["lhs_batch_size"])
    return {
        "fixed": FixedActionStrategy(tuple(config["fixed_action"])),
        "random": RandomActionStrategy(seed=seed),
        "lhs": LatinHypercubeActionStrategy(
            seed=seed,
            batch_size=batch_size,
        ),
        "rule_guided_lhs": RuleGuidedLhsActionStrategy(
            seed=seed,
            batch_size=batch_size,
            minimum_magnitude=float(config["rule_lhs_minimum_magnitude"]),
        ),
    }


def evaluate_strategy_candidate(
    name,
    strategy,
    retry_strategy,
    sample,
    sample_index,
    agent_config,
    max_attempts,
):
    record = sample["record"]
    initial_action = strategy.select_action(sample_index, {})
    retry = propose_with_retries(
        record,
        retry_strategy,
        observation={},
        max_attempts=max_attempts,
        step_index=0,
        config=agent_config,
        initial_action=initial_action,
    )
    proposal = retry["proposal"]
    selected_action = (
        proposal.get("action")
        if proposal is not None
        else retry["attempts"][-1]["action"]
    )
    baseline_fingerprint = canonical_parameter_fingerprint(record)
    candidate = proposal.get("candidate") if proposal is not None else None
    candidate_fingerprint = (
        proposal.get("fingerprint") if proposal is not None else None
    )
    shift = None
    if candidate is not None:
        baseline_values = normalize_vector(parameter_vector(record), clip=True)
        candidate_values = normalize_vector(parameter_vector(candidate), clip=True)
        shift = math.sqrt(
            float(np.mean(np.square(candidate_values - baseline_values)))
        )
    return {
        "strategy": name,
        "sample_index": sample_index,
        "library_id": sample["sampling"]["library_id"],
        "baseline_sample_id": record["sample_id"],
        "generator": sample["sampling"]["generator"],
        "target_risk_level": sample["sampling"]["target_risk_level"],
        "weather_tags": sample["sampling"]["weather_tags"],
        "hazard_tags": sample["sampling"]["hazard_tags"],
        "traffic_manager_seed": sample["sampling"]["traffic_manager_seed"],
        "historical_baseline_risk": sample["sampling"][
            "historical_observed_risk"
        ],
        "action": selected_action,
        "mean_absolute_action": float(np.mean(np.abs(selected_action))),
        "action_clipped": bool(
            proposal.get("clipped", False) if proposal is not None else False
        ),
        "valid": bool(retry["valid"]),
        "error": (
            None if retry["valid"] else retry["attempts"][-1]["error"]
        ),
        "attempts": retry["attempts"],
        "attempt_count": retry["attempt_count"],
        "invalid_attempt_count": retry["invalid_attempt_count"],
        "first_attempt_valid": retry["first_attempt_valid"],
        "retry_exhausted": retry["retry_exhausted"],
        "baseline_fingerprint": baseline_fingerprint,
        "candidate_fingerprint": candidate_fingerprint,
        "unchanged_from_baseline": (
            candidate_fingerprint == baseline_fingerprint
            if candidate_fingerprint is not None
            else False
        ),
        "normalized_parameter_shift": shift,
        "candidate": candidate,
        "candidate_runtime_status": "not_executed",
    }


def evaluate_baselines(config, output_dir):
    seed = int(config["random_seed"])
    sample_rows = sample_scenarios(config)
    strategies = build_baseline_strategies(config)
    retry_strategies = build_baseline_strategies(
        config,
        seed=seed + int(config["retry_seed_offset"]),
    )
    agent_config = load_agent_config(_project_path(config["agent_config_path"]))
    proposal_rows = []
    rows_by_strategy = {name: [] for name in strategies}
    for name, strategy in strategies.items():
        for index, sample in enumerate(sample_rows):
            row = evaluate_strategy_candidate(
                name,
                strategy,
                retry_strategies[name],
                sample,
                index,
                agent_config,
                int(config["max_candidate_attempts"][name]),
            )
            proposal_rows.append(row)
            rows_by_strategy[name].append(row)

    summary = {
        "format": "adversarial_offline_baseline_report_v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_kind": "offline_candidate_generation",
        "random_seed": seed,
        "source_git": git_state(),
        "risk_effectiveness_evaluated": False,
        "runtime_boundary": (
            "Candidates were not executed in CARLA. Historical baseline risk is "
            "sampling context only and is not a candidate reward or risk result."
        ),
        "sampling": _sample_coverage(sample_rows),
        "strategies": {
            name: _strategy_summary(rows)
            for name, rows in rows_by_strategy.items()
        },
        "artifacts": {
            "samples": "sample_manifest.jsonl",
            "proposals": "baseline_proposals.jsonl",
        },
    }
    os.makedirs(output_dir, exist_ok=False)
    _write_jsonl(os.path.join(output_dir, "sample_manifest.jsonl"), sample_rows)
    _write_jsonl(os.path.join(output_dir, "baseline_proposals.jsonl"), proposal_rows)
    _write_json(os.path.join(output_dir, "baseline_summary.json"), summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate stratified fixed/random/LHS/rule-guided LHS candidates offline"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_baseline_config(args.config)
    output_dir = os.path.abspath(args.output_dir or _default_output_root(config))
    summary = evaluate_baselines(config, output_dir)
    print(f"[BASELINE] samples={summary['sampling']['sample_count']}")
    for name, metrics in summary["strategies"].items():
        print(
            f"[BASELINE] {name}: raw_valid="
            f"{metrics['raw_first_attempt_valid_count']}/{metrics['proposal_count']} "
            f"selected={metrics['selected_valid_count']}/"
            f"{metrics['proposal_count']} attempts={metrics['total_attempt_count']}"
        )
    print(f"[RESULT_DIR] {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
