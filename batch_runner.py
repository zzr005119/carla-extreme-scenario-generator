# -*- coding: utf-8 -*-
"""顺序运行多个 CARLA 配置，并汇总风险评估结果。"""

import argparse
import copy
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

from core.batch_statistics import AGGREGATE_FIELDS, aggregate_variant_rows


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCENE_RUNNER = os.path.join(
    PROJECT_ROOT,
    "scenes",
    "scene_04_parameterized.py",
)
DEFAULT_BATCH_CONFIG = os.path.join(
    PROJECT_ROOT,
    "configs",
    "batch_rainy_night_variants.json",
)
SUMMARY_FIELDS = [
    "variant",
    "repeat_index",
    "repeat_count",
    "run_order",
    "traffic_manager_seed",
    "status",
    "exit_code",
    "run_dir",
    "collision_count",
    "minimum_ttc_seconds",
    "minimum_lead_gap_m",
    "minimum_pedestrian_distance_m",
    "risk_score",
    "risk_level",
    "sensor_pipeline_status",
    "sensor_frames_complete",
    "server_health_status",
    "rgb_frames",
    "depth_frames",
    "semantic_frames",
    "total_frames",
    "error",
]


def parse_args():
    parser = argparse.ArgumentParser(description="批量运行 CARLA 极端场景变体")
    parser.add_argument(
        "--config",
        default=DEFAULT_BATCH_CONFIG,
        help="批量 JSON 配置文件路径",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅校验所有变体，不启动 CARLA",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只运行前 N 个变体，用于冒烟测试",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="覆盖配置中的重复次数",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def safe_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name)).strip("_")
    if not cleaned:
        raise ValueError("变体名称不能为空")
    return cleaned


def set_dotted_value(config, dotted_key, value):
    parts = dotted_key.split(".")
    target = config
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            raise KeyError(f"覆盖路径不存在: {dotted_key}")
        target = target[part]
    if parts[-1] not in target:
        raise KeyError(f"覆盖字段不存在: {dotted_key}")
    target[parts[-1]] = value


def resolve_path(base_dir, path):
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(base_dir, path))


def load_batch_definition(batch_path):
    batch_path = os.path.abspath(batch_path)
    batch_config = load_json(batch_path)
    if not batch_config.get("batch_name"):
        raise ValueError("batch_name 不能为空")
    variants = batch_config.get("variants")
    if not variants:
        raise ValueError("variants 不能为空")
    variant_names = [safe_name(variant["name"]) for variant in variants]
    if len(set(variant_names)) != len(variant_names):
        raise ValueError("变体名称不能重复")
    repeat_count = int(batch_config.get("repeat_count", 3))
    if repeat_count <= 0:
        raise ValueError("repeat_count 必须大于 0")
    seed_stride = int(batch_config.get("seed_stride", 1))
    if seed_stride < 0:
        raise ValueError("seed_stride 不能小于 0")

    base_path = resolve_path(
        os.path.dirname(batch_path),
        batch_config["base_config"],
    )
    base_config = load_json(base_path)
    return batch_path, batch_config, base_path, base_config


def build_variant_config(base_config, variant, base_config_path):
    variant_name = safe_name(variant["name"])
    config = copy.deepcopy(base_config)
    for dotted_key, value in variant.get("overrides", {}).items():
        set_dotted_value(config, dotted_key, value)

    base_name = safe_name(config["scenario"]["name"])
    config["scenario"]["name"] = f"{base_name}__{variant_name}"
    output_root = config["output"]["root"]
    if not os.path.isabs(output_root):
        output_root = resolve_path(os.path.dirname(base_config_path), output_root)
    config["output"]["root"] = output_root
    return variant_name, config


def build_run_config(variant_config, repeat_index, seed_stride):
    config = copy.deepcopy(variant_config)
    base_seed = int(config["scenario"].get("traffic_manager_seed", 0))
    run_seed = base_seed + (repeat_index - 1) * seed_stride
    config["scenario"]["traffic_manager_seed"] = run_seed
    return run_seed, config


def build_run_schedule(variants, repeat_count):
    schedule = []
    variant_count = len(variants)
    for repeat_index in range(1, repeat_count + 1):
        rotation = (repeat_index - 1) % variant_count
        ordered_variants = variants[rotation:] + variants[:rotation]
        for variant in ordered_variants:
            schedule.append(
                {
                    "variant": variant,
                    "repeat_index": repeat_index,
                }
            )
    return schedule


def validate_scene_config(config, scene_runner):
    with tempfile.TemporaryDirectory(prefix="carla_config_") as temp_dir:
        temp_config = os.path.join(temp_dir, "variant.json")
        with open(temp_config, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, scene_runner, "--config", temp_config, "--validate-only"],
            cwd=os.path.dirname(scene_runner),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def create_batch_run_dir(output_root, batch_name):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_root = os.path.join(output_root, "batches", safe_name(batch_name))
    run_dir = os.path.join(batch_root, timestamp)
    suffix = 1
    unique_dir = run_dir
    while os.path.exists(unique_dir):
        unique_dir = f"{run_dir}_{suffix:02d}"
        suffix += 1
    os.makedirs(os.path.join(unique_dir, "generated_configs"), exist_ok=False)
    os.makedirs(os.path.join(unique_dir, "logs"), exist_ok=True)
    return unique_dir


