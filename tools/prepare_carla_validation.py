"""为生成模型样本准备可复现的 CARLA 抽样验证集。"""

import argparse
import copy
import csv
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

from core.scenario_features import (  # noqa: E402
    RISK_LEVELS,
    encode_record,
    load_jsonl,
)
from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    load_json,
    require_valid_scenario,
)


DEFAULT_INPUTS = [
    os.path.join(
        PROJECT_ROOT,
        "artifacts",
        "final_evaluation",
        f"cvae_{level}.jsonl",
    )
    for level in RISK_LEVELS
]
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "cvae_validation_v1",
)
DEFAULT_BASE_CONFIG = os.path.join(
    PROJECT_ROOT,
    "configs",
    "multi_hazard_rainy_night.json",
)
DEFAULT_SCENE_RUNNER = os.path.join(
    PROJECT_ROOT,
    "scenes",
    "scene_04_parameterized.py",
)
DEFAULT_CARLA_ROOT = r"F:\Carla\test"


def parse_args():
    parser = argparse.ArgumentParser(
        description="从生成模型结果中抽样并编译 CARLA 验证配置"
    )
    parser.add_argument("inputs", nargs="*", default=DEFAULT_INPUTS)
    parser.add_argument("--per-level", type=int, default=1)
    parser.add_argument(
        "--selection",
        choices=("spread", "centroid", "first"),
        default="centroid",
        help="spread 沿同档样本主要变化方向选择分散代表样本",
    )
    parser.add_argument(
        "--exclude-records",
        action="append",
        default=[],
        help="排除已验证记录，可重复指定 JSONL 文件",
    )
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--carla-root", default=DEFAULT_CARLA_ROOT)
    parser.add_argument(
        "--runtime-output-root",
        help="CARLA 运行输出根目录；默认按验证集目录名分组",
    )
    parser.add_argument("--scene-runner", default=DEFAULT_SCENE_RUNNER)
    parser.add_argument(
        "--sensor-profile",
        choices=("lightweight", "full"),
        default="lightweight",
    )
    parser.add_argument("--run-seed", type=int, default=20260813)
    parser.add_argument("--traffic-seed-base", type=int, default=20260821)
    parser.add_argument("--runs-per-script", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def excluded_sample_ids(paths):
    sample_ids = set()
    for path in paths:
        for record in load_jsonl(os.path.abspath(path)):
            sample_ids.add(record["sample_id"])
    return sample_ids


def records_by_level(paths, excluded_ids=None):
    grouped = {level: [] for level in RISK_LEVELS}
    seen_ids = set()
    excluded_ids = excluded_ids or set()
    for path in paths:
        absolute_path = os.path.abspath(path)
        for record in load_jsonl(absolute_path):
            require_valid_scenario(record)
            sample_id = record["sample_id"]
            if sample_id in seen_ids:
                raise ValueError(f"样本编号重复: {sample_id}")
            seen_ids.add(sample_id)
            if sample_id in excluded_ids:
                continue
            grouped[record["conditions"]["target_risk_level"]].append(record)
    return grouped


def select_records(records, count, method):
    if len(records) < count:
        raise ValueError(f"可用样本仅 {len(records)} 条，无法抽取 {count} 条")
    if method == "first":
        return records[:count]

    values = np.asarray([encode_record(record) for record in records])
    centroid = np.mean(values, axis=0)
    if method == "spread":
        centered = values - centroid
        _, _, axes = np.linalg.svd(centered, full_matrices=False)
        scores = centered @ axes[0]
        quantiles = np.linspace(0.1, 0.9, count)
        targets = np.quantile(scores, quantiles)
        available = set(range(len(records)))
        selected_indices = []
        for target in targets:
            selected_index = min(
                available,
                key=lambda index: (
                    abs(float(scores[index] - target)),
                    records[index]["sample_id"],
                ),
            )
            selected_indices.append(selected_index)
            available.remove(selected_index)
        return [records[index] for index in selected_indices]

    distances = np.linalg.norm(values - centroid, axis=1)
    order = sorted(
        range(len(records)),
        key=lambda index: (float(distances[index]), records[index]["sample_id"]),
    )
    return [records[index] for index in order[:count]]


def apply_sensor_profile(config, profile):
    if profile == "full":
        return config
    camera = config["sensors"]["camera"]
    camera.update(
        {
            "width": 640,
            "height": 360,
            "sensor_tick": 0.2,
            "writer_workers": 1,
            "writer_queue_size": 8,
        }
    )
    config["sensors"]["rgb"]["enabled"] = True
    config["sensors"]["depth"]["enabled"] = False
    config["sensors"]["semantic"]["enabled"] = False
    return config


def relative_to_output(path, output_dir):
    return os.path.relpath(path, output_dir).replace("\\", "/")


def write_run_script(path, carla_root, scene_runner, config_paths):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        f'cd /d "{carla_root}"',
        "",
    ]
    for index, (sample_id, config_path) in enumerate(config_paths, 1):
        lines.extend(
            [
                f"echo [RUN {index}/{len(config_paths)}] {sample_id}",
                f'python -u "{scene_runner}" --config "{config_path}"',
                "if errorlevel 1 goto :failed",
                "timeout /t 5 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] CARLA sample validation completed.",
            "exit /b 0",
            "",
            ":failed",
            "echo [FAILED] Stop after CARLA or Python error.",
            "exit /b 1",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as file:
        file.write("\n".join(lines))


def blocked_run_order(selected_by_level, seed):
    generator = np.random.default_rng(seed)
    schedule = []
    rounds = max(len(records) for records in selected_by_level.values())
    for round_index in range(rounds):
        block = [
            selected_by_level[level][round_index]
            for level in RISK_LEVELS
            if round_index < len(selected_by_level[level])
        ]
        generator.shuffle(block)
        schedule.extend(block)
    return schedule


def write_batch_scripts(
    output_dir,
    carla_root,
    scene_runner,
    command_configs,
    runs_per_script,
):
    part_paths = []
    for start in range(0, len(command_configs), runs_per_script):
        part = command_configs[start : start + runs_per_script]
        part_path = os.path.join(
            output_dir,
            f"run_part_{len(part_paths) + 1:02d}.cmd",
        )
        write_run_script(part_path, carla_root, scene_runner, part)
        part_paths.append(part_path)

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
                f'call "{part_path}"',
                "if errorlevel 1 exit /b 1",
                "timeout /t 10 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] All validation batches completed.",
            "exit /b 0",
            "",
        ]
    )
    run_all_path = os.path.join(output_dir, "run_all.cmd")
    with open(run_all_path, "w", encoding="utf-8-sig", newline="\r\n") as file:
        file.write("\n".join(lines))
    return run_all_path, part_paths


