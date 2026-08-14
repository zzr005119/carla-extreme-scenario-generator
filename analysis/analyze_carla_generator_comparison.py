"""分析 LHS、GMM 与 CVAE 的同口径 CARLA 实测结果。"""

import csv
import json
import os
from collections import Counter

import numpy as np

from core.scenario_features import FEATURE_NAMES, encode_record, parameter_vector
from tools.generate_seed_dataset import RANGES


GENERATORS = ("lhs", "gmm", "cvae")
GENERATOR_NAMES = {
    "balanced_latin_hypercube_v1": "lhs",
    "conditional_diagonal_gmm_v1": "gmm",
    "conditional_tabular_cvae_v1": "cvae",
}
RISK_LEVELS = ("low", "medium", "high", "critical")
RISK_INDEX = {level: index for index, level in enumerate(RISK_LEVELS)}


def completed_rows(rows):
    return [
        row
        for row in rows
        if row["status"] == "completed"
        and row["observed_risk_level"] in RISK_INDEX
        and row["risk_score"] is not None
    ]


def pairwise_distance_mean(records):
    if len(records) < 2:
        return None
    values = np.asarray([encode_record(record) for record in records], dtype=float)
    distances = np.sqrt(
        np.sum((values[:, None, :] - values[None, :, :]) ** 2, axis=2)
    )
    upper = distances[np.triu_indices(len(values), 1)]
    return float(np.mean(upper))


def design_range_consistency(records):
    record_matches = 0
    field_matches = 0
    field_count = 0
    for record in records:
        level = record["conditions"]["target_risk_level"]
        ranges = RANGES[level]
        inside_record = True
        for name, value in zip(FEATURE_NAMES, parameter_vector(record)):
            low, high = ranges[name.split(".", 1)[1]]
            inside = float(low) <= float(value) <= float(high)
            field_matches += int(inside)
            field_count += 1
            inside_record = inside_record and inside
        record_matches += int(inside_record)
    return {
        "record_rate": record_matches / max(1, len(records)),
        "field_rate": field_matches / max(1, field_count),
    }


def selected_record_metrics(records):
    by_generator = {generator: [] for generator in GENERATORS}
    for record in records:
        generator = GENERATOR_NAMES[record["provenance"]["generator"]]
        by_generator[generator].append(record)

    metrics = {}
    for generator, generator_records in by_generator.items():
        per_level_distances = []
        for level in RISK_LEVELS:
            level_records = [
                record
                for record in generator_records
                if record["conditions"]["target_risk_level"] == level
            ]
            distance = pairwise_distance_mean(level_records)
            if distance is not None:
                per_level_distances.append(distance)
        consistency = design_range_consistency(generator_records)
        metrics[generator] = {
            "selected_scenarios": len(generator_records),
            "mean_within_level_pairwise_distance": (
                float(np.mean(per_level_distances))
                if per_level_distances
                else None
            ),
            "design_record_rate": consistency["record_rate"],
            "design_field_rate": consistency["field_rate"],
        }
    return metrics


def safe_std(values):
    return float(np.std(values, ddof=1)) if len(values) > 1 else None


