"""分析反馈候选短名单的 CARLA 外部验证结果。"""

import csv
import json
import math
import os
from collections import defaultdict

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error


HIGH_RISK_THRESHOLD = 50.0
DEFAULT_TOP_K = 9


def safe_std(values):
    return float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def safe_spearman(left, right):
    if len(left) < 2 or len(set(left)) < 2 or len(set(right)) < 2:
        return None
    result = spearmanr(left, right)
    value = getattr(result, "statistic", result[0])
    return None if np.isnan(value) else float(value)


def ranked_sample_ids(rows, score_key, top_k):
    ordered = sorted(
        rows,
        key=lambda row: (-float(row[score_key]), str(row["sample_id"])),
    )
    return [row["sample_id"] for row in ordered[:top_k]]


def aggregate_scenarios(rows):
    accepted = [row for row in rows if row.get("acceptance_status") == "completed"]
    grouped = defaultdict(list)
    for row in accepted:
        grouped[row["sample_id"]].append(row)

    scenario_rows = []
    for sample_id, repeated_rows in sorted(grouped.items()):
        repeated_rows.sort(key=lambda row: int(row["traffic_manager_seed"]))
        scores = [float(row["risk_score"]) for row in repeated_rows]
        collision_counts = [int(row["collision_count"] or 0) for row in repeated_rows]
        source = repeated_rows[0]
        scenario_rows.append(
            {
                "sample_id": sample_id,
                "generator": source["generator"],
                "selection_channel": source["selection_channel"],
                "selection_order": int(source["selection_order"]),
                "target_risk_level": source["target_risk_level"],
                "accepted_runs": len(repeated_rows),
                "traffic_manager_seeds": ",".join(
                    str(row["traffic_manager_seed"]) for row in repeated_rows
                ),
                "predicted_risk_mean": float(source["predicted_risk_mean"]),
                "predicted_risk_std": float(source["predicted_risk_std"]),
                "robust_predicted_risk_score": float(
                    source["robust_predicted_risk_score"]
                ),
                "bootstrap_top_k_frequency": float(
                    source["bootstrap_top_k_frequency"]
                ),
                "nearest_collision_distance": float(
                    source["nearest_collision_distance"]
                ),
                "collision_boundary_score": float(
                    source["collision_boundary_score"]
                ),
                "selection_diversity_distance": float(
                    source["selection_diversity_distance"]
                ),
                "observed_risk_score_mean": float(np.mean(scores)),
                "observed_risk_score_std": safe_std(scores),
                "observed_risk_score_min": float(np.min(scores)),
                "observed_risk_score_max": float(np.max(scores)),
                "prediction_error": float(np.mean(scores))
                - float(source["predicted_risk_mean"]),
                "absolute_prediction_error": abs(
                    float(np.mean(scores)) - float(source["predicted_risk_mean"])
                ),
                "high_or_critical_observed": float(np.mean(scores))
                >= HIGH_RISK_THRESHOLD,
                "collision_runs": sum(count > 0 for count in collision_counts),
                "collision_events": sum(collision_counts),
                "collision_observed": any(count > 0 for count in collision_counts),
                "minimum_ttc_seconds": min(
                    float(row["minimum_ttc_seconds"]) for row in repeated_rows
                ),
                "minimum_lead_gap_m": min(
                    float(row["minimum_lead_gap_m"]) for row in repeated_rows
                ),
                "minimum_pedestrian_distance_m": min(
                    float(row["minimum_pedestrian_distance_m"])
                    for row in repeated_rows
                ),
            }
        )
    return scenario_rows


def summarize_group(rows, fields):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in fields)].append(row)
    summaries = []
    for key, current in sorted(grouped.items()):
        predicted = [float(row["predicted_risk_mean"]) for row in current]
        observed = [float(row["observed_risk_score_mean"]) for row in current]
        item = {field: value for field, value in zip(fields, key)}
        item.update(
            {
                "scenario_count": len(current),
                "predicted_risk_mean": float(np.mean(predicted)),
                "observed_risk_mean": float(np.mean(observed)),
                "observed_risk_std_between_scenarios": safe_std(observed),
                "external_mae": float(mean_absolute_error(observed, predicted)),
                "high_or_critical_scenarios": sum(
                    row["high_or_critical_observed"] for row in current
                ),
                "high_or_critical_rate": sum(
                    row["high_or_critical_observed"] for row in current
                )
                / len(current),
                "collision_scenarios": sum(
                    row["collision_observed"] for row in current
                ),
                "collision_scenario_rate": sum(
                    row["collision_observed"] for row in current
                )
                / len(current),
                "mean_nearest_collision_distance": float(
                    np.mean(
                        [float(row["nearest_collision_distance"]) for row in current]
                    )
                ),
            }
        )
        summaries.append(item)
    return summaries