def write_readme(path, manifest_path, run_script_path, part_paths):
    lines = [
        "# CVAE CARLA 抽样验证集",
        "",
        "该目录用于验证生成模型参数能否在 CARLA 中成功运行，并回填实测风险。",
        "`target_risk_level` 是生成条件，`observed_risk` 才是 CARLA 实测结果。",
        "",
        "## 执行顺序",
        "",
        f"1. 启动 CARLAUE4。",
        "2. 推荐依次运行下列分批脚本，每批完成后观察 CARLA 是否稳定：",
        *[f"   - `{os.path.basename(part_path)}`" for part_path in part_paths],
        f"   也可以一次运行 `{os.path.basename(run_script_path)}`。",
        "3. 全部场景运行后执行：",
        "",
        "```cmd",
        "cd /d D:\\Xx\\竞赛\\大创实施ing",
        "D:\\Anaconda\\envs\\Carla666\\python.exe "
        "tools\\collect_carla_validation.py "
        f"--manifest \"{manifest_path}\"",
        "```",
        "",
        "`run_all.cmd` 使用当前系统 `python`，该解释器必须已安装 CARLA Python API；",
        "结果回填使用 `Carla666`，避免与 CARLA 运行环境混用。",
        "",
        "每一批包含低、中、高、临界四档各 1 条，并共享同一个 Traffic Manager 种子；",
        "批内顺序固定随机化，用于控制交通随机性和连续运行顺序的干扰。",
        "",
        "轻量传感器配置仅保留 640×360 RGB 与碰撞传感器，降低本机负载；",
        "风险评分仍来自车辆、前车、行人遥测和天气参数。",
        "",
    ]
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def main():
    args = parse_args()
    if args.per_level <= 0:
        raise ValueError("--per-level 必须大于 0")
    if args.runs_per_script <= 0:
        raise ValueError("--runs-per-script 必须大于 0")

    output_dir = os.path.abspath(args.output_dir)
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(
                f"输出目录非空: {output_dir}，如需覆盖请加 --force"
            )
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    config_dir = os.path.join(output_dir, "configs")
    os.makedirs(config_dir, exist_ok=True)

    base_config_path = os.path.abspath(args.base_config)
    base_config = load_json(base_config_path)
    carla_root = os.path.abspath(args.carla_root)
    runtime_output_root = os.path.abspath(
        args.runtime_output_root
        or os.path.join(
            carla_root,
            "output",
            "model_generated_validation",
            os.path.basename(output_dir),
        )
    )
    scene_runner = os.path.abspath(args.scene_runner)

    excluded_ids = excluded_sample_ids(args.exclude_records)
    grouped = records_by_level(args.inputs, excluded_ids=excluded_ids)
    selected = []
    selected_by_level = {}
    for level in RISK_LEVELS:
        selected_by_level[level] = []
        for block_index, source_record in enumerate(
            select_records(grouped[level], args.per_level, args.selection),
            1,
        ):
            record = copy.deepcopy(source_record)
            record["scenario"]["traffic_manager_seed"] = (
                args.traffic_seed_base + block_index - 1
            )
            selected_by_level[level].append(record)
        selected.extend(selected_by_level[level])

    records_path = os.path.join(output_dir, "selected_records.jsonl")
    write_jsonl(records_path, selected)
    manifest_rows = []
    config_paths_by_id = {}
    for record in selected:
        sample_id = record["sample_id"]
        config = compile_carla_config(record, base_config)
        config = apply_sensor_profile(config, args.sensor_profile)
        config["output"]["root"] = runtime_output_root
        config_path = os.path.join(config_dir, f"{sample_id}.json")
        write_json(config_path, config)
        config_paths_by_id[sample_id] = config_path
        manifest_rows.append(
            {
                "sample_id": sample_id,
                "target_risk_level": record["conditions"]["target_risk_level"],
                "block_index": selected_by_level[
                    record["conditions"]["target_risk_level"]
                ].index(record)
                + 1,
                "traffic_manager_seed": record["scenario"][
                    "traffic_manager_seed"
                ],
                "config_path": relative_to_output(config_path, output_dir),
                "expected_run_root": os.path.join(runtime_output_root, sample_id),
            }
        )

    run_schedule = blocked_run_order(selected_by_level, args.run_seed)
    command_configs = [
        (record["sample_id"], config_paths_by_id[record["sample_id"]])
        for record in run_schedule
    ]
    schedule_position = {
        record["sample_id"]: index
        for index, record in enumerate(run_schedule, 1)
    }
    for row in manifest_rows:
        row["run_order"] = schedule_position[row["sample_id"]]

    manifest_path = os.path.join(output_dir, "manifest.json")
    manifest = {
        "format": "cvae_carla_validation_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_inputs": [os.path.abspath(path) for path in args.inputs],
        "selection": args.selection,
        "excluded_records": [os.path.abspath(path) for path in args.exclude_records],
        "excluded_sample_count": len(excluded_ids),
        "per_level": args.per_level,
        "run_seed": args.run_seed,
        "traffic_seed_base": args.traffic_seed_base,
        "runs_per_script": args.runs_per_script,
        "sensor_profile": args.sensor_profile,
        "base_config": base_config_path,
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_output_root,
        "selected_records": relative_to_output(records_path, output_dir),
        "records": manifest_rows,
    }
    write_json(manifest_path, manifest)

    csv_path = os.path.join(output_dir, "selection_summary.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "run_order",
                "block_index",
                "sample_id",
                "target_risk_level",
                "traffic_manager_seed",
                "config_path",
            ),
        )
        writer.writeheader()
        writer.writerows(
            {
                key: row[key]
                for key in (
                    "run_order",
                    "block_index",
                    "sample_id",
                    "target_risk_level",
                    "traffic_manager_seed",
                    "config_path",
                )
            }
            for row in sorted(manifest_rows, key=lambda item: item["run_order"])
        )

    run_script_path, part_paths = write_batch_scripts(
        output_dir,
        carla_root,
        scene_runner,
        command_configs,
        args.runs_per_script,
    )
    write_readme(
        os.path.join(output_dir, "README.md"),
        manifest_path,
        run_script_path,
        part_paths,
    )
    print(f"[PREPARE] 样本数: {len(selected)}")
    print(f"[PREPARE] 目录: {output_dir}")
    print(f"[PREPARE] 运行脚本: {run_script_path}")
    print(
        "[PREPARE] 结果回填: "
        "D:\\Anaconda\\envs\\Carla666\\python.exe "
        "tools\\collect_carla_validation.py "
        f'--manifest "{manifest_path}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
