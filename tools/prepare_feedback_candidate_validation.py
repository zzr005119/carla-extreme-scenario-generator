"""准备 27 个反馈短名单的 81 次 CARLA 外部验证。"""

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import shutil
import stat
import subprocess
import sys
from datetime import datetime


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    load_json,
    require_valid_scenario,
)
from tools.prepare_carla_route_regression import (  # noqa: E402
    apply_regression_profile,
    load_control_profile,
)


GENERATORS = ("lhs", "gmm", "cvae")
SELECTION_CHANNELS = (
    "stable_high_score",
    "high_uncertainty",
    "collision_boundary",
)
TRAFFIC_SEEDS = (20260821, 20260822, 20260823)
DEFAULT_SELECTED_RECORDS = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "feedback_candidate_scoring_v1",
    "scoring",
    "selected_candidates.json",
)
DEFAULT_SELECTION_CSV = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "feedback_candidate_scoring_v1",
    "scoring",
    "selected_candidates.csv",
)
DEFAULT_BASE_CONFIG = os.path.join(
    PROJECT_ROOT, "configs", "multi_hazard_rainy_night.json"
)
DEFAULT_CONTROL_PROFILE = os.path.join(
    PROJECT_ROOT,
    "configs",
    "route_control_profiles",
    "waypoint_follower_v1.json",
)
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT, "output", "feedback_candidate_validation_v1"
)
DEFAULT_RUNTIME_OUTPUT_ROOT = os.path.join(
    PROJECT_ROOT, "output", "feedback_candidate_validation_v1", "runtime"
)


def parse_args():
    parser = argparse.ArgumentParser(description="准备反馈候选 CARLA 外部验证")
    parser.add_argument("--selected-records", default=DEFAULT_SELECTED_RECORDS)
    parser.add_argument("--selection-csv", default=DEFAULT_SELECTION_CSV)
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--control-profile", default=DEFAULT_CONTROL_PROFILE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--runtime-output-root", default=DEFAULT_RUNTIME_OUTPUT_ROOT)
    parser.add_argument("--carla-root", default=PROJECT_ROOT)
    parser.add_argument("--run-seed", type=int, default=20260815)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-runner", action="store_true")
    parser.add_argument("--validation-python", default=sys.executable)
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
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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


def load_selected_records(path):
    with open(path, "r", encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list):
        raise ValueError("selected_candidates.json 必须是 JSON 数组")
    seen = set()
    for record in records:
        require_valid_scenario(record)
        sample_id = record["sample_id"]
        if sample_id in seen:
            raise ValueError(f"场景编号重复: {sample_id}")
        seen.add(sample_id)
    return records


def load_selection_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {
        "sample_id",
        "generator",
        "selection_channel",
        "selection_order",
        "target_risk_level",
        "predicted_risk_mean",
        "predicted_risk_std",
        "robust_predicted_risk_score",
        "bootstrap_top_k_frequency",
        "nearest_collision_distance",
        "collision_boundary_score",
        "selection_diversity_distance",
    }
    missing = sorted(required - set(rows[0])) if rows else sorted(required)
    if missing:
        raise ValueError(f"选择清单缺少列: {missing}")
    return rows