def build_paired_comparison(scenarios):
    grouped = defaultdict(dict)
    for row in scenarios:
        key = (
            row["generator"],
            row["target_risk_level"],
            int(row["selection_order"]),
        )
        grouped[key][row["selection_channel"]] = row

    pair_rows = []
    for key in sorted(grouped):
        channels = grouped[key]
        if "single_only" not in channels or "dual_only" not in channels:
            continue
        single = channels["single_only"]
        dual = channels["dual_only"]
        pair_rows.append(
            {
                "generator": key[0],
                "target_risk_level": key[1],
                "pair_order": key[2],
                "single_sample_id": single["sample_id"],
                "dual_sample_id": dual["sample_id"],
                "single_predicted_risk_mean": float(single["predicted_risk_mean"]),
                "dual_predicted_risk_mean": float(dual["predicted_risk_mean"]),
                "single_observed_risk_mean": float(
                    single["observed_risk_score_mean"]
                ),
                "dual_observed_risk_mean": float(dual["observed_risk_score_mean"]),
                "observed_risk_delta_dual_minus_single": float(
                    dual["observed_risk_score_mean"]
                    - single["observed_risk_score_mean"]
                ),
                "single_collision_observed": bool(single["collision_observed"]),
                "dual_collision_observed": bool(dual["collision_observed"]),
                "single_high_or_critical_observed": bool(
                    single["high_or_critical_observed"]
                ),
                "dual_high_or_critical_observed": bool(
                    dual["high_or_critical_observed"]
                ),
            }
        )

    observed_deltas = [
        row["observed_risk_delta_dual_minus_single"] for row in pair_rows
    ]
    dual_collision_count = sum(row["dual_collision_observed"] for row in pair_rows)
    single_collision_count = sum(
        row["single_collision_observed"] for row in pair_rows
    )
    return {
        "pair_count": len(pair_rows),
        "complete_pair_count": len(pair_rows),
        "observed_risk_delta_dual_minus_single_mean": (
            float(np.mean(observed_deltas)) if observed_deltas else None
        ),
        "observed_risk_delta_dual_minus_single_median": (
            float(np.median(observed_deltas)) if observed_deltas else None
        ),
        "dual_higher_observed_count": sum(delta > 0 for delta in observed_deltas),
        "single_higher_observed_count": sum(delta < 0 for delta in observed_deltas),
        "tie_observed_count": sum(delta == 0 for delta in observed_deltas),
        "dual_collision_scenario_count": dual_collision_count,
        "single_collision_scenario_count": single_collision_count,
        "collision_count_delta_dual_minus_single": (
            dual_collision_count - single_collision_count
        ),
        "collision_discordant_pair_count": sum(
            row["dual_collision_observed"] != row["single_collision_observed"]
            for row in pair_rows
        ),
    }, pair_rows


def analyze(rows, planned_scenario_count, top_k=DEFAULT_TOP_K):
    scenarios = aggregate_scenarios(rows)
    predicted = [float(row["predicted_risk_mean"]) for row in scenarios]
    robust = [float(row["robust_predicted_risk_score"]) for row in scenarios]
    observed = [float(row["observed_risk_score_mean"]) for row in scenarios]
    effective_top_k = min(top_k, len(scenarios))
    predicted_top = set(
        ranked_sample_ids(scenarios, "robust_predicted_risk_score", effective_top_k)
    )
    observed_top = set(
        ranked_sample_ids(scenarios, "observed_risk_score_mean", effective_top_k)
    )
    union = predicted_top | observed_top
    intersection = predicted_top & observed_top
    paired_comparison, paired_rows = build_paired_comparison(scenarios)
    return {
        "format": "feedback_candidate_external_validation_v1",
        "planned_scenario_count": planned_scenario_count,
        "accepted_scenario_count": len(scenarios),
        "complete": len(scenarios) == planned_scenario_count,
        "high_risk_threshold": HIGH_RISK_THRESHOLD,
        "external_metrics": {
            "mae": (
                float(mean_absolute_error(observed, predicted)) if scenarios else None
            ),
            "rmse": (
                float(mean_squared_error(observed, predicted) ** 0.5)
                if scenarios
                else None
            ),
            "predicted_mean_spearman": safe_spearman(predicted, observed),
            "robust_score_spearman": safe_spearman(robust, observed),
            "mean_bias": (
                float(np.mean(np.asarray(predicted) - np.asarray(observed)))
                if scenarios
                else None
            ),
        },
        "discovery": {
            "high_or_critical_scenarios": sum(
                row["high_or_critical_observed"] for row in scenarios
            ),
            "high_or_critical_rate": (
                sum(row["high_or_critical_observed"] for row in scenarios)
                / len(scenarios)
                if scenarios
                else None
            ),
            "collision_scenarios": sum(
                row["collision_observed"] for row in scenarios
            ),
            "collision_scenario_rate": (
                sum(row["collision_observed"] for row in scenarios) / len(scenarios)
                if scenarios
                else None
            ),
            "collision_events": sum(row["collision_events"] for row in scenarios),
        },
        "top_k": {
            "k": effective_top_k,
            "predicted_ids": sorted(predicted_top),
            "observed_ids": sorted(observed_top),
            "overlap_count": len(intersection),
            "recall": (
                len(intersection) / effective_top_k if effective_top_k else None
            ),
            "jaccard": len(intersection) / len(union) if union else None,
        },
        "by_generator": summarize_group(scenarios, ("generator",)),
        "by_channel": summarize_group(scenarios, ("selection_channel",)),
        "by_generator_channel": summarize_group(
            scenarios, ("generator", "selection_channel")
        ),
        "by_target": summarize_group(scenarios, ("target_risk_level",)),
        "paired_comparison": paired_comparison,
        "scenario_rows": scenarios,
        "paired_rows": paired_rows,
    }


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def format_number(value):
    return "-" if value is None or not math.isfinite(value) else f"{value:.3f}"


