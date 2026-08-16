"""准备碰撞边界主动补样的 18 个场景与 54 次多传感器运行。"""

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scenario_validator import compile_carla_config, require_valid_scenario  # noqa: E402
from tools.prepare_carla_route_regression import (  # noqa: E402
    apply_regression_profile,
    load_control_profile,
)


GENERATORS = ("lhs", "gmm", "cvae")
TARGET_LEVELS = ("high", "critical")
TRAFFIC_SEEDS = (20260821, 20260822, 20260823)
CAMERA_SETTINGS = {
    "width": 640,
    "height": 360,
    "sensor_tick": 0.2,
    "writer_workers": 1,
    "writer_queue_size": 8,
}


def parse_args():
    parser = argparse.ArgumentParser(description="准备碰撞边界主动补样多传感器验证")
    parser.add_argument("--scoring-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-output-root", required=True)
    parser.add_argument(
        "--base-config",
        default=str(PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"),
    )
    parser.add_argument(
        "--control-profile",
        default=str(
            PROJECT_ROOT
            / "configs"
            / "route_control_profiles"
            / "waypoint_follower_v1.json"
        ),
    )
    parser.add_argument("--carla-root", default=str(PROJECT_ROOT))
    parser.add_argument("--run-seed", type=int, default=20260816)
    parser.add_argument("--validation-python", default=sys.executable)
    parser.add_argument("--validate-runner", action="store_true")
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"不能写入空 CSV: {path}")
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_scored_rows(scoring_dir):
    path = Path(scoring_dir).resolve() / "scored_candidates.csv"
    if not path.is_file():
        raise FileNotFoundError(f"缺少 V3 候选评分文件: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        "source_path",
        "predicted_risk_std",
        "nearest_collision_distance",
        "collision_distance_margin",
        "collision_boundary_score",
    }
    missing = sorted(required - set(rows[0] if rows else []))
    if missing:
        raise ValueError(f"候选评分缺少字段: {missing}")
    return path, rows


def numeric(row, field):
    return float(row[field])


def select_cell(rows):
    if len(rows) < 3:
        raise ValueError("每个生成器×目标档候选不足 3 个")

    boundary_rows = sorted(
        rows,
        key=lambda row: (
            -numeric(row, "collision_boundary_score"),
            abs(numeric(row, "collision_distance_margin")),
            numeric(row, "nearest_collision_distance"),
            row["sample_id"],
        ),
    )
    uncertainty_rows = sorted(
        rows,
        key=lambda row: (
            -numeric(row, "predicted_risk_std"),
            -numeric(row, "collision_boundary_score"),
            row["sample_id"],
        ),
    )

    selected = []
    used = set()
    for row in boundary_rows:
        if row["sample_id"] in used:
            continue
        selected.append(("collision_boundary", row))
        used.add(row["sample_id"])
        if len(selected) == 2:
            break
    for row in uncertainty_rows:
        if row["sample_id"] not in used:
            selected.append(("high_uncertainty", row))
            used.add(row["sample_id"])
            break
    if len(selected) != 3:
        raise ValueError("主动补样单元未能选出 2 个边界样本和 1 个不确定性样本")

    output = []
    for order, (channel, row) in enumerate(selected, 1):
        output.append(
            {
                **row,
                "selection_channel": channel,
                "selection_order": order,
            }
        )
    return output


def select_rows(rows):
    cells = {}
    for row in rows:
        if row["generator"] not in GENERATORS:
            continue
        if row["target_risk_level"] not in TARGET_LEVELS:
            continue
        cells.setdefault((row["generator"], row["target_risk_level"]), []).append(row)

    selected = []
    for generator in GENERATORS:
        for target_level in TARGET_LEVELS:
            cell = cells.get((generator, target_level), [])
            selected.extend(select_cell(cell))
    if len(selected) != 18:
        raise ValueError(f"主动补样应有 18 个独立场景，实际为 {len(selected)}")
    if len({row["sample_id"] for row in selected}) != 18:
        raise ValueError("主动补样样本编号重复")
    return selected