def write_summary(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def write_aggregate_summary(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=AGGREGATE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: row.get(field, "") for field in AGGREGATE_FIELDS}
            )


def summarize_result(variant_name, process_returncode, output_dir, metadata):
    result = metadata.get("result", {}) if metadata else {}
    risk = result.get("risk_evaluation") or {}
    frames = metadata.get("frames", {}) if metadata else {}
    sensor_pipeline = metadata.get("sensor_pipeline", {}) if metadata else {}
    sensor_status = sensor_pipeline.get("status", "")
    server_health = metadata.get("server_health", {}) if metadata else {}
    server_health_status = server_health.get("status", "")
    error = result.get("error", "")
    cleanup = metadata.get("cleanup", {}) if metadata else {}
    status = result.get("status", "failed")
    if process_returncode != 0 or (
        cleanup and cleanup.get("status") != "completed"
    ):
        status = "failed"
    if sensor_pipeline and sensor_status != "completed":
        status = "failed"
        if not error:
            error = f"传感器写盘状态: {sensor_status or 'unknown'}"
    if server_health and server_health_status != "healthy":
        status = "failed"
        if not error:
            error = f"CARLA 服务状态: {server_health_status or 'unknown'}"
    if process_returncode != 0 and not error:
        error = f"场景进程退出码: {process_returncode}"
    return {
        "variant": variant_name,
        "status": status,
        "exit_code": process_returncode,
        "run_dir": output_dir or "",
        "collision_count": result.get("collision_count", ""),
        "minimum_ttc_seconds": result.get("minimum_ttc_seconds", ""),
        "minimum_lead_gap_m": result.get("minimum_lead_gap_m", ""),
        "minimum_pedestrian_distance_m": result.get(
            "minimum_pedestrian_distance_m",
            "",
        ),
        "risk_score": risk.get("score", ""),
        "risk_level": risk.get("level", ""),
        "sensor_pipeline_status": sensor_status,
        "sensor_frames_complete": sensor_status == "completed",
        "server_health_status": server_health_status,
        "rgb_frames": frames.get("rgb", 0),
        "depth_frames": frames.get("depth", 0),
        "semantic_frames": frames.get("semantic", 0),
        "total_frames": sum(frames.values()) if frames else 0,
        "error": error,
    }


