"""离线比较参数级场景生成器的合法性、条件一致性与多样性。"""

import argparse
import csv
import json
import os
import sys
from collections import Counter

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import (  # noqa: E402
    FEATURE_NAMES,
    encode_record,
    load_jsonl,
    parameter_vector,
)
from core.scenario_validator import validate_scenario_record  # noqa: E402
from tools.generate_seed_dataset import RANGES  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="比较场景生成器离线质量")
    parser.add_argument(
        "--reference",
        default=os.path.join(
            PROJECT_ROOT,
            "data",
            "scenarios",
            "seed_v1",
            "train.jsonl",
        ),
    )
    parser.add_argument("inputs", nargs="+", help="待评估的 JSONL 文件")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "artifacts", "evaluation"),
    )
    return parser.parse_args()


def pairwise_summary(values):
    if len(values) < 2:
        return {"mean": None, "minimum": None}
    distances = np.sqrt(
        np.sum((values[:, None, :] - values[None, :, :]) ** 2, axis=2)
    )
    upper = distances[np.triu_indices(len(values), 1)]
    return {
        "mean": float(np.mean(upper)),
        "minimum": float(np.min(upper)),
    }


def nearest_distance(values, reference):
    if not len(values) or not len(reference):
        return {"mean": None, "minimum": None}
    distances = np.sqrt(
        np.sum((values[:, None, :] - reference[None, :, :]) ** 2, axis=2)
    )
    nearest = np.min(distances, axis=1)
    return {
        "mean": float(np.mean(nearest)),
        "minimum": float(np.min(nearest)),
    }


def safe_correlation(values):
    if len(values) < 2:
        return np.zeros((len(FEATURE_NAMES), len(FEATURE_NAMES)))
    centered = values - np.mean(values, axis=0, keepdims=True)
    standard_deviation = np.std(centered, axis=0)
    valid = standard_deviation > 0.0
    standardized = np.zeros_like(centered)
    standardized[:, valid] = centered[:, valid] / standard_deviation[valid]
    return standardized.T @ standardized / len(values)


def design_range_consistency(records):
    all_fields_inside = 0
    inside_fields = 0
    total_fields = 0
    for record in records:
        level = record["conditions"]["target_risk_level"]
        ranges = RANGES[level]
        vector = parameter_vector(record)
        record_inside = True
        for name, value in zip(FEATURE_NAMES, vector):
            low, high = ranges[name.split(".", 1)[1]]
            inside = low <= float(value) <= high
            inside_fields += int(inside)
            total_fields += 1
            record_inside = record_inside and inside
        all_fields_inside += int(record_inside)
    return {
        "record_rate": all_fields_inside / max(1, len(records)),
        "field_rate": inside_fields / max(1, total_fields),
    }


def generation_summary(path):
    summary_path = os.path.splitext(path)[0] + "_summary.json"
    if not os.path.isfile(summary_path):
        return None
    with open(summary_path, "r", encoding="utf-8") as file:
        return json.load(file)


def evaluate_file(path, reference_records, reference_by_level):
    records = load_jsonl(path)
    validations = [validate_scenario_record(record) for record in records]
    valid_count = sum(result["valid"] for result in validations)
    warning_count = sum(len(result["warnings"]) for result in validations)
    values = np.asarray([encode_record(record) for record in records])
    rounded_vectors = [tuple(np.round(value, 6)) for value in values]
    reference_vectors = np.asarray(
        [encode_record(record) for record in reference_records]
    )
    reference_keys = {
        tuple(np.round(value, 6))
        for value in reference_vectors
    }
    if records:
        levels = sorted(
            {record["conditions"]["target_risk_level"] for record in records}
        )
        level_reference_records = [
            record
            for level in levels
            for record in reference_by_level[level]
        ]
    else:
        levels = []
        level_reference_records = []
    level_reference = np.asarray(
        [encode_record(record) for record in level_reference_records]
    )
    pairwise = pairwise_summary(values)
    nearest = nearest_distance(values, level_reference)
    correlation_error = None
    if len(values) >= 2 and len(level_reference) >= 2:
        correlation_error = float(
            np.sqrt(
                np.mean(
                    (
                        safe_correlation(values)
                        - safe_correlation(level_reference)
                    )
                    ** 2
                )
            )
        )
    summary = generation_summary(path)
    return {
        "name": os.path.splitext(os.path.basename(path))[0],
        "path": os.path.abspath(path),
        "records": len(records),
        "risk_levels": levels,
        "schema_valid_rate": valid_count / max(1, len(records)),
        "warning_count": warning_count,
        "unique_rate": len(set(rounded_vectors)) / max(1, len(records)),
        "training_exact_duplicate_rate": sum(
            vector in reference_keys for vector in rounded_vectors
        )
        / max(1, len(records)),
        "feature_std_mean": float(np.mean(np.std(values, axis=0)))
        if len(values)
        else None,
        "pairwise_distance_mean": pairwise["mean"],
        "pairwise_distance_minimum": pairwise["minimum"],
        "nearest_same_level_train_mean": nearest["mean"],
        "nearest_same_level_train_minimum": nearest["minimum"],
        "correlation_rmse": correlation_error,
        "design_range_consistency": design_range_consistency(records),
        "weather_tag_distribution": dict(
            Counter(
                tag
                for record in records
                for tag in record["conditions"]["weather_tags"]
            )
        ),
        "generation": summary,
    }