def analyze(rows, selected_records, expected_seeds):
    completed = completed_rows(rows)
    offline_metrics = selected_record_metrics(selected_records)
    generator_rows = []
    generator_target_rows = []

    for generator in GENERATORS:
        current = [row for row in completed if row["generator"] == generator]
        all_rows = [row for row in rows if row["generator"] == generator]
        scores = [float(row["risk_score"]) for row in current]
        target_indices = np.asarray(
            [RISK_INDEX[row["target_risk_level"]] for row in current],
            dtype=float,
        )
        scenario_stds = []
        for sample_id in sorted({row["sample_id"] for row in current}):
            sample_scores = [
                float(row["risk_score"])
                for row in current
                if row["sample_id"] == sample_id
            ]
            if len(sample_scores) > 1:
                scenario_stds.append(float(np.std(sample_scores, ddof=1)))
        seed_means = []
        for seed in expected_seeds:
            seed_scores = [
                float(row["risk_score"])
                for row in current
                if int(row["traffic_manager_seed"]) == int(seed)
            ]
            if seed_scores:
                seed_means.append(float(np.mean(seed_scores)))

        level_means = []
        for level in RISK_LEVELS:
            level_rows = [
                row for row in current if row["target_risk_level"] == level
            ]
            level_scores = [float(row["risk_score"]) for row in level_rows]
            level_mean = float(np.mean(level_scores)) if level_scores else None
            level_means.append(level_mean)
            generator_target_rows.append(
                {
                    "generator": generator,
                    "target_risk_level": level,
                    "selected_scenarios": len(
                        {
                            row["sample_id"]
                            for row in all_rows
                            if row["target_risk_level"] == level
                        }
                    ),
                    "completed_runs": len(level_rows),
                    "accepted_runs": sum(
                        row["acceptance_status"] == "completed"
                        for row in level_rows
                    ),
                    "score_mean": level_mean,
                    "score_std": safe_std(level_scores),
                    "target_match_rate": (
                        sum(
                            row["observed_risk_level"] == level
                            for row in level_rows
                        )
                        / len(level_rows)
                        if level_rows
                        else None
                    ),
                    "observed_distribution": dict(
                        Counter(
                            row["observed_risk_level"] for row in level_rows
                        )
                    ),
                    "collision_runs": sum(
                        int(row["collision_count"] or 0) > 0
                        for row in level_rows
                    ),
                }
            )

        offline = offline_metrics[generator]
        generator_rows.append(
            {
                "generator": generator,
                "selected_scenarios": len(
                    {row["sample_id"] for row in all_rows}
                ),
                "planned_runs": len(all_rows),
                "completed_runs": len(current),
                "accepted_runs": sum(
                    row["acceptance_status"] == "completed" for row in current
                ),
                "route_verified_runs": sum(
                    row.get("route_verified") is True for row in all_rows
                ),
                "score_mean": float(np.mean(scores)) if scores else None,
                "score_std": safe_std(scores),
                "target_match_rate": (
                    sum(
                        row["observed_risk_level"]
                        == row["target_risk_level"]
                        for row in current
                    )
                    / len(current)
                    if current
                    else None
                ),
                "high_or_critical_rate": (
                    sum(
                        row["observed_risk_level"] in {"high", "critical"}
                        for row in current
                    )
                    / len(current)
                    if current
                    else None
                ),
                "critical_rate": (
                    sum(
                        row["observed_risk_level"] == "critical"
                        for row in current
                    )
                    / len(current)
                    if current
                    else None
                ),
                "collision_run_rate": (
                    sum(
                        int(row["collision_count"] or 0) > 0
                        for row in current
                    )
                    / len(current)
                    if current
                    else None
                ),
                "target_score_ordinal_correlation": (
                    float(np.corrcoef(target_indices, np.asarray(scores))[0, 1])
                    if len(scores) > 1
                    else None
                ),
                "mean_scores_strictly_increasing": (
                    all(
                        left is not None and right is not None and left < right
                        for left, right in zip(level_means, level_means[1:])
                    )
                    if level_means
                    else None
                ),
                "mean_within_scenario_score_std": (
                    float(np.mean(scenario_stds)) if scenario_stds else None
                ),
                "maximum_within_scenario_score_std": (
                    float(np.max(scenario_stds)) if scenario_stds else None
                ),
                "seed_mean_score_range": (
                    float(np.max(seed_means) - np.min(seed_means))
                    if seed_means
                    else None
                ),
                "mean_within_level_pairwise_distance": offline[
                    "mean_within_level_pairwise_distance"
                ],
                "design_record_rate": offline["design_record_rate"],
                "design_field_rate": offline["design_field_rate"],
            }
        )

    return {
        "planned_runs": len(rows),
        "completed_runs": len(completed),
        "accepted_runs": sum(
            row["acceptance_status"] == "completed" for row in completed
        ),
        "generator_rows": generator_rows,
        "generator_target_rows": generator_target_rows,
        "analysis_unit": "selected_scenario",
        "traffic_seed_role": "repeated_measure",
        "supports_significance_testing": False,
    }


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def format_number(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    return f"{float(value):.3f}"


def write_report(path, result):
    lines = [
        "# LHS / GMM / CVAE CARLA 同口径对照",
        "",
        f"- 计划运行：`{result['planned_runs']}`",
        f"- 完成运行：`{result['completed_runs']}`",
        f"- 严格验收：`{result['accepted_runs']}`",
        "- 独立实验单位是生成场景样本；三个交通种子是同一样本的重复测量。",
        "- 每个生成器每个目标档仅 3 个独立样本，本轮只做工程描述性比较，不支持统计显著性结论。",
        "",
        "## 生成器汇总",
        "",
        "| 生成器 | 场景 | 完成/计划 | 验收 | 平均分 | 目标命中率 | 高及以上率 | 碰撞运行率 | 场景内标准差均值 | 种子均值极差 | 同档样本距离 | 设计区间记录率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["generator_rows"]:
        lines.append(
            f"| {row['generator']} | {row['selected_scenarios']} | "
            f"{row['completed_runs']}/{row['planned_runs']} | "
            f"{row['accepted_runs']} | {format_number(row['score_mean'])} | "
            f"{format_number(row['target_match_rate'])} | "
            f"{format_number(row['high_or_critical_rate'])} | "
            f"{format_number(row['collision_run_rate'])} | "
            f"{format_number(row['mean_within_scenario_score_std'])} | "
            f"{format_number(row['seed_mean_score_range'])} | "
            f"{format_number(row['mean_within_level_pairwise_distance'])} | "
            f"{format_number(row['design_record_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## 生成器与目标档",
            "",
            "| 生成器 | 目标档 | 场景 | 完成 | 平均分 | 标准差 | 命中率 | 实测分布 | 碰撞运行 |",
            "|---|---|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for row in result["generator_target_rows"]:
        distribution = ", ".join(
            f"{level}:{count}"
            for level, count in sorted(
                row["observed_distribution"].items(),
                key=lambda item: RISK_INDEX[item[0]],
            )
        )
        lines.append(
            f"| {row['generator']} | {row['target_risk_level']} | "
            f"{row['selected_scenarios']} | {row['completed_runs']} | "
            f"{format_number(row['score_mean'])} | "
            f"{format_number(row['score_std'])} | "
            f"{format_number(row['target_match_rate'])} | {distribution} | "
            f"{row['collision_runs']} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- `target_risk_level` 是生成条件，`observed_risk` 是 CARLA 实测标签，二者必须分开报告。",
            "- 交通种子重复不能当作新增独立场景样本，不能把每个生成器的 36 次运行直接当作 n=36。",
            "- 同档样本距离反映选中参数的离线分散程度，不等于交通真实性或危险性。",
            "- 生成器主线应综合运行成功率、风险排序与命中、高风险产出、重复性和多样性确定。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def write_comparison(rows, selected_records, expected_seeds, output_dir):
    result = analyze(rows, selected_records, expected_seeds)
    summary_path = os.path.join(output_dir, "generator_comparison_summary.json")
    generator_csv = os.path.join(output_dir, "generator_summary.csv")
    target_csv = os.path.join(output_dir, "generator_target_summary.csv")
    report_path = os.path.join(output_dir, "generator_comparison_report.md")
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    write_csv(generator_csv, result["generator_rows"])
    target_rows = []
    for row in result["generator_target_rows"]:
        target_rows.append(
            {
                **row,
                "observed_distribution": json.dumps(
                    row["observed_distribution"], ensure_ascii=False
                ),
            }
        )
    write_csv(target_csv, target_rows)
    write_report(report_path, result)
    return result, summary_path, generator_csv, target_csv, report_path