def validate_design(records, selection_rows):
    records_by_id = {record["sample_id"]: record for record in records}
    rows_by_id = {row["sample_id"]: row for row in selection_rows}
    if set(records_by_id) != set(rows_by_id):
        raise ValueError("selected_candidates.json 与 CSV 的 sample_id 集合不一致")
    if len(records) != 27:
        raise ValueError(f"当前设计固定要求 27 个独立场景，实际为 {len(records)}")

    cells = {}
    for row in selection_rows:
        generator = row["generator"]
        channel = row["selection_channel"]
        order = int(row["selection_order"])
        if generator not in GENERATORS or channel not in SELECTION_CHANNELS:
            raise ValueError(f"未知生成器或选择通道: {generator}/{channel}")
        cells.setdefault((generator, channel), []).append(row)
        record = records_by_id[row["sample_id"]]
        if record["conditions"]["target_risk_level"] != row["target_risk_level"]:
            raise ValueError(f"目标风险档不一致: {row['sample_id']}")
        if order not in (1, 2, 3):
            raise ValueError(f"选择序号必须为 1/2/3: {row['sample_id']}")
    for generator in GENERATORS:
        for channel in SELECTION_CHANNELS:
            current = cells.get((generator, channel), [])
            if len(current) != 3:
                raise ValueError(f"{generator}/{channel} 必须有 3 个场景")
            if {int(row["selection_order"]) for row in current} != {1, 2, 3}:
                raise ValueError(f"{generator}/{channel} 的选择序号不完整")
            targets = {row["target_risk_level"] for row in current}
            if not {"high", "critical"}.issubset(targets):
                raise ValueError(f"{generator}/{channel} 未同时覆盖 high 与 critical")
    return records_by_id, rows_by_id


def selection_metadata(row):
    numeric_fields = (
        "predicted_risk_mean",
        "predicted_risk_std",
        "robust_predicted_risk_score",
        "bootstrap_top_k_frequency",
        "nearest_observed_distance",
        "nearest_collision_distance",
        "nearest_non_collision_distance",
        "collision_boundary_score",
        "selection_utility",
        "selection_diversity_distance",
    )
    result = {
        "sample_id": row["sample_id"],
        "generator": row["generator"],
        "selection_channel": row["selection_channel"],
        "selection_order": int(row["selection_order"]),
        "target_risk_level": row["target_risk_level"],
    }
    for field in numeric_fields:
        if row.get(field) not in (None, ""):
            result[field] = float(row[field])
    return result


def build_runs(
    records_by_id,
    rows_by_id,
    base_config,
    control_profile,
    config_dir,
    runtime_output_root,
):
    runs = {}
    for sample_id, record in sorted(records_by_id.items()):
        metadata = selection_metadata(rows_by_id[sample_id])
        for repeat_round, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
            run_id = f"{sample_id}__tm_{traffic_seed}__feedback_validation_v1"
            config = compile_carla_config(
                copy.deepcopy(record), copy.deepcopy(base_config)
            )
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            apply_regression_profile(config, control_profile)
            config["output"]["root"] = runtime_output_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            runs[(sample_id, traffic_seed)] = {
                **metadata,
                "run_id": run_id,
                "repeat_round": repeat_round,
                "traffic_manager_seed": traffic_seed,
                "source": "feedback_candidate_validation_v1",
                "config_path": config_path,
                "expected_run_root": os.path.join(runtime_output_root, run_id),
                "group_index": None,
                "part_index": None,
                "run_order": None,
                "block_selection_order": None,
                "block_traffic_manager_seed": None,
            }
    return runs


def build_schedule(runs, selection_rows, run_seed):
    rows_by_cell_order = {
        (row["generator"], row["selection_channel"], int(row["selection_order"])): row
        for row in selection_rows
    }
    blocks = [
        (selection_order, traffic_seed)
        for selection_order in (1, 2, 3)
        for traffic_seed in TRAFFIC_SEEDS
    ]
    generator = random.Random(run_seed)
    generator.shuffle(blocks)
    groups = []
    schedule = []
    part_index = 0
    for group_index, (selection_order, traffic_seed) in enumerate(blocks, 1):
        current = []
        for model_name in GENERATORS:
            for channel in SELECTION_CHANNELS:
                selected = rows_by_cell_order[(model_name, channel, selection_order)]
                current.append(runs[(selected["sample_id"], traffic_seed)])
        generator.shuffle(current)
        group_parts = []
        for offset in range(0, len(current), 3):
            part_index += 1
            part_rows = current[offset : offset + 3]
            for row in part_rows:
                row["group_index"] = group_index
                row["part_index"] = part_index
                row["run_order"] = len(schedule) + 1
                row["block_selection_order"] = selection_order
                row["block_traffic_manager_seed"] = traffic_seed
                schedule.append(row)
            group_parts.append(part_rows)
        groups.append(group_parts)
    return groups, schedule


