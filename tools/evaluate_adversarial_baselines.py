"""Evaluate non-learning adversarial candidate baselines offline."""

import argparse
import json
import math
import os
import statistics
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
    propose_candidate,
)
from core.adversarial_loop import (  # noqa: E402
    FixedActionStrategy,
    LatinHypercubeActionStrategy,
    RandomActionStrategy,
    RuleGuidedLhsActionStrategy,
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
    valid = [row for row in rows if row["valid"]]
    fingerprints = [row["candidate_fingerprint"] for row in valid]
    return {
        "proposal_count": len(rows),
        "valid_count": len(valid),
        "invalid_count": len(rows) - len(valid),
        "valid_rate": len(valid) / len(rows) if rows else 0.0,
        "unique_candidate_count": len(set(fingerprints)),
        "unique_rate_among_valid": (
            len(set(fingerprints)) / len(valid) if valid else 0.0
        ),
        "unchanged_candidate_count": sum(
            row["unchanged_from_baseline"] for row in valid
        ),
        "clipped_action_count": sum(row["action_clipped"] for row in rows),
        "mean_absolute_action": (
            statistics.fmean(row["mean_absolute_action"] for row in rows)
            if rows
            else 0.0
        ),
        "mean_normalized_parameter_shift": (
            statistics.fmean(
                row["normalized_parameter_shift"] for row in valid
            )
            if valid
            else 0.0
        ),
        "invalid_reasons": dict(
            sorted(Counter(row["error"] for row in rows if row["error"]).items())
        ),
    }


def evaluate_baselines(config, output_dir):
    seed = int(config["random_seed"])
    sampler = ScenarioLibrarySampler(
        entries_path=_project_path(config["scenario_library_path"]),
        manifest_path=_project_path(config["scenario_library_manifest_path"]),
        seed=seed,
    )
    options = dict(config["filters"])
    sample_rows = []
    for index in range(int(config["sample_count"])):
        record, sampling = sampler(seed if index == 0 else None, options)
        sample_rows.append({"sampling": sampling, "record": record})

    strategies = {
        "fixed": FixedActionStrategy(tuple(config["fixed_action"])),
        "random": RandomActionStrategy(seed=seed),
        "lhs": LatinHypercubeActionStrategy(
            seed=seed,
            batch_size=int(config["lhs_batch_size"]),
        ),
        "rule_guided_lhs": RuleGuidedLhsActionStrategy(
            seed=seed,
            batch_size=int(config["lhs_batch_size"]),
            minimum_magnitude=float(config["rule_lhs_minimum_magnitude"]),
        ),
    }
    agent_config = load_agent_config(_project_path(config["agent_config_path"]))
    proposal_rows = []
    rows_by_strategy = {name: [] for name in strategies}
    for name, strategy in strategies.items():
        for index, sample in enumerate(sample_rows):
            record = sample["record"]
            action = strategy.select_action(index, {})
            proposal = propose_candidate(
                record,
                action,
                step_index=0,
                config=agent_config,
            )
            baseline_fingerprint = canonical_parameter_fingerprint(record)
            candidate = proposal.get("candidate")
            candidate_fingerprint = proposal.get("fingerprint")
            shift = None
            if candidate is not None:
                baseline_values = normalize_vector(parameter_vector(record), clip=True)
                candidate_values = normalize_vector(parameter_vector(candidate), clip=True)
                shift = math.sqrt(
                    float(np.mean(np.square(candidate_values - baseline_values)))
                )
            row = {
                "strategy": name,
                "sample_index": index,
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
                "action": proposal.get("action"),
                "mean_absolute_action": float(np.mean(np.abs(action))),
                "action_clipped": bool(proposal.get("clipped", False)),
                "valid": bool(proposal["valid"]),
                "error": proposal.get("error"),
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
            proposal_rows.append(row)
            rows_by_strategy[name].append(row)

    summary = {
        "format": "adversarial_offline_baseline_report_v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_kind": "offline_candidate_generation",
        "random_seed": seed,
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
            f"[BASELINE] {name}: valid={metrics['valid_count']}/"
            f"{metrics['proposal_count']} unique={metrics['unique_candidate_count']}"
        )
    print(f"[RESULT_DIR] {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
