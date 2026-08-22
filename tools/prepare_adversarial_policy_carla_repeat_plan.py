"""Prepare repeated-seed CARLA runs for selected frozen policy pairs."""

import argparse
import copy
import csv
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import load_json, validate_schema_value
from tools.evaluate_adversarial_baselines import git_state
from tools.prepare_adversarial_baseline_carla_plan import (
    _portable,
    _write_json,
    _write_run_artifacts,
)
from tools.run_adversarial_episode import load_loop_config

DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT, "configs", "adversarial_policy_carla_repeat_plan_v1.json"
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT, "schemas", "adversarial_policy_carla_repeat_plan_v1.schema.json"
)
STRATEGY_SUFFIXES = {"sac_policy": "sac", "rule_guided_lhs": "rulelhs"}


def _rooted_path(spec):
    root = os.environ.get(spec["root_env"])
    if not root:
        raise ValueError(f"缺少路径根目录环境变量: {spec['root_env']}")
    return os.path.abspath(os.path.join(root, spec["relative_path"]))


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def load_repeat_plan_config(path=DEFAULT_CONFIG_PATH, schema_path=DEFAULT_SCHEMA_PATH):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    if len(set(config["traffic_manager_seeds"])) != len(config["traffic_manager_seeds"]):
        raise ValueError("traffic_manager_seeds 必须唯一")
    return config


def load_source_plan(path):
    source_path = os.path.abspath(path)
    plan = load_json(source_path)
    if plan.get("format") != "adversarial_policy_carla_run_plan_v1":
        raise ValueError("source plan 必须为 adversarial_policy_carla_run_plan_v1")
    if not plan.get("runs"):
        raise ValueError("source plan 不得为空")
    return source_path, plan


def _group_source_runs(plan, selected_pair_ids):
    grouped = OrderedDict()
    for pair_id in selected_pair_ids:
        rows = [row for row in plan["runs"] if row["pair_id"] == pair_id]
        if len(rows) != 3:
            raise ValueError(f"{pair_id} 必须包含 1 个基线和 2 个候选")
        phases = [row["phase"] for row in rows]
        strategies = [row.get("strategy") for row in rows if row["phase"] == "candidate"]
        if phases.count("baseline") != 1 or strategies != ["sac_policy", "rule_guided_lhs"]:
            raise ValueError(f"{pair_id} 的运行顺序或策略不符合冻结契约")
        grouped[pair_id] = sorted(
            rows,
            key=lambda row: int(row.get("run_order", 0)),
        )
    return grouped


def _load_record(source_dir, run):
    path = os.path.join(source_dir, run["record_path"])
    record = load_json(path)
    if not isinstance(record, dict) or "scenario" not in record:
        raise ValueError(f"记录缺少 scenario: {path}")
    return record


def _write_csv(path, rows):
    fields = [
        "run_order", "pair_id", "source_pair_id", "repeat_seed", "phase",
        "strategy", "run_id", "sample_id", "library_id", "generator",
        "target_risk_level", "traffic_manager_seed", "record_path",
        "config_path", "expected_run_root", "validation_status",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows)


def _default_plan_root(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT") or (r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp")
    return os.path.join(root, config["output_subdirectory"], datetime.now().strftime("%Y%m%d_%H%M%S"))


def _default_runtime_root(config, plan_root):
    root = os.environ.get("PROJECT_OUTPUT_ROOT") or (r"F:\Carla\output-0.9.16" if os.name == "nt" else plan_root)
    return os.path.join(root, config["runtime_output_subdirectory"], os.path.basename(plan_root))


