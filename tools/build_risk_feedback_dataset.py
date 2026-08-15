"""构建按独立场景聚合的 CARLA 实测风险反馈数据集。"""

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import (
    FEATURE_NAMES,
    encode_record,
    load_jsonl,
    parameter_vector,
)


DEFAULT_RUN_RESULTS = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "generator_comparison_v1",
    "run_results.csv",
)
DEFAULT_SELECTED_RECORDS = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "generator_comparison_v1",
    "selected_records.jsonl",
)
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
)
EXPECTED_REPEATS = 3
FEATURE_COLUMNS = tuple(
    f"feature_{index:02d}_{name.replace('.', '_')}"
    for index, name in enumerate(FEATURE_NAMES, 1)
)
PARAMETER_COLUMNS = tuple(
    f"parameter_{name.replace('.', '_')}" for name in FEATURE_NAMES
)


def parse_args():
    parser = argparse.ArgumentParser(description="构建风险反馈聚合数据集")
    parser.add_argument("--run-results", default=DEFAULT_RUN_RESULTS)
    parser.add_argument("--selected-records", default=DEFAULT_SELECTED_RECORDS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-repeats", type=int, default=EXPECTED_REPEATS)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def safe_float(value):
    if value in (None, ""):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def load_completed_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required_status = {
        "status": "completed",
        "acceptance_status": "completed",
        "sensor_status": "completed",
        "server_status": "healthy",
        "route_verified": "True",
    }
    rejected = []
    accepted = []
    for row in rows:
        failures = [
            key for key, expected in required_status.items() if row.get(key) != expected
        ]
        if failures:
            rejected.append({"run_id": row.get("run_id"), "failures": failures})
        else:
            accepted.append(row)
    if rejected:
        raise ValueError(f"存在未通过严格验收的运行: {rejected[:3]}")
    return accepted


def aggregate_rows(rows, records_by_id, min_repeats):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["sample_id"], []).append(row)
    if not grouped:
        raise ValueError("没有可聚合的严格验收运行")

    dataset = []
    for sample_id, repeated_rows in sorted(grouped.items()):
        record = records_by_id.get(sample_id)
        if record is None:
            raise ValueError(f"selected_records.jsonl 缺少样本: {sample_id}")
        if len(repeated_rows) < min_repeats:
            raise ValueError(
                f"样本 {sample_id} 只有 {len(repeated_rows)} 次重复测量，"
                f"少于要求的 {min_repeats} 次"
            )
        seeds = {row["traffic_manager_seed"] for row in repeated_rows}
        if len(seeds) != len(repeated_rows):
            raise ValueError(f"样本 {sample_id} 存在重复交通种子")

        target_levels = {row["target_risk_level"] for row in repeated_rows}
        generators = {row["generator"] for row in repeated_rows}
        if len(target_levels) != 1 or len(generators) != 1:
            raise ValueError(f"样本 {sample_id} 的来源条件不一致")

        scores = [float(row["risk_score"]) for row in repeated_rows]
        observed_levels = [row["observed_risk_level"] for row in repeated_rows]
        level_counts = Counter(observed_levels)
        mode_level, mode_count = level_counts.most_common(1)[0]
        parameters = encode_record(record)
        raw_parameters = [float(value) for value in parameter_vector(record)]
        normalized_parameters = [float(value) for value in parameters]
        collision_counts = [int(row["collision_count"]) for row in repeated_rows]

        item = {
            "sample_id": sample_id,
            "generator": next(iter(generators)),
            "target_risk_level": next(iter(target_levels)),
            "generator_target_cell": f"{next(iter(generators))}__{next(iter(target_levels))}",
            "repeat_count": len(repeated_rows),
            "traffic_manager_seeds": ",".join(sorted(seeds)),
            "observed_risk_score_mean": statistics.mean(scores),
            "observed_risk_score_std": statistics.stdev(scores)
            if len(scores) > 1
            else 0.0,
            "observed_risk_score_min": min(scores),
            "observed_risk_score_max": max(scores),
            "observed_risk_level_mode": mode_level,
            "observed_risk_level_consistency": mode_count / len(observed_levels),
            "collision_run_rate": sum(count > 0 for count in collision_counts)
            / len(collision_counts),
            "collision_event_total": sum(collision_counts),
            "minimum_ttc_seconds_min": min(
                float(row["minimum_ttc_seconds"]) for row in repeated_rows
            ),
            "minimum_lead_gap_m_min": min(
                float(row["minimum_lead_gap_m"]) for row in repeated_rows
            ),
            "minimum_pedestrian_distance_m_min": min(
                float(row["minimum_pedestrian_distance_m"]) for row in repeated_rows
            ),
        }
        item.update(dict(zip(PARAMETER_COLUMNS, raw_parameters)))
        item.update(dict(zip(FEATURE_COLUMNS, normalized_parameters)))
        dataset.append(item)
    return dataset


def write_csv(path, rows):
    fields = list(rows[0])
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)
    if os.path.isdir(output_dir) and os.listdir(output_dir) and not args.force:
        raise FileExistsError(f"输出目录非空，如需覆盖请使用 --force: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    records = load_jsonl(os.path.abspath(args.selected_records))
    records_by_id = {record["sample_id"]: record for record in records}
    rows = load_completed_rows(os.path.abspath(args.run_results))
    dataset = aggregate_rows(rows, records_by_id, args.min_repeats)
    write_csv(os.path.join(output_dir, "dataset.csv"), dataset)
    with open(os.path.join(output_dir, "dataset.jsonl"), "w", encoding="utf-8") as file:
        for item in dataset:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    generator_counts = Counter(item["generator"] for item in dataset)
    target_counts = Counter(item["target_risk_level"] for item in dataset)
    summary = {
        "format": "risk_feedback_dataset_v1",
        "source_run_results": os.path.abspath(args.run_results),
        "source_selected_records": os.path.abspath(args.selected_records),
        "raw_run_count": len(rows),
        "independent_scenario_count": len(dataset),
        "minimum_repeats": args.min_repeats,
        "analysis_unit": "independent_scenario",
        "traffic_seed_role": "repeated_measurement",
        "feature_count": len(FEATURE_NAMES),
        "feature_names": list(FEATURE_NAMES),
        "model_input_columns": list(FEATURE_COLUMNS),
        "target_column": "observed_risk_score_mean",
        "target_risk_level_is_input": False,
        "generator_is_input": False,
        "generator_counts": dict(sorted(generator_counts.items())),
        "target_level_counts": dict(sorted(target_counts.items())),
        "collision_run_count": sum(item["collision_run_rate"] > 0 for item in dataset),
    }
    write_json(os.path.join(output_dir, "dataset_summary.json"), summary)
    print(
        f"[DATASET] runs={len(rows)} | independent_scenarios={len(dataset)} | "
        f"features={len(FEATURE_NAMES)}"
    )
    print(f"[DATASET] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
