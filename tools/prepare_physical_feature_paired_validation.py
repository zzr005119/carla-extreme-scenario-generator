"""准备原始与物理增强候选的 CARLA 配对验证计划。"""

import argparse
import copy
import csv
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scenario_features import load_jsonl
from core.scenario_validator import compile_carla_config, load_json, require_valid_scenario
from tools.prepare_carla_route_regression import apply_regression_profile, load_control_profile
from tools.prepare_dual_channel_validation import (
    TRAFFIC_SEEDS,
    build_schedule,
    current_git_commit,
    file_sha256,
    validate_configs,
    write_csv,
    write_executable,
    write_json,
    write_jsonl,
    write_scripts,
)


ARMS = ("raw_15d", "physical_enhanced")
SENSOR_PROFILES = ("rgb_collision", "full_multisensor")
DEFAULT_BASE_CONFIG = PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"
DEFAULT_CONTROL_PROFILE = (
    PROJECT_ROOT / "configs" / "route_control_profiles" / "waypoint_follower_v1.json"
)


def parse_args():
    parser = argparse.ArgumentParser(description="准备物理增强候选配对验证")
    parser.add_argument("--pair-selection", required=True)
    parser.add_argument("--baseline-records", required=True)
    parser.add_argument("--baseline-selection", required=True)
    parser.add_argument("--enhanced-records", required=True)
    parser.add_argument("--enhanced-selection", required=True)
    parser.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG))
    parser.add_argument("--control-profile", default=str(DEFAULT_CONTROL_PROFILE))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-output-root", required=True)
    parser.add_argument("--carla-root", default=str(PROJECT_ROOT))
    parser.add_argument("--sensor-profile", choices=SENSOR_PROFILES, default="rgb_collision")
    parser.add_argument("--run-seed", type=int, default=20260817)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-runner", action="store_true")
    parser.add_argument("--validation-python", default=sys.executable)
    return parser.parse_args()


def load_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"CSV 为空: {path}")
    return rows


def load_records(path):
    records = {}
    for source in load_jsonl(os.path.abspath(path)):
        record = copy.deepcopy(source)
        record.pop("candidate_scoring_v2", None)
        require_valid_scenario(record)
        sample_id = str(record["sample_id"])
        if sample_id in records:
            raise ValueError(f"场景 sample_id 重复: {sample_id}")
        records[sample_id] = record
    return records


def load_selection(path):
    rows = load_csv(os.path.abspath(path))
    result = {}
    for row in rows:
        sample_id = str(row["sample_id"])
        if sample_id in result:
            raise ValueError(f"选择清单 sample_id 重复: {sample_id}")
        result[sample_id] = row
    return result


def build_selected_inputs(args):
    pair_rows = load_csv(os.path.abspath(args.pair_selection))
    if len(pair_rows) != 9:
        raise ValueError(f"配对清单必须包含 9 对，实际为 {len(pair_rows)}")
    arm_records = {
        "raw_15d": load_records(args.baseline_records),
        "physical_enhanced": load_records(args.enhanced_records),
    }
    arm_rows = {
        "raw_15d": load_selection(args.baseline_selection),
        "physical_enhanced": load_selection(args.enhanced_selection),
    }
    records = {}
    metadata_rows = []
    for pair in pair_rows:
        pair_index = int(pair["pair_index"])
        pair_id = pair["pair_id"]
        for arm, id_column, paired_column in (
            ("raw_15d", "baseline_sample_id", "enhanced_sample_id"),
            ("physical_enhanced", "enhanced_sample_id", "baseline_sample_id"),
        ):
            sample_id = pair[id_column]
            paired_sample_id = pair[paired_column]
            if sample_id not in arm_records[arm] or sample_id not in arm_rows[arm]:
                raise ValueError(f"{arm} 缺少配对场景: {sample_id}")
            if sample_id in records:
                raise ValueError(f"场景跨配对重复: {sample_id}")
            record = copy.deepcopy(arm_records[arm][sample_id])
            if record["conditions"]["target_risk_level"] != pair["target_risk_level"]:
                raise ValueError(f"配对目标档不一致: {sample_id}")
            row = dict(arm_rows[arm][sample_id])
            row.update(
                {
                    "comparison_arm": arm,
                    "feature_space": arm,
                    "pair_id": pair_id,
                    "pair_index": pair_index,
                    "paired_sample_id": paired_sample_id,
                    "slot_order": int(pair["slot_order"]),
                    "pair_crossover_strength": float(
                        pair["crossover_strength"]
                    ),
                    "pair_baseline_preference": float(
                        pair["baseline_preference"]
                    ),
                    "pair_enhanced_preference": float(
                        pair["enhanced_preference"]
                    ),
                    "pair_risk_disagreement": float(pair["risk_disagreement"]),
                    "pair_collision_disagreement": float(
                        pair["collision_disagreement"]
                    ),
                }
            )
            records[sample_id] = record
            metadata_rows.append(row)
    if len(records) != 18:
        raise ValueError(f"计划必须包含 18 个唯一场景，实际为 {len(records)}")
    return pair_rows, records, metadata_rows