def write_csv(path, results):
    fields = (
        "name",
        "records",
        "schema_valid_rate",
        "warning_count",
        "unique_rate",
        "training_exact_duplicate_rate",
        "feature_std_mean",
        "pairwise_distance_mean",
        "pairwise_distance_minimum",
        "nearest_same_level_train_mean",
        "nearest_same_level_train_minimum",
        "correlation_rmse",
        "design_record_rate",
        "design_field_rate",
        "acceptance_rate",
        "accepted_sample_latency_ms",
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            generation = result["generation"] or {}
            writer.writerow(
                {
                    **{name: result.get(name) for name in fields},
                    "design_record_rate": result["design_range_consistency"][
                        "record_rate"
                    ],
                    "design_field_rate": result["design_range_consistency"][
                        "field_rate"
                    ],
                    "acceptance_rate": generation.get("acceptance_rate"),
                    "accepted_sample_latency_ms": generation.get(
                        "accepted_sample_latency_ms"
                    ),
                }
            )


def write_markdown(path, results):
    lines = [
        "# 参数级场景生成器离线评估",
        "",
        "> 这些指标衡量合法性、人工条件一致性和参数分布，不代表 CARLA 实测危险性。",
        "",
        "| 数据集 | 有效率 | 唯一率 | 设计区间记录一致率 | 平均样本距离 | 最近训练距离 | 相关矩阵误差 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            "| {name} | {valid:.3f} | {unique:.3f} | {design:.3f} | "
            "{pair:.4f} | {nearest:.4f} | {corr:.4f} |".format(
                name=result["name"],
                valid=result["schema_valid_rate"],
                unique=result["unique_rate"],
                design=result["design_range_consistency"]["record_rate"],
                pair=result["pairwise_distance_mean"] or 0.0,
                nearest=result["nearest_same_level_train_mean"] or 0.0,
                corr=result["correlation_rmse"] or 0.0,
            )
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- `target_risk_level` 仍是人工参数设计条件，不是实测风险标签。",
            "- 有效率来自 Schema 与语义校验，不等于 CARLA 可成功生成 Actor。",
            "- 最近训练距离和样本距离越大通常代表更高多样性，但过大也可能偏离训练分布。",
            "- 最终模型优劣仍需抽样运行 CARLA，并回填 `observed_risk` 后判断。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def main():
    args = parse_args()
    reference_records = load_jsonl(os.path.abspath(args.reference))
    reference_by_level = {}
    for record in reference_records:
        level = record["conditions"]["target_risk_level"]
        reference_by_level.setdefault(level, []).append(record)
    results = [
        evaluate_file(os.path.abspath(path), reference_records, reference_by_level)
        for path in args.inputs
    ]
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "generator_evaluation.json")
    csv_path = os.path.join(output_dir, "generator_evaluation.csv")
    markdown_path = os.path.join(output_dir, "generator_evaluation.md")
    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
    write_csv(csv_path, results)
    write_markdown(markdown_path, results)
    print(f"[EVALUATION] 数据集: {len(results)}")
    print(f"[EVALUATION] JSON: {json_path}")
    print(f"[EVALUATION] CSV: {csv_path}")
    print(f"[EVALUATION] 报告: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
