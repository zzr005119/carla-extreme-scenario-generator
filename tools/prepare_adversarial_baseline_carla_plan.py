"""Prepare a shared-baseline CARLA comparison plan for static strategies."""

import argparse
import copy
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.scenario_validator import (  # noqa: E402
    load_json,
    require_valid_scenario,
    validate_schema_value,
)
from tools.evaluate_adversarial_baselines import (  # noqa: E402
    build_baseline_strategies,
    evaluate_strategy_candidate,
    git_state,
    load_baseline_config,
    sample_scenarios,
)
from tools.run_adversarial_episode import (  # noqa: E402
    build_carla_config,
    load_loop_config,
    validate_carla_config,
)


DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_baseline_carla_plan_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_baseline_carla_plan_v1.schema.json",
)
STRATEGY_SUFFIXES = {
    "fixed": "fixed",
    "random": "random",
    "lhs": "lhs",
    "rule_guided_lhs": "rulelhs",
}


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def load_plan_config(path=DEFAULT_CONFIG_PATH, schema_path=DEFAULT_SCHEMA_PATH):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    expected = set(STRATEGY_SUFFIXES)
    if set(config["strategy_order"]) != expected:
        raise ValueError("strategy_order must contain all four baseline strategies")
    return config


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_csv(path, rows):
    fields = [
        "run_order",
        "pair_id",
        "phase",
        "strategy",
        "run_id",
        "sample_id",
        "library_id",
        "generator",
        "target_risk_level",
        "traffic_manager_seed",
        "first_attempt_valid",
        "attempt_count",
        "invalid_attempt_count",
        "record_path",
        "config_path",
        "expected_run_root",
        "validation_status",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows)