def build_runs(records, rows_by_id, base_config, control_profile, config_dir, runtime_root):
    runs = {}
    for sample_id in sorted(records):
        record = records[sample_id]
        metadata = dict(rows_by_id[sample_id])
        for repeat_round, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
            run_id = (
                f"{metadata['pair_id']}__{metadata['comparison_arm']}__"
                f"{sample_id}__tm_{traffic_seed}__physical_feature_validation_v1"
            )
            config = compile_carla_config(copy.deepcopy(record), copy.deepcopy(base_config))
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            apply_regression_profile(config, control_profile)
            config["output"]["root"] = runtime_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            runs[(sample_id, traffic_seed)] = {
                **metadata,
                "sample_id": sample_id,
                "run_id": run_id,
                "repeat_round": repeat_round,
                "traffic_manager_seed": traffic_seed,
                "source": "physical_feature_validation_v1",
                "config_path": config_path,
                "expected_run_root": os.path.join(runtime_root, run_id),
                "group_index": None,
                "part_index": None,
                "run_order": None,
                "block_traffic_manager_seed": None,
            }
    return runs


def main():
    args = parse_args()
    output_dir = Path(os.path.abspath(args.output_dir))
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"输出目录非空，如需覆盖请使用 --force: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir = output_dir / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = os.path.abspath(args.runtime_output_root)

    pair_rows, records, metadata_rows = build_selected_inputs(args)
    rows_by_id = {row["sample_id"]: row for row in metadata_rows}
    selected_records_path = output_dir / "selected_records.jsonl"
    selection_csv_path = output_dir / "selection_metadata.csv"
    write_jsonl(
        selected_records_path,
        [records[sample_id] for sample_id in sorted(records)],
    )
    write_csv(selection_csv_path, metadata_rows)

    base_config = load_json(os.path.abspath(args.base_config))
    if args.sensor_profile == "rgb_collision":
        base_config["sensors"]["depth"]["enabled"] = False
        base_config["sensors"]["semantic"]["enabled"] = False
    _, control_profile = load_control_profile(args.control_profile)
    carla_root = os.path.abspath(args.carla_root)
    scene_runner = os.path.join(carla_root, "scenes", "scene_04_parameterized.py")
    runs = build_runs(
        records,
        rows_by_id,
        base_config,
        control_profile,
        str(config_dir),
        runtime_root,
    )
    groups, schedule = build_schedule(runs, args.run_seed)
    validation_results = []
    if args.validate_runner:
        validation_results = validate_configs(
            [row["config_path"] for row in schedule],
            scene_runner,
            args.validation_python,
        )
    write_csv(output_dir / "run_schedule.csv", schedule)
    write_scripts(str(output_dir), groups, carla_root)

    acceptance = copy.deepcopy(control_profile["acceptance_requirements"])
    acceptance["carla_version"] = "0.9.16"
    acceptance["route_verification_scope"] = "pre_collision_for_collision_runs"
    manifest = {
        "format": "feedback_candidate_validation_v1",
        "experiment": "physical_feature_paired_validation_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": current_git_commit(),
        "analysis_unit": "paired_unique_candidate",
        "traffic_seed_role": "repeated_measurement",
        "supports_significance_testing": False,
        "generators": ["lhs", "gmm", "cvae"],
        "selection_channels": [
            "stable_high_score",
            "high_uncertainty",
            "collision_propensity",
        ],
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "selected_scenario_count": len(records),
        "planned_run_count": len(schedule),
        "selected_records": str(selected_records_path),
        "selected_records_sha256": file_sha256(selected_records_path),
        "selection_metadata": str(selection_csv_path),
        "selection_metadata_sha256": file_sha256(selection_csv_path),
        "pair_selection": os.path.abspath(args.pair_selection),
        "pair_selection_sha256": file_sha256(args.pair_selection),
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_root,
        "route_lock_required": True,
        "controller_mode": control_profile["route"]["route_control_mode"],
        "control_profile_id": control_profile["profile_id"],
        "sensor_profile": args.sensor_profile,
        "acceptance_requirements": acceptance,
        "runs": schedule,
        "comparison_design": {
            "pair_count": len(pair_rows),
            "arms": list(ARMS),
            "pairing_factors": [
                "generator",
                "selection_channel",
                "target_risk_level",
                "traffic_manager_seed",
            ],
            "independent_unit": "scenario",
        },
        "validation_results": validation_results,
        "design": {
            "type": "paired_randomized_block_repeated_measurement",
            "run_seed": args.run_seed,
            "block_count": len(groups),
            "part_count": len([part for group in groups for part in group]),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# 物理增强候选 CARLA 配对验证 V1",
                "",
                "- 设计：3 个生成器 × 3 个选择通道，每个单元 1 对原始/增强候选。",
                f"- 本次验证：`{len(records)}` 个独立场景 × 3 个交通种子 = `{len(schedule)}` 次运行。",
                f"- 传感器档位：`{args.sensor_profile}`；本轮默认使用 RGB + Collision 性能基线。",
                "- 每个场景只出现一次，交通种子仅作为重复测量。",
                "- 先执行单场景冒烟，严格验收通过后再执行完整批次。",
                "",
                "## 执行",
                "",
                "```bash",
                "bash run_smoke.sh",
                "bash run_all.sh",
                "bash collect_results.sh",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        f"[PHYSICAL_PLAN] pairs={len(pair_rows)} | scenarios={len(records)} | "
        f"runs={len(schedule)}"
    )
    print(f"[PHYSICAL_PLAN] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
