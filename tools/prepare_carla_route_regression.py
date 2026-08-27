"""准备 waypoint 控制器下的 CVAE 多种子受控重复性回归。"""

import argparse
import copy
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import load_jsonl  # noqa: E402
from core.scenario_validator import compile_carla_config, load_json  # noqa: E402


DEFAULT_SOURCE_MANIFEST = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "cvae_validation_v2",
    "manifest.json",
)
DEFAULT_CONTROL_PROFILE = os.path.join(
    PROJECT_ROOT,
    "configs",
    "route_control_profiles",
    "waypoint_follower_v1.json",
)
DEFAULT_CARLA_ROOT = PROJECT_ROOT
DEFAULT_RUNTIME_OUTPUT_BASE = r"F:\Carla\output-0.9.16"
REPRESENTATIVE_SAMPLE_IDS = (
    "cvae_low_20260813_0001",
    "cvae_medium_20260813_0103",
    "cvae_high_20260813_0074",
)
TRAFFIC_SEEDS = (20260821, 20260822, 20260823)
RISK_LEVELS = ("low", "medium", "high", "critical")


def parse_args():
    parser = argparse.ArgumentParser(description="准备 waypoint 受控重复性回归")
    parser.add_argument("--source-manifest", default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--output-dir")
    parser.add_argument("--carla-root", default=DEFAULT_CARLA_ROOT)
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--control-profile", default=DEFAULT_CONTROL_PROFILE)
    parser.add_argument(
        "--sample-set",
        choices=("representative3", "all12"),
        default="representative3",
    )
    parser.add_argument(
        "--experiment-version",
        choices=("v3", "v4"),
        default="v3",
    )
    parser.add_argument("--run-seed", type=int, default=20260813)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def resolve_path(base_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_control_profile(path):
    profile_path = os.path.abspath(path)
    profile = load_json(profile_path)
    required = {
        "profile_id",
        "sensor_profile",
        "route",
        "controller",
        "acceptance_requirements",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise ValueError(f"控制配置缺少字段: {', '.join(missing)}")
    route = profile["route"]
    acceptance = profile["acceptance_requirements"]
    if route.get("route_control_mode") != "waypoint_follower":
        raise ValueError("控制配置必须使用 waypoint_follower")
    if acceptance.get("route_control_mode") != route["route_control_mode"]:
        raise ValueError("控制模式与验收模式不一致")
    if float(acceptance["maximum_route_deviation_m"]) != float(
        route["route_deviation_tolerance_m"]
    ):
        raise ValueError("路线偏差容差与验收阈值不一致")
    return profile_path, profile


def apply_regression_profile(config, profile):
    sensor_profile = profile["sensor_profile"]
    camera = config["sensors"]["camera"]
    camera.update(
        {
            "width": int(sensor_profile["width"]),
            "height": int(sensor_profile["height"]),
            "sensor_tick": float(sensor_profile["sensor_tick"]),
            "writer_workers": int(sensor_profile["writer_workers"]),
            "writer_queue_size": int(sensor_profile["writer_queue_size"]),
        }
    )
    config["sensors"]["rgb"]["enabled"] = bool(
        sensor_profile["rgb_enabled"]
    )
    config["sensors"]["depth"]["enabled"] = bool(
        sensor_profile["depth_enabled"]
    )
    config["sensors"]["semantic"]["enabled"] = bool(
        sensor_profile["semantic_enabled"]
    )
    route = profile["route"]
    config["traffic"].update(
        {
            "route_lock_enabled": bool(route["route_lock_enabled"]),
            "route_control_mode": route["route_control_mode"],
            "route_length_m": float(route["route_length_m"]),
            "route_step_m": float(route["route_step_m"]),
            "route_deviation_tolerance_m": float(
                route["route_deviation_tolerance_m"]
            ),
            "lead_stop_lock_enabled": bool(
                route.get("lead_stop_lock_enabled", True)
            ),
            "lead_stop_lock_speed_kmh": float(
                route.get("lead_stop_lock_speed_kmh", 1.0)
            ),
            "lead_stop_lock_confirm_steps": int(
                route.get("lead_stop_lock_confirm_steps", 3)
            ),
            "route_controller": copy.deepcopy(profile["controller"]),
        }
    )
    return config


def write_lines(path, lines):
    with open(path, "w", encoding="ascii", newline="") as file:
        file.write("\r\n".join(lines))


def write_run_script(path, carla_root, scene_runner, rows):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        f'cd /d "{carla_root}"',
        "",
    ]
    for index, row in enumerate(rows, 1):
        config_name = os.path.basename(row["config_path"])
        lines.extend(
            [
                f"echo [RUN {index}/{len(rows)}] {row['run_id']}",
                f'python -u "{scene_runner}" --config "%~dp0configs\\{config_name}"',
                "if errorlevel 1 goto :failed",
                "timeout /t 10 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] Route regression batch completed.",
            "exit /b 0",
            "",
            ":failed",
            "echo [FAILED] Stop after CARLA or Python error.",
            "exit /b 1",
            "",
        ]
    )
    write_lines(path, lines)


def write_run_all(path, part_paths):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        "",
    ]
    for part_path in part_paths:
        lines.extend(
            [
                f'call "%~dp0{os.path.basename(part_path)}"',
                "if errorlevel 1 exit /b 1",
                "timeout /t 20 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            'call "%~dp0collect_results.cmd"',
            "if errorlevel 1 exit /b 1",
            "",
            "echo [DONE] All route regression batches completed.",
            "exit /b 0",
            "",
        ]
    )
    write_lines(path, lines)


def write_collect_script(path):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        'cd /d "%~dp0..\\..\\.."',
        "",
        "python -u tools\\collect_carla_repeatability.py "
        '--manifest "%~dp0manifest.json"',
        "if errorlevel 1 goto :failed",
        "",
        "echo [DONE] Strict repeatability acceptance passed.",
        "exit /b 0",
        "",
        ":failed",
        "echo [FAILED] Strict repeatability acceptance failed.",
        "exit /b 1",
        "",
    ]
    write_lines(path, lines)