def load_candidate_records(selected_rows):
    by_source = {}
    for row in selected_rows:
        by_source.setdefault(os.path.abspath(row["source_path"]), set()).add(
            row["sample_id"]
        )

    records_by_id = {}
    for source_path, sample_ids in by_source.items():
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"缺少候选 JSONL: {source_path}")
        with open(source_path, "r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                record = json.loads(line)
                sample_id = record.get("sample_id")
                if sample_id in sample_ids:
                    require_valid_scenario(record)
                    records_by_id[sample_id] = record
    missing = sorted(
        row["sample_id"] for row in selected_rows if row["sample_id"] not in records_by_id
    )
    if missing:
        raise ValueError(f"候选 JSONL 中缺少样本: {missing}")
    return records_by_id


def scoring_metadata(row):
    fields = (
        "predicted_risk_mean",
        "predicted_risk_std",
        "robust_predicted_risk_score",
        "predicted_collision_probability_mean",
        "predicted_collision_probability_std",
        "nearest_collision_distance",
        "nearest_non_collision_distance",
        "collision_distance_margin",
        "collision_boundary_score",
        "high_uncertainty_base",
    )
    result = {
        "selection_channel": row["selection_channel"],
        "selection_order": int(row["selection_order"]),
        "selection_policy": "collision_boundary_primary_high_uncertainty_auxiliary",
    }
    for field in fields:
        if field in row and row[field] not in (None, ""):
            result[field] = float(row[field])
    return result


def build_runs(
    selected_rows,
    records_by_id,
    base_config,
    control_profile,
    config_dir,
    runtime_output_root,
    traffic_manager_port,
):
    runs = []
    for row in selected_rows:
        record = copy.deepcopy(records_by_id[row["sample_id"]])
        for traffic_seed in TRAFFIC_SEEDS:
            run_id = (
                f"{row['sample_id']}__tm_{traffic_seed}"
                "__collision_boundary_multisensor_v1"
            )
            config = compile_carla_config(copy.deepcopy(record), copy.deepcopy(base_config))
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            config["scenario"]["traffic_manager_port"] = traffic_manager_port
            apply_regression_profile(config, control_profile)
            config["sensors"]["camera"].update(CAMERA_SETTINGS)
            for sensor_name in ("rgb", "depth", "semantic", "collision"):
                config["sensors"][sensor_name]["enabled"] = True
            config["sensors"]["semantic"]["save_raw_labels"] = True
            config["output"]["root"] = runtime_output_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            runs.append(
                {
                    "sample_id": row["sample_id"],
                    "generator": row["generator"],
                    "selection_channel": row["selection_channel"],
                    "selection_order": int(row["selection_order"]),
                    "target_risk_level": row["target_risk_level"],
                    "predicted_risk_mean": row.get("predicted_risk_mean"),
                    "predicted_risk_std": row.get("predicted_risk_std"),
                    "robust_predicted_risk_score": row.get(
                        "robust_predicted_risk_score"
                    ),
                    "nearest_collision_distance": row.get(
                        "nearest_collision_distance"
                    ),
                    "collision_boundary_score": row.get("collision_boundary_score"),
                    "high_uncertainty_base": row.get("high_uncertainty_base"),
                    "run_id": run_id,
                    "traffic_manager_seed": traffic_seed,
                    "config_path": config_path,
                    "expected_run_root": os.path.join(runtime_output_root, run_id),
                    "group_index": None,
                    "part_index": None,
                    "run_order": None,
                    "block_selection_order": None,
                    "block_traffic_manager_seed": None,
                }
            )
    return runs


def build_schedule(runs, run_seed):
    by_block = {}
    for run in runs:
        key = (run["selection_order"], run["traffic_manager_seed"])
        by_block.setdefault(key, []).append(run)
    expected_blocks = [
        (selection_order, traffic_seed)
        for selection_order in (1, 2, 3)
        for traffic_seed in TRAFFIC_SEEDS
    ]
    if set(by_block) != set(expected_blocks) or any(
        len(by_block[key]) != 6 for key in expected_blocks
    ):
        raise ValueError("区组设计不完整：每个选择序号×交通种子应有 6 次运行")

    rng = random.Random(run_seed)
    blocks = expected_blocks[:]
    rng.shuffle(blocks)
    schedule = []
    groups = []
    run_order = 1
    part_index = 1
    for group_index, block in enumerate(blocks, 1):
        current = by_block[block][:]
        rng.shuffle(current)
        group_parts = []
        for offset in range(0, len(current), 3):
            part = current[offset : offset + 3]
            for run in part:
                run["group_index"] = group_index
                run["part_index"] = part_index
                run["run_order"] = run_order
                run["block_selection_order"] = block[0]
                run["block_traffic_manager_seed"] = block[1]
                schedule.append(run)
                run_order += 1
            group_parts.append(part)
            part_index += 1
        groups.append(group_parts)
    return groups, schedule


def write_executable(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")
    os.chmod(
        path,
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH,
    )


def write_scripts(output_dir, groups, carla_root):
    runner = os.path.join(carla_root, "tools", "run_feedback_candidate_validation.py")
    collector = os.path.join(
        carla_root, "tools", "collect_feedback_candidate_validation.py"
    )
    checker = os.path.join(carla_root, "tools", "check_multisensor_manifest.py")
    manifest = os.path.join(output_dir, "manifest.json")
    group_paths = []
    part_index = 1
    for group_index, group_parts in enumerate(groups, 1):
        part_paths = []
        for _ in group_parts:
            part_path = os.path.join(output_dir, f"run_part_{part_index:02d}.sh")
            write_executable(
                part_path,
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f'python -u "{runner}" --manifest "{manifest}" --part-index {part_index} --pause-seconds 8',
                ],
            )
            part_paths.append(part_path)
            part_index += 1
        group_path = os.path.join(output_dir, f"run_group_{group_index:02d}.sh")
        group_lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
        for part_path in part_paths:
            group_lines.extend([f'bash "{part_path}"', "sleep 15"])
        group_lines.append(f'python -u "{checker}" --manifest "{manifest}" --min-completed 1')
        write_executable(group_path, group_lines)
        group_paths.append(group_path)

    run_all = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for group_path in group_paths:
        run_all.extend([f'bash "{group_path}"', "sleep 30"])
    write_executable(os.path.join(output_dir, "run_all.sh"), run_all)
    write_executable(
        os.path.join(output_dir, "run_smoke.sh"),
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'python -u "{runner}" --manifest "{manifest}" --limit 1 --pause-seconds 0',
            f'python -u "{checker}" --manifest "{manifest}" --min-completed 1',
        ],
    )
    write_executable(
        os.path.join(output_dir, "collect_results.sh"),
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'python -u "{collector}" --manifest "{manifest}"',
            f'python -u "{checker}" --manifest "{manifest}" --require-all',
        ],
    )
    return group_paths