def run_batch(
    batch_path,
    batch_config,
    base_config_path,
    base_config,
    repeat_count,
    limit=None,
):
    batch_started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    variants = batch_config["variants"]
    if limit is not None:
        if limit <= 0:
            raise ValueError("--limit 必须大于 0")
        variants = variants[:limit]
    seed_stride = int(batch_config.get("seed_stride", 1))
    schedule = build_run_schedule(variants, repeat_count)
    variant_names = [safe_name(variant["name"]) for variant in variants]

    _, first_config = build_variant_config(
        base_config,
        variants[0],
        base_config_path,
    )
    output_root = first_config["output"]["root"]
    batch_run_dir = create_batch_run_dir(output_root, batch_config["batch_name"])
    generated_dir = os.path.join(batch_run_dir, "generated_configs")
    logs_dir = os.path.join(batch_run_dir, "logs")
    summary_path = os.path.join(batch_run_dir, "batch_summary.csv")
    aggregate_summary_path = os.path.join(
        batch_run_dir,
        "aggregate_summary.csv",
    )
    schedule_path = os.path.join(batch_run_dir, "run_schedule.json")
    rows = []

    prepared_runs = []
    for run_order, schedule_item in enumerate(schedule, start=1):
        variant_name, variant_config = build_variant_config(
            base_config,
            schedule_item["variant"],
            base_config_path,
        )
        repeat_index = schedule_item["repeat_index"]
        run_seed, run_config = build_run_config(
            variant_config,
            repeat_index,
            seed_stride,
        )
        file_stem = (
            f"{variant_name}_repeat_{repeat_index:02d}_seed_{run_seed}"
        )
        config_path = os.path.join(generated_dir, f"{file_stem}.json")
        log_path = os.path.join(logs_dir, f"{file_stem}.log")
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(run_config, file, ensure_ascii=False, indent=2)
        prepared_runs.append(
            {
                "run_order": run_order,
                "variant_name": variant_name,
                "repeat_index": repeat_index,
                "traffic_manager_seed": run_seed,
                "config_path": config_path,
                "log_path": log_path,
            }
        )

    with open(schedule_path, "w", encoding="utf-8") as file:
        json.dump(prepared_runs, file, ensure_ascii=False, indent=2)

    print(f"[BATCH] 运行目录: {batch_run_dir}")
    print(
        f"[BATCH] {len(variants)} 个变体 × {repeat_count} 次 = "
        f"{len(prepared_runs)} 次运行"
    )
    for prepared_run in prepared_runs:
        index = prepared_run["run_order"]
        variant_name = prepared_run["variant_name"]
        repeat_index = prepared_run["repeat_index"]
        run_seed = prepared_run["traffic_manager_seed"]
        config_path = prepared_run["config_path"]
        log_path = prepared_run["log_path"]
        log_prefix = f"{variant_name} R{repeat_index}/{repeat_count}"

        print(
            f"[BATCH {index}/{len(prepared_runs)}] 开始: "
            f"{variant_name} | 重复 {repeat_index}/{repeat_count} | "
            f"种子 {run_seed}"
        )
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        output_dir = None
        lines = []
        process = subprocess.Popen(
            [sys.executable, "-u", SCENE_RUNNER, "--config", config_path],
            cwd=os.path.dirname(SCENE_RUNNER),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
        for line in process.stdout:
            lines.append(line)
            print(f"[{log_prefix}] {line}", end="")
            if line.startswith("[OUTPUT]") and ": " in line:
                output_dir = line.strip().split(": ", 1)[1]
        process.wait()
        with open(log_path, "w", encoding="utf-8") as file:
            file.writelines(lines)

        metadata = None
        if output_dir:
            metadata_path = os.path.join(output_dir, "metadata.json")
            if os.path.isfile(metadata_path):
                metadata = load_json(metadata_path)
        row = summarize_result(variant_name, process.returncode, output_dir, metadata)
        row.update(
            {
                "repeat_index": repeat_index,
                "repeat_count": repeat_count,
                "run_order": index,
                "traffic_manager_seed": run_seed,
            }
        )
        rows.append(row)
        write_summary(summary_path, rows)
        aggregates = aggregate_variant_rows(
            variant_names,
            rows,
            repeat_count,
        )
        write_aggregate_summary(aggregate_summary_path, aggregates)
        print(
            f"[BATCH {index}/{len(prepared_runs)}] 结束: "
            f"{row['status']} / 风险={row['risk_level'] or 'unknown'} / "
            f"传感器={row['sensor_pipeline_status'] or 'unknown'} / "
            f"服务={row['server_health_status'] or 'unknown'}"
        )

        if row["status"] != "completed" and not batch_config.get(
            "continue_on_error",
            True,
        ):
            break

    aggregates = aggregate_variant_rows(
        variant_names,
        rows,
        repeat_count,
    )
    write_aggregate_summary(aggregate_summary_path, aggregates)

    batch_metadata = {
        "batch_name": batch_config["batch_name"],
        "source_batch_config": batch_path,
        "started_at": batch_started_at,
        "variant_count": len(variants),
        "repeat_count": repeat_count,
        "seed_stride": seed_stride,
        "planned_run_count": len(prepared_runs),
        "attempted_run_count": len(rows),
        "unattempted_run_count": len(prepared_runs) - len(rows),
        "completed_count": sum(row["status"] == "completed" for row in rows),
        "failed_count": sum(row["status"] != "completed" for row in rows),
        "summary_path": summary_path,
        "aggregate_summary_path": aggregate_summary_path,
        "schedule_path": schedule_path,
        "runs": rows,
        "aggregates": aggregates,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with open(
        os.path.join(batch_run_dir, "batch_metadata.json"),
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(batch_metadata, file, ensure_ascii=False, indent=2)

    print(f"[BATCH] 汇总: {summary_path}")
    print(f"[BATCH] 统计: {aggregate_summary_path}")
    all_runs_attempted = len(rows) == len(prepared_runs)
    return 0 if batch_metadata["failed_count"] == 0 and all_runs_attempted else 1


def main():
    args = parse_args()
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")
    if args.repeat is not None and args.repeat <= 0:
        raise ValueError("--repeat 必须大于 0")
    batch_path = os.path.abspath(args.config)
    batch_path, batch_config, base_path, base_config = load_batch_definition(batch_path)
    if not os.path.isfile(SCENE_RUNNER):
        raise FileNotFoundError(f"找不到场景运行器: {SCENE_RUNNER}")

    variants = batch_config["variants"]
    if args.limit is not None:
        variants = variants[:args.limit]
    for variant in variants:
        variant_name, variant_config = build_variant_config(
            base_config,
            variant,
            base_path,
        )
        validate_scene_config(variant_config, SCENE_RUNNER)
        print(f"[VALID] {variant_name}")

    repeat_count = (
        args.repeat
        if args.repeat is not None
        else int(batch_config.get("repeat_count", 3))
    )

    if args.validate_only:
        print(
            f"[BATCH] 配置校验通过，共 {len(variants)} 个变体 × "
            f"{repeat_count} 次 = {len(variants) * repeat_count} 次运行"
        )
        return 0

    return run_batch(
        batch_path,
        batch_config,
        base_path,
        base_config,
        repeat_count,
        args.limit,
    )


if __name__ == "__main__":
    sys.exit(main())