def report_table(lines, title, rows, group_fields):
    lines.extend(
        [
            f"## {title}",
            "",
            "| 分组 | 场景 | 预测均值 | 实测均值 | 外部MAE | 高风险及以上 | 碰撞场景 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        group = " / ".join(str(row[field]) for field in group_fields)
        lines.append(
            f"| {group} | {row['scenario_count']} | "
            f"{format_number(row['predicted_risk_mean'])} | "
            f"{format_number(row['observed_risk_mean'])} | "
            f"{format_number(row['external_mae'])} | "
            f"{row['high_or_critical_scenarios']} | {row['collision_scenarios']} |"
        )
    lines.append("")


def write_report(path, result):
    metrics = result["external_metrics"]
    discovery = result["discovery"]
    top_k = result["top_k"]
    lines = [
        "# 反馈候选 CARLA 外部验证 V1",
        "",
        f"- 完整独立场景：`{result['accepted_scenario_count']}/{result['planned_scenario_count']}`。",
        f"- 代理预测均值外部 MAE：`{format_number(metrics['mae'])}`；RMSE：`{format_number(metrics['rmse'])}`。",
        f"- 预测均值与实测均值 Spearman：`{format_number(metrics['predicted_mean_spearman'])}`。",
        f"- 稳健排序分与实测均值 Spearman：`{format_number(metrics['robust_score_spearman'])}`。",
        f"- 高风险及以上场景：`{discovery['high_or_critical_scenarios']}`；碰撞场景：`{discovery['collision_scenarios']}`。",
        f"- Top-{top_k['k']} 重合：`{top_k['overlap_count']}`；召回率：`{format_number(top_k['recall'])}`；Jaccard：`{format_number(top_k['jaccard'])}`。",
        "",
    ]
    report_table(lines, "按生成器", result["by_generator"], ("generator",))
    report_table(lines, "按选择通道", result["by_channel"], ("selection_channel",))
    report_table(
        lines,
        "按生成器与选择通道",
        result["by_generator_channel"],
        ("generator", "selection_channel"),
    )
    paired = result["paired_comparison"]
    lines.extend(
        [
            "## 配对比较",
            "",
            f"- 完整配对：`{paired['complete_pair_count']}/{paired['pair_count']}`。",
            f"- 实测风险差值（双通道独有 - 单通道独有）均值：`{format_number(paired['observed_risk_delta_dual_minus_single_mean'])}`；中位数：`{format_number(paired['observed_risk_delta_dual_minus_single_median'])}`。",
            f"- 配对中双通道实测更高：`{paired['dual_higher_observed_count']}`；单通道更高：`{paired['single_higher_observed_count']}`；相同：`{paired['tie_observed_count']}`。",
            f"- 碰撞场景数：双通道 `{paired['dual_collision_scenario_count']}`，单通道 `{paired['single_collision_scenario_count']}`；不一致配对：`{paired['collision_discordant_pair_count']}`。",
            "",
            "## 解释边界",
            "",
            f"- `{result['accepted_scenario_count']}` 个场景是由旧风险代理主动筛选的外部验证短名单，不代表原始生成器总体分布。",
            f"- 每个场景的三个 Traffic Manager 种子是重复测量，独立样本量仍为 `{result['accepted_scenario_count']}`。",
            "- 各生成器和通道只有 9 个独立场景，本轮仅作工程描述，不进行显著性检验。",
            "- `target_risk_level` 是生成条件，所有危险性结论必须以 CARLA 实测 `observed_risk` 为准。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def write_analysis(rows, planned_scenario_count, output_dir, top_k=DEFAULT_TOP_K):
    result = analyze(rows, planned_scenario_count, top_k=top_k)
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, "external_validation_summary.json")
    scenario_path = os.path.join(output_dir, "external_validation_by_scenario.csv")
    generator_path = os.path.join(output_dir, "external_validation_by_generator.csv")
    channel_path = os.path.join(output_dir, "external_validation_by_channel.csv")
    paired_path = os.path.join(output_dir, "external_validation_paired.csv")
    generator_channel_path = os.path.join(
        output_dir, "external_validation_by_generator_channel.csv"
    )
    report_path = os.path.join(output_dir, "external_validation_report.md")
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                key: value
                for key, value in result.items()
                if key not in {"scenario_rows", "paired_rows"}
            },
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    write_csv(scenario_path, result["scenario_rows"])
    write_csv(generator_path, result["by_generator"])
    write_csv(channel_path, result["by_channel"])
    write_csv(paired_path, result["paired_rows"])
    write_csv(generator_channel_path, result["by_generator_channel"])
    write_report(report_path, result)
    return result, summary_path, scenario_path, report_path
