"""为 CVAE 第二轮样本准备多 Traffic Manager 种子复测。"""

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

from core.scenario_features import RISK_LEVELS, load_jsonl  # noqa: E402
from core.scenario_validator import compile_carla_config, load_json  # noqa: E402


DEFAULT_SOURCE_MANIFEST = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "cvae_validation_v2",
    "manifest.json",
)
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "cvae_repeatability_v1",
)
DEFAULT_CARLA_ROOT = r"F:\Carla\test"


def parse_seeds(value):
    seeds = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise argparse.ArgumentTypeError("交通种子至少两个且不能重复")
    if any(seed < 0 for seed in seeds):
        raise argparse.ArgumentTypeError("交通种子不能小于 0")
    return seeds


def parse_args():
    parser = argparse.ArgumentParser(description="准备 CVAE 场景多种子复测")
    parser.add_argument("--source-manifest", default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--carla-root", default=DEFAULT_CARLA_ROOT)
    parser.add_argument(
        "--traffic-seeds",
        type=parse_seeds,
        default=(20260821, 20260822, 20260823),
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


def apply_lightweight_profile(config):
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
        lines.extend(
            [
                f"echo [RUN {index}/{len(rows)}] {row['run_id']}",
                f'python -u "{scene_runner}" --config "{row["config_path"]}"',
                "if errorlevel 1 goto :failed",
                "timeout /t 5 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] Repeatability batch completed.",
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
                f'call "{part_path}"',
                "if errorlevel 1 exit /b 1",
                "timeout /t 10 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] All repeatability batches completed.",
            "exit /b 0",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as file:
        file.write("\n".join(lines))


def write_readme(path, manifest_path, part_paths):
    lines = [
        "# CVAE CARLA 多种子重复性验证 V1",
        "",
        "该实验将第二轮的 12 个固定场景分别运行 3 个 Traffic Manager 种子。",
        "第二轮已有 12 次结果，因此本目录只新增缺失的 24 次运行。",
        "",
        "## 实验设计",
        "",
        "- 12 个场景 × 3 个交通种子 = 36 次完整结果。",
        "- 已有结果：12 次；本轮新增：24 次。",
        "- 每批 4 次，包含低、中、高、临界目标各 1 条。",
        "- 同一场景的参数保持不变，只改变 Traffic Manager 种子。",
        "",
        "## 执行",
        "",
        "启动 CARLAUE4 后，建议依次运行：",
        "",
        *[f"- `{os.path.basename(part_path)}`" for part_path in part_paths],
        "",
        "全部运行完成后执行：",
        "",
        "```cmd",
        "cd /d D:\\Xx\\竞赛\\大创实施ing",
        "D:\\Anaconda\\envs\\Carla666\\python.exe "
        "tools\\collect_carla_repeatability.py "
        f'--manifest "{manifest_path}"',
        "```",
        "",
        "若某批失败，只需重新运行对应的 `run_part_XX.cmd`。",
        "",
    ]
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def main():
    args = parse_args()
    source_manifest_path = os.path.abspath(args.source_manifest)
    source_manifest_dir = os.path.dirname(source_manifest_path)
    source_manifest = load_json(source_manifest_path)
    if source_manifest.get("format") != "cvae_carla_validation_v1":
        raise ValueError("来源清单不是支持的 CVAE 验证清单")

    output_dir = os.path.abspath(args.output_dir)
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
    records = load_jsonl(records_path)
    records_by_id = {record["sample_id"]: record for record in records}
    source_rows = {row["sample_id"]: row for row in source_manifest["records"]}
    if set(records_by_id) != set(source_rows):
        raise ValueError("来源记录与来源清单的 sample_id 不一致")

    base_config = load_json(source_manifest["base_config"])
    scene_runner = source_manifest["scene_runner"]
    carla_root = os.path.abspath(args.carla_root)
    runtime_output_root = os.path.join(
        carla_root,
        "output",
        "model_generated_validation",
        os.path.basename(output_dir),
    )

    all_runs = []
    planned_by_round_block = {}
    for sample_id, source_row in source_rows.items():
        record = records_by_id[sample_id]
        original_seed = int(source_row["traffic_manager_seed"])
        if original_seed not in args.traffic_seeds:
            raise ValueError(f"{sample_id} 的原始交通种子不在复测种子集合中")
        original_run_id = f"{sample_id}__tm_{original_seed}"
        all_runs.append(
            {
                "run_id": original_run_id,
                "sample_id": sample_id,
                "target_risk_level": source_row["target_risk_level"],
                "source_block_index": int(source_row["block_index"]),
                "repeat_round": 0,
                "traffic_manager_seed": original_seed,
                "source": "existing_validation_v2",
                "planned": False,
                "run_order": None,
                "part_index": None,
                "config_path": resolve_path(
                    source_manifest_dir,
                    source_row["config_path"],
                ),
                "expected_run_root": source_row["expected_run_root"],
            }
        )

        original_index = args.traffic_seeds.index(original_seed)
        missing_seeds = (
            args.traffic_seeds[(original_index + 1) % len(args.traffic_seeds)],
            args.traffic_seeds[(original_index + 2) % len(args.traffic_seeds)],
        )
        for repeat_round, traffic_seed in enumerate(missing_seeds, 1):
            run_id = f"{sample_id}__tm_{traffic_seed}"
            config = compile_carla_config(copy.deepcopy(record), base_config)
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            apply_lightweight_profile(config)
            config["output"]["root"] = runtime_output_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            row = {
                "run_id": run_id,
                "sample_id": sample_id,
                "target_risk_level": source_row["target_risk_level"],
                "source_block_index": int(source_row["block_index"]),
                "repeat_round": repeat_round,
                "traffic_manager_seed": traffic_seed,
                "source": "planned_repeatability_v1",
                "planned": True,
                "run_order": None,
                "part_index": None,
                "config_path": config_path,
                "expected_run_root": os.path.join(runtime_output_root, run_id),
            }
            all_runs.append(row)
            planned_by_round_block.setdefault(
                (repeat_round, int(source_row["block_index"])),
                [],
            ).append(row)

    generator = np.random.default_rng(args.run_seed)
    planned_rows = []
    part_paths = []
    for part_index, key in enumerate(sorted(planned_by_round_block), 1):
        rows = planned_by_round_block[key]
        if {row["target_risk_level"] for row in rows} != set(RISK_LEVELS):
            raise ValueError(f"复测区组 {key} 未包含完整四个风险档")
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
    manifest = {
        "format": "cvae_carla_repeatability_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_validation_manifest": source_manifest_path,
        "source_records": records_path,
        "base_config": source_manifest["base_config"],
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_output_root,
        "traffic_seeds": list(args.traffic_seeds),
        "run_seed": args.run_seed,
        "scenario_count": len(records),
        "existing_run_count": sum(not row["planned"] for row in all_runs),
        "planned_run_count": len(planned_rows),
        "total_run_count": len(all_runs),
        "runs": sorted(
            all_runs,
            key=lambda row: (
                row["sample_id"],
                row["traffic_manager_seed"],
            ),
        ),
    }
    write_json(manifest_path, manifest)

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
        manifest_path,
        part_paths,
    )
    print(f"[PREPARE] 固定场景: {len(records)}")
    print(f"[PREPARE] 已有运行: {manifest['existing_run_count']}")
    print(f"[PREPARE] 新增运行: {manifest['planned_run_count']}")
    print(f"[PREPARE] 完整设计: {manifest['total_run_count']}")
    print(f"[PREPARE] 分批脚本: {len(part_paths)}")
    print(f"[PREPARE] 目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