def validate_configs(config_paths, scene_runner, python_path):
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    results = []
    for config_path in config_paths:
        completed = subprocess.run(
            [
                os.path.abspath(python_path),
                scene_runner,
                "--config",
                config_path,
                "--validate-only",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        results.append(
            {
                "config_path": config_path,
                "valid": completed.returncode == 0,
                "return_code": completed.returncode,
                "message": (completed.stdout or completed.stderr).strip(),
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"配置校验失败: {config_path}\n{completed.stdout}\n{completed.stderr}"
            )
    return results


def write_scripts(output_dir, groups, project_root):
    runner = os.path.join(project_root, "tools", "run_feedback_candidate_validation.py")
    collector = os.path.join(
        project_root, "tools", "collect_feedback_candidate_validation.py"
    )
    manifest = os.path.join(output_dir, "manifest.json")
    part_paths = []
    group_paths = []
    for group_index, group_parts in enumerate(groups, 1):
        current_parts = []
        for part_rows in group_parts:
            part_index = int(part_rows[0]["part_index"])
            part_path = os.path.join(output_dir, f"run_part_{part_index:02d}.sh")
            write_executable(
                part_path,
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f'python -u "{runner}" --manifest "{manifest}" --part-index {part_index}',
                ],
            )
            part_paths.append(part_path)
            current_parts.append(part_path)
        group_path = os.path.join(output_dir, f"run_group_{group_index:02d}.sh")
        group_lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
        for part_path in current_parts:
            group_lines.extend([f'bash "{part_path}"', "sleep 20"])
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
            f'python -u "{runner}" --manifest "{manifest}" --limit 1',
        ],
    )
    write_executable(
        os.path.join(output_dir, "collect_results.sh"),
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'python -u "{collector}" --manifest "{manifest}"',
        ],
    )
    return part_paths, group_paths