def _default_plan_root(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(root, config["output_subdirectory"], timestamp)


def _default_runtime_root(config, plan_root):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else plan_root
    return os.path.join(
        root,
        config["runtime_output_subdirectory"],
        os.path.basename(plan_root),
    )


def _portable(plan_root, path):
    return os.path.relpath(path, plan_root).replace("\\", "/")


def _candidate_sample_id(record, pair_index, strategy):
    suffix = f"_bcmp_{pair_index:02d}_{STRATEGY_SUFFIXES[strategy]}"
    base = str(record["sample_id"]).split("_adv_", 1)[0]
    return f"{base[:64 - len(suffix)]}{suffix}"


def _write_run_artifacts(
    plan_root,
    runtime_output_root,
    record,
    run_id,
    base_config,
    route_profile,
    traffic_manager_port,
    validate_runner,
):
    record_path = os.path.join(plan_root, "records", f"{run_id}.json")
    config_path = os.path.join(plan_root, "configs", f"{run_id}.json")
    _write_json(record_path, record)
    config = build_carla_config(
        record,
        base_config,
        route_profile,
        run_id,
        runtime_output_root,
        traffic_manager_port,
    )
    _write_json(config_path, config)
    validation_status = "not_requested"
    if validate_runner:
        output = validate_carla_config(config_path)
        log_path = os.path.join(plan_root, "validation_logs", f"{run_id}.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as file:
            file.write(output)
        validation_status = "completed"
    return {
        "record_path": _portable(plan_root, record_path),
        "config_path": _portable(plan_root, config_path),
        "expected_run_root": os.path.join(runtime_output_root, run_id),
        "validation_status": validation_status,
    }


def prepare_plan(
    plan_config,
    plan_root,
    runtime_output_root,
    traffic_manager_port=None,
    validate_runner=None,
):
    baseline_config = load_baseline_config(
        _project_path(plan_config["baseline_config_path"])
    )
    loop_config = load_loop_config(_project_path(plan_config["loop_config_path"]))
    sample_count = int(plan_config["sample_count"])
    sample_rows = sample_scenarios(baseline_config, sample_count=sample_count)
    strategies = build_baseline_strategies(
        baseline_config,
        lhs_batch_size=sample_count,
    )
    retry_strategies = build_baseline_strategies(
        baseline_config,
        lhs_batch_size=sample_count,
        seed=(
            int(baseline_config["random_seed"])
            + int(baseline_config["retry_seed_offset"])
        ),
    )
    agent_config = load_agent_config(
        _project_path(baseline_config["agent_config_path"])
    )
    base_config = load_json(_project_path(loop_config["base_carla_config_path"]))
    route_profile = load_json(_project_path(loop_config["route_profile_path"]))
    traffic_manager_port = int(
        traffic_manager_port or loop_config["runtime"]["traffic_manager_port"]
    )
    if validate_runner is None:
        validate_runner = bool(plan_config["validate_scene_configs"])
    os.makedirs(plan_root, exist_ok=False)

    runs = []
    candidate_rows = []
    for pair_index, sample in enumerate(sample_rows, 1):
        record = copy.deepcopy(sample["record"])
        sampling = sample["sampling"]
        pair_id = f"abcv1_pair_{pair_index:02d}"
        baseline_run_id = f"{pair_id}_baseline"
        baseline_artifacts = _write_run_artifacts(
            plan_root,
            runtime_output_root,
            record,
            baseline_run_id,
            base_config,
            route_profile,
            traffic_manager_port,
            validate_runner,
        )
        runs.append(
            {
                "run_order": len(runs) + 1,
                "pair_id": pair_id,
                "phase": "baseline",
                "strategy": None,
                "run_id": baseline_run_id,
                "sample_id": record["sample_id"],
                "library_id": sampling["library_id"],
                "generator": sampling["generator"],
                "target_risk_level": sampling["target_risk_level"],
                "traffic_manager_seed": sampling["traffic_manager_seed"],
                "first_attempt_valid": None,
                "attempt_count": 0,
                "invalid_attempt_count": 0,
                **baseline_artifacts,
            }
        )

        for strategy_name in plan_config["strategy_order"]:
            row = evaluate_strategy_candidate(
                strategy_name,
                strategies[strategy_name],
                retry_strategies[strategy_name],
                sample,
                pair_index - 1,
                agent_config,
                int(baseline_config["max_candidate_attempts"][strategy_name]),
            )
            candidate_rows.append(row)
            if not row["valid"]:
                raise ValueError(
                    f"{pair_id}/{strategy_name}: retry budget exhausted"
                )
            candidate = copy.deepcopy(row["candidate"])
            candidate["sample_id"] = _candidate_sample_id(
                record,
                pair_index,
                strategy_name,
            )
            require_valid_scenario(candidate)
            run_id = f"{pair_id}_{STRATEGY_SUFFIXES[strategy_name]}"
            artifacts = _write_run_artifacts(
                plan_root,
                runtime_output_root,
                candidate,
                run_id,
                base_config,
                route_profile,
                traffic_manager_port,
                validate_runner,
            )
            runs.append(
                {
                    "run_order": len(runs) + 1,
                    "pair_id": pair_id,
                    "phase": "candidate",
                    "strategy": strategy_name,
                    "run_id": run_id,
                    "sample_id": candidate["sample_id"],
                    "library_id": sampling["library_id"],
                    "generator": sampling["generator"],
                    "target_risk_level": sampling["target_risk_level"],
                    "traffic_manager_seed": sampling["traffic_manager_seed"],
                    "first_attempt_valid": row["first_attempt_valid"],
                    "attempt_count": row["attempt_count"],
                    "invalid_attempt_count": row["invalid_attempt_count"],
                    "selected_action": row["action"],
                    "attempts": row["attempts"],
                    "candidate_fingerprint": row["candidate_fingerprint"],
                    **artifacts,
                }
            )

    strata = {
        (row["sampling"]["generator"], row["sampling"]["target_risk_level"])
        for row in sample_rows
    }
    strategy_counts = Counter(row["strategy"] for row in candidate_rows)
    raw_valid_counts = Counter(
        row["strategy"] for row in candidate_rows if row["first_attempt_valid"]
    )
    attempt_counts = Counter()
    for row in candidate_rows:
        attempt_counts[row["strategy"]] += row["attempt_count"]
    summary = {
        "format": "adversarial_baseline_carla_plan_summary_v1",
        "evidence_kind": "static_validation",
        "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_git": git_state(),
        "sample_count": sample_count,
        "generator_target_stratum_count": len(strata),
        "baseline_run_count": sum(row["phase"] == "baseline" for row in runs),
        "candidate_run_count": sum(row["phase"] == "candidate" for row in runs),
        "total_run_count": len(runs),
        "strategy_candidate_counts": dict(sorted(strategy_counts.items())),
        "strategy_raw_first_attempt_valid_counts": {
            name: raw_valid_counts[name] for name in plan_config["strategy_order"]
        },
        "strategy_total_attempt_counts": {
            name: attempt_counts[name] for name in plan_config["strategy_order"]
        },
        "retry_exhausted_count": sum(
            row["retry_exhausted"] for row in candidate_rows
        ),
        "scene_config_validation_count": sum(
            row["validation_status"] == "completed" for row in runs
        ),
        "carla_runtime_executed": False,
        "runtime_boundary": (
            "All scenario and CARLA configs were prepared for comparison, but no "
            "CARLA scene was executed by this planning command."
        ),
        "runtime_output_root": os.path.abspath(runtime_output_root),
        "traffic_manager_port": traffic_manager_port,
        "artifacts": {
            "run_plan_json": "run_plan.json",
            "run_plan_csv": "run_plan.csv",
            "sample_manifest": "sample_manifest.jsonl",
        },
    }
    with open(
        os.path.join(plan_root, "sample_manifest.jsonl"),
        "w",
        encoding="utf-8",
    ) as file:
        for row in sample_rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _write_json(
        os.path.join(plan_root, "run_plan.json"),
        {
            "format": "adversarial_baseline_carla_run_plan_v1",
            "summary": summary,
            "acceptance_requirements": loop_config["acceptance_requirements"],
            "runs": runs,
        },
    )
    _write_csv(os.path.join(plan_root, "run_plan.csv"), runs)
    _write_json(os.path.join(plan_root, "summary.json"), summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepare shared-baseline CARLA configs for four static strategies"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--skip-runner-validation", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_plan_config(args.config)
    plan_root = os.path.abspath(args.output_dir or _default_plan_root(config))
    runtime_output_root = os.path.abspath(
        args.runtime_output_root or _default_runtime_root(config, plan_root)
    )
    summary = prepare_plan(
        config,
        plan_root,
        runtime_output_root,
        traffic_manager_port=args.traffic_manager_port,
        validate_runner=(
            False if args.skip_runner_validation else None
        ),
    )
    print(
        f"[PLAN] baseline={summary['baseline_run_count']} "
        f"candidates={summary['candidate_run_count']} "
        f"total={summary['total_run_count']}"
    )
    print(
        f"[PLAN] static_validated={summary['scene_config_validation_count']} "
        f"retry_exhausted={summary['retry_exhausted_count']}"
    )
    print(f"[RESULT_DIR] {plan_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