def write_readme(path, manifest, part_paths):
    run_all_path = os.path.join(os.path.dirname(path), "run_all.cmd")
    version = manifest["experiment_version"].upper()
    scenario_count = manifest["scenario_count"]
    run_count = manifest["planned_run_count"]
    part_count = len(part_paths)
    lines = [
        f"# CVAE CARLA 确定性路线回归 {version}",
        "",
        f"该实验使用冻结的 `{manifest['control_profile_id']}`，验证 "
        f"{scenario_count} 个固定 CVAE 场景在三个交通种子下的受控重复性。",
        "",
        "## 实验设计",
        "",
        f"- 固定场景数：{scenario_count}；总运行数：{run_count}。",
        f"- 共 {part_count} 个运行区组，每个区组内随机执行。",
        f"- 调度设计：{manifest['design']['description']}",
        "- 仅用于工程回归，不支持统计显著性结论。",
        "- 验收要求包括场景完成、RGB 不少于 100 帧、服务健康、双车同时在途率 1.0，以及双方最大路线偏差不超过 3.0 m。",
        "- 逐帧记录双方控制量、主车安全制动原因、控制器路径进度和路线拓扑诊断。",
        "",
        "## 执行",
        "",
        "启动 CARLAUE4 后运行：",
        "",
        "```cmd",
        f'"{run_all_path}"',
        "```",
        "",
        f"`run_all.cmd` 会在 {run_count} 次仿真完成后自动执行严格验收。也可分批运行：",
        "",
    ]
    lines.extend(f"- `{os.path.basename(item)}`" for item in part_paths)
    lines.extend(
        [
            "",
            "分批运行全部完成后执行：",
            "",
            "```cmd",
            f'"{os.path.join(os.path.dirname(path), "collect_results.cmd")}"',
            "```",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write(chr(10).join(lines))


def select_sample_ids(source_manifest, sample_set):
    if sample_set == "representative3":
        return list(REPRESENTATIVE_SAMPLE_IDS)
    sample_ids = [row["sample_id"] for row in source_manifest["records"]]
    counts = {
        level: sum(
            row["target_risk_level"] == level
            for row in source_manifest["records"]
        )
        for level in RISK_LEVELS
    }
    if len(sample_ids) != 12 or any(count != 3 for count in counts.values()):
        raise ValueError(
            "all12 要求来源清单包含低/中/高/临界各 3 条，共 12 条"
        )
    return sample_ids


def validate_experiment_args(args):
    expected_version = {
        "representative3": "v3",
        "all12": "v4",
    }[args.sample_set]
    if args.experiment_version != expected_version:
        raise ValueError(
            f"{args.sample_set} 必须使用 experiment-version={expected_version}"
        )


def main():
    args = parse_args()
    validate_experiment_args(args)
    source_manifest_path = os.path.abspath(args.source_manifest)
    source_manifest_dir = os.path.dirname(source_manifest_path)
    source_manifest = load_json(source_manifest_path)
    if source_manifest.get("format") != "cvae_carla_validation_v1":
        raise ValueError("来源清单不是支持的 CVAE 验证清单")

    experiment_name = f"cvae_repeatability_{args.experiment_version}"
    output_dir = os.path.abspath(
        args.output_dir
        or os.path.join(
            PROJECT_ROOT,
            "data",
            "scenarios",
            experiment_name,
        )
    )
    control_profile_path, control_profile = load_control_profile(
        args.control_profile
    )
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(f"输出目录非空: {output_dir}，如需覆盖请加 --force")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    config_dir = os.path.join(output_dir, "configs")
    os.makedirs(config_dir, exist_ok=True)

    records_path = resolve_path(
        source_manifest_dir,
        source_manifest["selected_records"],
    )
    records_by_id = {
        record["sample_id"]: record for record in load_jsonl(records_path)
    }
    source_rows = {
        row["sample_id"]: row for row in source_manifest["records"]
    }
    sample_ids = select_sample_ids(source_manifest, args.sample_set)
    missing = [
        sample_id
        for sample_id in sample_ids
        if sample_id not in records_by_id or sample_id not in source_rows
    ]
    if missing:
        raise ValueError(f"来源数据缺少样本: {', '.join(missing)}")

    base_config = load_json(source_manifest["base_config"])
    carla_root = os.path.abspath(args.carla_root)
    scene_runner = os.path.join(
        carla_root,
        "scenes",
        "scene_04_parameterized.py",
    )
    runtime_output_root = os.path.abspath(
        args.runtime_output_root
        or os.path.join(
            DEFAULT_RUNTIME_OUTPUT_BASE,
            "model_generated_validation",
            os.path.basename(output_dir),
        )
    )

    runs = {}
    for sample_id in sample_ids:
        record = records_by_id[sample_id]
        source_row = source_rows[sample_id]
        for repeat_round, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
            run_id = (
                f"{sample_id}__tm_{traffic_seed}__route_"
                f"{args.experiment_version}"
            )
            config = compile_carla_config(copy.deepcopy(record), base_config)
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            apply_regression_profile(config, control_profile)
            config["output"]["root"] = runtime_output_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            runs[(sample_id, traffic_seed)] = {
                "run_id": run_id,
                "sample_id": sample_id,
                "target_risk_level": source_row["target_risk_level"],
                "source_block_index": int(source_row["block_index"]),
                "repeat_round": repeat_round,
                "traffic_manager_seed": traffic_seed,
                "source": (
                    "waypoint_controlled_repeatability_"
                    f"{args.experiment_version}"
                ),
                "planned": True,
                "run_order": None,
                "part_index": None,
                "config_path": config_path,
                "expected_run_root": os.path.join(runtime_output_root, run_id),
            }

    generator = np.random.default_rng(args.run_seed)
    planned_rows = []
    part_paths = []
    if args.sample_set == "representative3":
        part_rows = [
            [
                runs[(sample_id, TRAFFIC_SEEDS[(part_index + index) % 3])]
                for index, sample_id in enumerate(sample_ids)
            ]
            for part_index in range(3)
        ]
        design = {
            "type": "balanced_cross_schedule",
            "part_count": 3,
            "runs_per_part": 3,
            "description": (
                "三批平衡交叉安排，每批包含低、中、高代表场景各 1 条"
            ),
        }
    else:
        sample_ids_by_level = {
            level: sorted(
                [
                    sample_id
                    for sample_id in sample_ids
                    if source_rows[sample_id]["target_risk_level"] == level
                ],
                key=lambda sample_id: int(
                    source_rows[sample_id]["block_index"]
                ),
            )
            for level in RISK_LEVELS
        }
        block_templates = [
            (sample_offset, seed_offset)
            for sample_offset in range(3)
            for seed_offset in range(3)
        ]
        generator.shuffle(block_templates)
        part_rows = []
        for sample_offset, seed_offset in block_templates:
            rows = []
            for level_index, level in enumerate(RISK_LEVELS):
                level_sample_ids = sample_ids_by_level[level]
                sample_id = level_sample_ids[
                    (sample_offset + level_index) % 3
                ]
                traffic_seed = TRAFFIC_SEEDS[
                    (seed_offset + level_index) % 3
                ]
                rows.append(runs[(sample_id, traffic_seed)])
            part_rows.append(rows)
        design = {
            "type": "randomized_latin_block",
            "blocking_factor": "run_part",
            "part_count": 9,
            "runs_per_part": 4,
            "description": (
                "九个拉丁式随机区组，每组包含四个风险档各 1 次，"
                "种子重复位置在区组间轮换"
            ),
        }
    for part_index, rows in enumerate(part_rows, 1):
        generator.shuffle(rows)
        for row in rows:
            row["part_index"] = part_index
            row["run_order"] = len(planned_rows) + 1
            planned_rows.append(row)
        part_path = os.path.join(output_dir, f"run_part_{part_index:02d}.cmd")
        write_run_script(part_path, carla_root, scene_runner, rows)
        part_paths.append(part_path)

    run_all_path = os.path.join(output_dir, "run_all.cmd")
    write_run_all(run_all_path, part_paths)
    manifest_path = os.path.join(output_dir, "manifest.json")
    route_profile = control_profile["route"]
    manifest = {
        "format": (
            "cvae_carla_route_repeatability_"
            f"{args.experiment_version}"
        ),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "experiment_version": args.experiment_version,
        "sample_set": args.sample_set,
        "source_validation_manifest": source_manifest_path,
        "source_records": records_path,
        "base_config": source_manifest["base_config"],
        "control_profile_id": control_profile["profile_id"],
        "control_profile_path": control_profile_path,
        "control_profile_sha256": file_sha256(control_profile_path),
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_output_root,
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "sample_ids": list(sample_ids),
        "run_seed": args.run_seed,
        "route_lock_required": True,
        "controller_mode": route_profile["route_control_mode"],
        "acceptance_requirements": copy.deepcopy(
            control_profile["acceptance_requirements"]
        ),
        "route_control": {
            **copy.deepcopy(route_profile),
            "route_controller": copy.deepcopy(control_profile["controller"]),
        },
        "design": design,
        "scenario_count": len(sample_ids),
        "existing_run_count": 0,
        "planned_run_count": len(planned_rows),
        "total_run_count": len(planned_rows),
        "runs": sorted(
            planned_rows,
            key=lambda row: (row["sample_id"], row["traffic_manager_seed"]),
        ),
    }
    write_json(manifest_path, manifest)
    write_collect_script(os.path.join(output_dir, "collect_results.cmd"))

    csv_path = os.path.join(output_dir, "run_schedule.csv")
    fields = (
        "run_order",
        "part_index",
        "repeat_round",
        "source_block_index",
        "run_id",
        "sample_id",
        "target_risk_level",
        "traffic_manager_seed",
        "source",
        "config_path",
        "expected_run_root",
    )
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field) for field in fields}
            for row in planned_rows
        )
    write_readme(
        os.path.join(output_dir, "README.md"),
        manifest,
        part_paths,
    )
    print(f"[PREPARE] 固定场景: {manifest['scenario_count']}")
    print(f"[PREPARE] 新增运行: {manifest['planned_run_count']}")
    print(f"[PREPARE] 分批脚本: {len(part_paths)}")
    print(f"[PREPARE] 目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