def write_readme(path, manifest):
    lines = [
        "# 反馈候选 CARLA 外部验证 V1",
        "",
        "## 设计",
        "",
        "- 独立实验单位：27 个反馈短名单场景。",
        "- 重复测量：每个场景使用 3 个 Traffic Manager 种子，共 81 次。",
        "- 因素：3 个生成器 × 3 个选择通道 × 每格 3 个场景。",
        "- 目标档：每个生成器均为 high 3 个、critical 6 个。",
        "- 调度：9 个随机化区组，每组 9 次并拆成 3 个小批次。",
        "- 控制器、传感器和严格验收均冻结为 waypoint_follower_v1。",
        "- 非碰撞运行按全程路线验收；发生碰撞时按首次碰撞前路线验收，并保留全程路线指标。",
        "",
        "## 执行",
        "",
        "```bash",
        "bash run_smoke.sh",
        "bash run_all.sh",
        "bash collect_results.sh",
        "```",
        "",
        "运行器会跳过已经通过严格验收的配置，因此中断后可直接重新执行。",
        "",
        "## 统计边界",
        "",
        "三个交通种子不作为独立样本；生成器和选择通道各只有 9 个独立场景，本轮只作工程描述性外部验证。",
        "",
        f"计划运行总数：`{manifest['planned_run_count']}`。",
        "",
    ]
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


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
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(f"输出目录非空: {output_dir}")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    config_dir = os.path.join(output_dir, "configs")
    os.makedirs(config_dir, exist_ok=True)

    selected_records_path = os.path.abspath(args.selected_records)
    selection_csv_path = os.path.abspath(args.selection_csv)
    records = load_selected_records(selected_records_path)
    selection_rows = load_selection_rows(selection_csv_path)
    records_by_id, rows_by_id = validate_design(records, selection_rows)
    selected_jsonl = os.path.join(output_dir, "selected_records.jsonl")
    write_jsonl(selected_jsonl, records)
    copied_selection_csv = os.path.join(output_dir, "selection_metadata.csv")
    write_csv(copied_selection_csv, [selection_metadata(row) for row in selection_rows])

    base_config_path = os.path.abspath(args.base_config)
    base_config = load_json(base_config_path)
    control_profile_path, control_profile = load_control_profile(args.control_profile)
    carla_root = os.path.abspath(args.carla_root)
    scene_runner = os.path.join(carla_root, "scenes", "scene_04_parameterized.py")
    runtime_output_root = os.path.abspath(args.runtime_output_root)
    runs = build_runs(
        records_by_id,
        rows_by_id,
        base_config,
        control_profile,
        config_dir,
        runtime_output_root,
    )
    groups, schedule = build_schedule(runs, selection_rows, args.run_seed)
    validation_results = []
    if args.validate_runner:
        validation_results = validate_configs(
            [row["config_path"] for row in schedule],
            scene_runner,
            args.validation_python,
        )

    schedule_path = os.path.join(output_dir, "run_schedule.csv")
    write_csv(schedule_path, schedule)
    part_paths, group_paths = write_scripts(output_dir, groups, carla_root)
    route = control_profile["route"]
    acceptance = copy.deepcopy(control_profile["acceptance_requirements"])
    acceptance["carla_version"] = "0.9.16"
    acceptance[
        "route_verification_scope"
    ] = "pre_collision_for_collision_runs"
    manifest = {
        "format": "feedback_candidate_validation_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": current_git_commit(),
        "analysis_unit": "selected_scenario",
        "traffic_seed_role": "repeated_measurement",
        "supports_significance_testing": False,
        "generators": list(GENERATORS),
        "selection_channels": list(SELECTION_CHANNELS),
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "selected_scenario_count": len(records),
        "planned_run_count": len(schedule),
        "selected_records": selected_jsonl,
        "selected_records_sha256": file_sha256(selected_jsonl),
        "selection_metadata": copied_selection_csv,
        "selection_metadata_sha256": file_sha256(copied_selection_csv),
        "source_selected_records": selected_records_path,
        "source_selected_records_sha256": file_sha256(selected_records_path),
        "source_selection_csv": selection_csv_path,
        "source_selection_csv_sha256": file_sha256(selection_csv_path),
        "base_config": base_config_path,
        "base_config_sha256": file_sha256(base_config_path),
        "control_profile_id": control_profile["profile_id"],
        "control_profile_path": control_profile_path,
        "control_profile_sha256": file_sha256(control_profile_path),
        "carla_root": carla_root,
        "scene_runner": scene_runner,
        "runtime_output_root": runtime_output_root,
        "route_lock_required": True,
        "controller_mode": route["route_control_mode"],
        "acceptance_requirements": acceptance,
        "design": {
            "type": "randomized_block_repeated_measurement",
            "run_seed": args.run_seed,
            "block_count": len(groups),
            "runs_per_block": 9,
            "parts_per_block": 3,
            "runs_per_part": 3,
            "description": (
                "9 个区组覆盖 selection_order×traffic_seed；每个区组包含 "
                "3 生成器×3 选择通道并随机运行"
            ),
        },
        "static_validation": {
            "requested": args.validate_runner,
            "validated_count": len(validation_results),
            "passed_count": sum(row["valid"] for row in validation_results),
        },
        "part_scripts": part_paths,
        "group_scripts": group_paths,
        "runs": schedule,
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    write_json(manifest_path, manifest)
    if validation_results:
        write_csv(os.path.join(output_dir, "static_validation.csv"), validation_results)
    write_readme(os.path.join(output_dir, "README.md"), manifest)
    print(f"[PREPARE] independent_scenarios={len(records)}")
    print(f"[PREPARE] planned_runs={len(schedule)}")
    print(f"[PREPARE] blocks={len(groups)} | parts={len(part_paths)}")
    if validation_results:
        print(f"[PREPARE] validate-only={len(validation_results)}/{len(schedule)}")
    print(f"[PREPARE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