def validate_configs(config_paths, scene_runner, validation_python):
    results = []
    for config_path in config_paths:
        completed = subprocess.run(
            [validation_python, scene_runner, "--config", config_path, "--validate-only"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "config_path": config_path,
                "valid": completed.returncode == 0,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(f"配置校验失败: {config_path}\n{completed.stdout}\n{completed.stderr}")
    return results


def current_git_commit():
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def main():
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    config_dir = os.path.join(output_dir, "configs")
    os.makedirs(config_dir, exist_ok=True)

    scoring_path, scored_rows = load_scored_rows(args.scoring_dir)
    selected_rows = select_rows(scored_rows)
    records_by_id = load_candidate_records(selected_rows)
    selected_records = []
    for row in selected_rows:
        record = copy.deepcopy(records_by_id[row["sample_id"]])
        selected_records.append(record)
    selected_records.sort(key=lambda row: row["sample_id"])

    selected_records_path = os.path.join(output_dir, "selected_records.jsonl")
    write_jsonl(selected_records_path, selected_records)
    selection_metadata = []
    for row in selected_rows:
        selection_metadata.append(
            {
                "sample_id": row["sample_id"],
                "generator": row["generator"],
                "target_risk_level": row["target_risk_level"],
                "selection_channel": row["selection_channel"],
                "selection_order": row["selection_order"],
                "collision_boundary_score": row["collision_boundary_score"],
                "predicted_risk_std": row["predicted_risk_std"],
                "nearest_collision_distance": row["nearest_collision_distance"],
                "collision_distance_margin": row["collision_distance_margin"],
            }
        )
    selection_metadata_path = os.path.join(output_dir, "selection_metadata.csv")
    write_csv(selection_metadata_path, selection_metadata)

    base_config_path = os.path.abspath(args.base_config)
    control_profile_path, control_profile = load_control_profile(args.control_profile)
    base_config = json.loads(Path(base_config_path).read_text(encoding="utf-8"))
    traffic_manager_port = int(os.environ.get("CARLA_TRAFFIC_MANAGER_PORT", "8100"))
    runtime_output_root = os.path.abspath(args.runtime_output_root)
    scene_runner = os.path.join(os.path.abspath(args.carla_root), "scenes", "scene_04_parameterized.py")
    runs = build_runs(
        selected_rows,
        records_by_id,
        base_config,
        control_profile,
        config_dir,
        runtime_output_root,
        traffic_manager_port,
    )
    groups, schedule = build_schedule(runs, args.run_seed)
    validation_results = []
    if args.validate_runner:
        validation_results = validate_configs(
            [run["config_path"] for run in schedule],
            scene_runner,
            args.validation_python,
        )

    write_csv(os.path.join(output_dir, "run_schedule.csv"), schedule)
    group_paths = write_scripts(output_dir, groups, os.path.abspath(args.carla_root))
    acceptance = copy.deepcopy(control_profile["acceptance_requirements"])
    acceptance.update(
        {
            "carla_version": "0.9.16",
            "route_verification_scope": "pre_collision_for_collision_runs",
            "minimum_depth_frames": 100,
            "minimum_semantic_frames": 100,
            "minimum_collision_sensor_events_field": True,
        }
    )
    manifest = {
        "format": "feedback_candidate_validation_v1",
        "experiment_format": "collision_boundary_multisensor_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": current_git_commit(),
        "analysis_unit": "selected_scenario",
        "traffic_seed_role": "repeated_measurement",
        "supports_significance_testing": False,
        "generators": list(GENERATORS),
        "target_levels": list(TARGET_LEVELS),
        "selection_channels": ["collision_boundary", "high_uncertainty"],
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "selected_scenario_count": len(selected_records),
        "planned_run_count": len(schedule),
        "selected_records": selected_records_path,
        "selected_records_sha256": file_sha256(selected_records_path),
        "selection_metadata": selection_metadata_path,
        "selection_metadata_sha256": file_sha256(selection_metadata_path),
        "source_scoring_dir": os.path.abspath(args.scoring_dir),
        "source_scoring_file": str(scoring_path),
        "source_scoring_sha256": file_sha256(scoring_path),
        "base_config": base_config_path,
        "base_config_sha256": file_sha256(base_config_path),
        "control_profile_id": control_profile["profile_id"],
        "control_profile_path": control_profile_path,
        "control_profile_sha256": file_sha256(control_profile_path),
        "carla_root": os.path.abspath(args.carla_root),
        "scene_runner": scene_runner,
        "runtime_output_root": runtime_output_root,
        "route_lock_required": True,
        "controller_mode": control_profile["route"]["route_control_mode"],
        "sensor_profile": {
            "rgb": True,
            "depth": True,
            "semantic": True,
            "collision": True,
            **CAMERA_SETTINGS,
        },
        "acceptance_requirements": acceptance,
        "design": {
            "type": "randomized_block_repeated_measurement",
            "run_seed": args.run_seed,
            "block_count": len(groups),
            "runs_per_block": 6,
            "parts_per_block": 2,
            "runs_per_part": 3,
            "description": (
                "3 生成器×high/critical 各 3 个独立场景；"
                "每个场景 3 个 Traffic Manager 种子；"
                "每个选择序号×交通种子区组包含 6 次运行并随机化顺序。"
            ),
        },
        "selection_policy": {
            "primary": "collision_boundary_score descending",
            "boundary_tiebreakers": [
                "absolute collision_distance_margin ascending",
                "nearest_collision_distance ascending",
                "sample_id ascending",
            ],
            "auxiliary": "predicted_risk_std descending",
            "quota": "each generator×target level: 2 collision_boundary + 1 high_uncertainty",
        },
        "static_validation": {
            "requested": args.validate_runner,
            "validated_count": len(validation_results),
            "passed_count": sum(row["valid"] for row in validation_results),
        },
        "group_scripts": group_paths,
        "runs": schedule,
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    write_json(manifest_path, manifest)
    if validation_results:
        write_csv(os.path.join(output_dir, "static_validation.csv"), validation_results)

    readme = os.path.join(output_dir, "README.md")
    Path(readme).write_text(
        "\n".join(
            [
                "# 碰撞边界主动补样多传感器验证 V1",
                "",
                "- 独立实验单位：18 个场景。",
                "- 结构：3 个生成器 × high/critical 两档 × 每格 3 个。",
                "- 每个单元：2 个 collision_boundary + 1 个 high_uncertainty。",
                "- 重复测量：3 个 Traffic Manager 种子，共 54 次运行。",
                "- 传感器：RGB、Depth、Semantic Segmentation、Collision，640×360，0.2s。",
                "- 控制器：冻结的 waypoint_follower_v1；路线严格验收保留。",
                "- 统计边界：Traffic Manager 种子是重复测量，不是独立样本。",
                "",
                "执行顺序：run_smoke.sh → run_all.sh → collect_results.sh。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[PREPARE] scoring_dir={args.scoring_dir}")
    print("[PREPARE] selected=18 | planned_runs=54 | sensors=rgb,depth,semantic,collision")
    print(f"[PREPARE] manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
