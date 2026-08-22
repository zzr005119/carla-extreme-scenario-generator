"""Prepare CARLA configs for the three frozen LHS/high boundary candidates."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import load_json, require_valid_scenario, validate_schema_value
from tools.evaluate_adversarial_baselines import git_state
from tools.prepare_adversarial_baseline_carla_plan import (
    _portable,
    _write_run_artifacts,
)
from tools.run_adversarial_episode import load_loop_config

DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "lhs_high_independent_carla_plan_v1.json")
DEFAULT_SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schemas", "lhs_high_independent_carla_plan_v1.schema.json")


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _default_root(config, runtime=False):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    subdirectory = config["runtime_output_subdirectory"] if runtime else config["output_subdirectory"]
    return os.path.join(root, subdirectory, datetime.now().strftime("%Y%m%d_%H%M%S"))


def _load_records(path, expected_ids):
    records = []
    seen = set()
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            require_valid_scenario(record)
            sample_id = record["sample_id"]
            if sample_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate sample_id {sample_id}")
            seen.add(sample_id)
            records.append(record)
    if seen != set(expected_ids):
        raise ValueError(f"candidate ids mismatch: expected={expected_ids}, actual={sorted(seen)}")
    return [next(record for record in records if record["sample_id"] == sample_id) for sample_id in expected_ids]


def _load_metadata(path, expected_ids):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    by_id = {row.get("sample_id"): row for row in rows}
    if set(by_id) != set(expected_ids):
        raise ValueError(f"metadata ids mismatch: expected={expected_ids}, actual={sorted(by_id)}")
    return {sample_id: by_id[sample_id] for sample_id in expected_ids}


def load_plan_config(path=DEFAULT_CONFIG_PATH, schema_path=DEFAULT_SCHEMA_PATH):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    return config


def prepare_plan(plan_config, plan_root, runtime_output_root, traffic_manager_port=None, validate_runner=None):
    records_path = _project_path(plan_config["records_path"])
    metadata_path = _project_path(plan_config["metadata_path"])
    records = _load_records(records_path, plan_config["expected_sample_ids"])
    metadata = _load_metadata(metadata_path, plan_config["expected_sample_ids"])
    loop_config = load_loop_config(_project_path(plan_config["loop_config_path"]))
    base_config = load_json(_project_path(loop_config["base_carla_config_path"]))
    route_profile = load_json(_project_path(loop_config["route_profile_path"]))
    traffic_manager_port = int(traffic_manager_port or loop_config["runtime"]["traffic_manager_port"])
    if validate_runner is None:
        validate_runner = bool(plan_config["validate_scene_configs"])
    os.makedirs(plan_root, exist_ok=False)
    runs = []
    manifest = []
    for index, record in enumerate(records, 1):
        sample_id = record["sample_id"]
        pair_id = f"lhs_high_boundary_v1_{index:02d}"
        run_id = f"{pair_id}_independent"
        artifacts = _write_run_artifacts(
            plan_root, runtime_output_root, record, run_id, base_config,
            route_profile, traffic_manager_port, validate_runner,
        )
        row = {
            "run_order": index,
            "pair_id": pair_id,
            "phase": "independent",
            "strategy": "lhs_high_independent",
            "run_id": run_id,
            "sample_id": sample_id,
            "library_id": None,
            "generator": record["provenance"]["generator"],
            "target_risk_level": record["conditions"]["target_risk_level"],
            "traffic_manager_seed": record["scenario"]["traffic_manager_seed"],
            "selection_metadata": metadata[sample_id],
            "risk_delta": None,
            **artifacts,
        }
        runs.append(row)
        manifest.append({"record": record, "selection_metadata": metadata[sample_id], "run": row})
    summary = {
        "format": "lhs_high_independent_carla_plan_summary_v1",
        "evidence_kind": "static_validation",
        "execution_mode": "independent",
        "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_git": git_state(),
        "candidate_count": len(records),
        "independent_run_count": len(runs),
        "scene_config_validation_count": sum(row["validation_status"] == "completed" for row in runs),
        "traffic_manager_port": traffic_manager_port,
        "carla_runtime_executed": False,
        "runtime_boundary": "Three frozen LHS/high boundary candidates are planned as independent scenes; no shared baseline, repeated pair, or online training is included.",
        "source_records": os.path.relpath(records_path, PROJECT_ROOT).replace("\\", "/"),
        "source_metadata": os.path.relpath(metadata_path, PROJECT_ROOT).replace("\\", "/"),
        "runtime_output_root": os.path.abspath(runtime_output_root),
        "artifacts": {"run_plan_json": "run_plan.json", "run_plan_csv": "run_plan.csv", "candidate_manifest": "candidate_manifest.jsonl"},
    }
    with open(os.path.join(plan_root, "candidate_manifest.jsonl"), "w", encoding="utf-8") as file:
        for item in manifest:
            file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    fields = ("run_order", "pair_id", "phase", "strategy", "run_id", "sample_id", "library_id", "generator", "target_risk_level", "traffic_manager_seed", "record_path", "config_path", "expected_run_root", "validation_status")
    with open(os.path.join(plan_root, "run_plan.csv"), "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in runs)
    _write_json(os.path.join(plan_root, "summary.json"), summary)
    _write_json(os.path.join(plan_root, "run_plan.json"), {"format": "lhs_high_independent_carla_run_plan_v1", "summary": summary, "acceptance_requirements": loop_config["acceptance_requirements"], "runs": runs})
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare independent LHS/high boundary CARLA configs")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--skip-runner-validation", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_plan_config(args.config)
    plan_root = os.path.abspath(args.output_dir or _default_root(config))
    runtime_root = os.path.abspath(args.runtime_output_root or _default_root(config, runtime=True))
    summary = prepare_plan(config, plan_root, runtime_root, args.traffic_manager_port, not args.skip_runner_validation)
    print(f"[SUMMARY] independent_runs={summary['independent_run_count']} validated={summary['scene_config_validation_count']}")
    print(f"[RESULT_DIR] {plan_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