def prepare_repeat_plan(
    config,
    plan_root,
    runtime_output_root,
    traffic_manager_port=None,
    source_plan_override=None,
):
    source_path, source_plan = load_source_plan(
        os.path.abspath(source_plan_override)
        if source_plan_override
        else _rooted_path(config["source_plan"])
    )
    source_dir = os.path.dirname(source_path)
    grouped = _group_source_runs(source_plan, config["selected_pair_ids"])
    loop_config = load_loop_config(_project_path("configs/adversarial_loop_v1.json"))
    base_config = load_json(_project_path(loop_config["base_carla_config_path"]))
    route_profile = load_json(_project_path(loop_config["route_profile_path"]))
    traffic_manager_port = int(traffic_manager_port or loop_config["runtime"]["traffic_manager_port"])
    os.makedirs(plan_root, exist_ok=False)
    runs = []
    manifest = []
    run_order = 0
    for source_pair_id, source_rows in grouped.items():
        source_baseline = next(row for row in source_rows if row["phase"] == "baseline")
        for seed in config["traffic_manager_seeds"]:
            repeat_pair_id = f"apcv2_repeat_{source_pair_id.replace('apcv1_', '')}_s{seed}"
            for source_row in source_rows:
                run_order += 1
                strategy = source_row.get("strategy")
                suffix = "baseline" if strategy is None else STRATEGY_SUFFIXES[strategy]
                run_id = f"{repeat_pair_id}_{suffix}"
                record = copy.deepcopy(_load_record(source_dir, source_row))
                record["scenario"]["traffic_manager_seed"] = int(seed)
                record["sample_id"] = f"{source_row['sample_id']}_s{seed}"
                if isinstance(record.get("sampling"), dict):
                    record["sampling"]["traffic_manager_seed"] = int(seed)
                artifacts = _write_run_artifacts(
                    plan_root, runtime_output_root, record, run_id, base_config,
                    route_profile, traffic_manager_port, bool(config["validate_scene_configs"]),
                )
                run = {
                    "run_order": run_order,
                    "pair_id": repeat_pair_id,
                    "source_pair_id": source_pair_id,
                    "repeat_seed": int(seed),
                    "phase": source_row["phase"],
                    "strategy": strategy,
                    "run_id": run_id,
                    "sample_id": record["sample_id"],
                    "library_id": source_row["library_id"],
                    "generator": source_row["generator"],
                    "target_risk_level": source_row["target_risk_level"],
                    "traffic_manager_seed": int(seed),
                    **artifacts,
                }
                runs.append(run)
                manifest.append({"source_run_id": source_row["run_id"], **run})
    summary = {
        "format": "adversarial_policy_carla_repeat_plan_summary_v1",
        "evidence_kind": "static_validation",
        "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_plan": source_path,
        "source_git": git_state(),
        "selected_source_pair_count": len(grouped),
        "repeat_seed_count": len(config["traffic_manager_seeds"]),
        "baseline_run_count": sum(row["phase"] == "baseline" for row in runs),
        "candidate_run_count": sum(row["phase"] == "candidate" for row in runs),
        "total_run_count": len(runs),
        "scene_config_validation_count": sum(row["validation_status"] == "completed" for row in runs),
        "selected_pair_ids": list(grouped),
        "traffic_manager_seeds": [int(seed) for seed in config["traffic_manager_seeds"]],
        "strategy_order": ["sac_policy", "rule_guided_lhs"],
        "carla_runtime_executed": False,
        "runtime_boundary": "Repeated configs passed static validation only; no CARLA scene was executed by this planning command.",
        "runtime_output_root": os.path.abspath(runtime_output_root),
        "traffic_manager_port": traffic_manager_port,
    }
    _write_json(os.path.join(plan_root, "summary.json"), summary)
    _write_json(os.path.join(plan_root, "run_plan.json"), {"format": "adversarial_policy_carla_repeat_run_plan_v1", "summary": summary, "acceptance_requirements": source_plan.get("acceptance_requirements", {}), "runs": runs})
    _write_json(os.path.join(plan_root, "source_manifest.json"), {"source_plan": source_path, "runs": manifest})
    _write_csv(os.path.join(plan_root, "run_plan.csv"), runs)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="准备冻结策略的 CARLA 重复 Traffic Manager 种子计划")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--source-plan", help="本地回收证据的源 run_plan.json 覆盖路径")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_repeat_plan_config(args.config)
    plan_root = os.path.abspath(args.output_dir or _default_plan_root(config))
    runtime_root = os.path.abspath(args.runtime_output_root or _default_runtime_root(config, plan_root))
    summary = prepare_repeat_plan(
        config,
        plan_root,
        runtime_root,
        args.traffic_manager_port,
        args.source_plan,
    )
    print(f"[PLAN] pairs={summary['selected_source_pair_count']} seeds={summary['repeat_seed_count']} total={summary['total_run_count']}")
    print(f"[PLAN] static_validated={summary['scene_config_validation_count']}")
    print(f"[RESULT_DIR] {plan_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
