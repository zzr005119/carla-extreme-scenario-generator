"""分析固定场景在多个 Traffic Manager 种子下的重复性。"""

import csv
import json
import os
from collections import Counter

import numpy as np


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


def analyze(rows, expected_seeds, route_lock_required=False):
    completed = completed_rows(rows)
    accepted = [row for row in completed if row.get("acceptance_status") == "completed"]
    target_levels = tuple(
        level
        for level in RISK_LEVELS
        if any(row["target_risk_level"] == level for row in rows)
    )
    target_matched_runs = sum(
        row["observed_risk_level"] == row["target_risk_level"]
        for row in completed
    )
    target_indices = np.asarray(
        [RISK_INDEX[row["target_risk_level"]] for row in completed],
        dtype=float,
    )
    completed_scores = np.asarray(
        [row["risk_score"] for row in completed],
        dtype=float,
    )
    by_sample = {}
    for row in completed:
        by_sample.setdefault(row["sample_id"], []).append(row)

    scenario_rows = []
    for sample_id, sample_rows in sorted(by_sample.items()):
        sample_rows.sort(key=lambda row: row["traffic_manager_seed"])
        scores = np.asarray([row["risk_score"] for row in sample_rows])
        levels = [row["observed_risk_level"] for row in sample_rows]
        level_counts = Counter(levels)
        modal_level, modal_count = max(
            level_counts.items(),
            key=lambda item: (item[1], -RISK_INDEX[item[0]]),
        )
        scenario_rows.append(
            {
                "sample_id": sample_id,
                "target_risk_level": sample_rows[0]["target_risk_level"],
                "completed_runs": len(sample_rows),
                "expected_runs": len(expected_seeds),
                "seeds": ",".join(
                    str(row["traffic_manager_seed"]) for row in sample_rows
                ),
                "score_mean": float(np.mean(scores)),
                "score_std": float(np.std(scores, ddof=1)) if len(scores) > 1 else None,
                "score_min": float(np.min(scores)),
                "score_max": float(np.max(scores)),
                "score_range": float(np.max(scores) - np.min(scores)),
                "modal_observed_level": modal_level,
                "level_consistency_rate": modal_count / len(sample_rows),
                "all_levels_equal": len(level_counts) == 1,
                "target_match_rate": sum(
                    row["observed_risk_level"] == row["target_risk_level"]
                    for row in sample_rows
                )
                / len(sample_rows),
                "collision_runs": sum(row["collision_count"] > 0 for row in sample_rows),
                "collision_events": sum(row["collision_count"] for row in sample_rows),
            }
        )

    seed_rows = []
    for seed in expected_seeds:
        seed_values = [
            row["risk_score"]
            for row in completed
            if row["traffic_manager_seed"] == seed
        ]
        seed_rows.append(
            {
                "traffic_manager_seed": seed,
                "completed_runs": len(seed_values),
                "score_mean": float(np.mean(seed_values)) if seed_values else None,
                "score_std": (
                    float(np.std(seed_values, ddof=1))
                    if len(seed_values) > 1
                    else None
                ),
            }
        )

    per_target_level = {}
    for level in RISK_LEVELS:
        level_rows = [row for row in completed if row["target_risk_level"] == level]
        scores = [row["risk_score"] for row in level_rows]
        per_target_level[level] = {
            "completed_runs": len(level_rows),
            "score_mean": float(np.mean(scores)) if scores else None,
            "score_std": float(np.std(scores, ddof=1)) if len(scores) > 1 else None,
            "target_match_rate": (
                sum(row["observed_risk_level"] == level for row in level_rows)
                / len(level_rows)
                if level_rows
                else None
            ),
            "observed_distribution": dict(
                Counter(row["observed_risk_level"] for row in level_rows)
            ),
        }

    scenario_stds = [
        row["score_std"] for row in scenario_rows if row["score_std"] is not None
    ]
    scenario_ranges = [row["score_range"] for row in scenario_rows]
    ordered_means = [
        per_target_level[level]["score_mean"] for level in target_levels
    ]
    seed_means = [
        row["score_mean"] for row in seed_rows if row["score_mean"] is not None
    ]
    most_variable_scenario = (
        max(scenario_rows, key=lambda row: row["score_std"] or 0.0)
        if scenario_rows
        else None
    )
    expected_sample_ids = {row["sample_id"] for row in rows}
    route_ego_rates = [
        float(row["route_ego_on_route_rate"])
        for row in completed
        if row.get("route_ego_on_route_rate") is not None
    ]
    route_lead_rates = [
        float(row["route_lead_on_route_rate"])
        for row in completed
        if row.get("route_lead_on_route_rate") is not None
    ]
    route_both_rates = [
        float(row["route_both_on_route_rate"])
        for row in completed
        if row.get("route_both_on_route_rate") is not None
    ]
    route_ego_deviations = [
        float(row["route_maximum_ego_deviation_m"])
        for row in completed
        if row.get("route_maximum_ego_deviation_m") is not None
    ]
    route_lead_deviations = [
        float(row["route_maximum_lead_deviation_m"])
        for row in completed
        if row.get("route_maximum_lead_deviation_m") is not None
    ]
    return {
        "expected_run_count": len(expected_sample_ids) * len(expected_seeds),
        "total_manifest_runs": len(rows),
        "completed_runs": len(completed),
        "accepted_runs": len(accepted),
        "acceptance_failed_runs": sum(
            row.get("acceptance_status") == "failed" for row in rows
        ),
        "failed_runs": sum(row["status"] == "failed" for row in rows),
        "missing_runs": sum(row["status"] == "missing" for row in rows),
        "sensor_completed_runs": sum(
            row["sensor_status"] == "completed" for row in completed
        ),
        "server_healthy_runs": sum(
            row["server_status"] == "healthy" for row in completed
        ),
        "route_lock_required": route_lock_required,
        "route_verified_runs": sum(
            row["route_verified"] is True for row in rows
        ),
        "route_verified_rate": (
            sum(row["route_verified"] is True for row in rows) / len(rows)
            if rows
            else None
        ),
        "route_ego_on_route_rate_mean": (
            float(np.mean(route_ego_rates)) if route_ego_rates else None
        ),
        "route_lead_on_route_rate_mean": (
            float(np.mean(route_lead_rates)) if route_lead_rates else None
        ),
        "route_both_on_route_rate_mean": (
            float(np.mean(route_both_rates)) if route_both_rates else None
        ),
        "route_maximum_ego_deviation_m": (
            float(np.max(route_ego_deviations)) if route_ego_deviations else None
        ),
        "route_maximum_lead_deviation_m": (
            float(np.max(route_lead_deviations)) if route_lead_deviations else None
        ),
        "target_levels": list(target_levels),
        "collision_runs": sum(row["collision_count"] > 0 for row in completed),
        "collision_events": sum(row["collision_count"] for row in completed),
        "collision_sample_ids": sorted(
            {
                row["sample_id"]
                for row in completed
                if row["collision_count"] > 0
            }
        ),
        "target_matched_runs": target_matched_runs,
        "target_match_rate": (
            target_matched_runs / len(completed) if completed else None
        ),
        "target_score_ordinal_correlation": (
            float(np.corrcoef(target_indices, completed_scores)[0, 1])
            if len(completed) > 1
            else None
        ),
        "scenario_count": len(scenario_rows),
        "complete_scenario_count": sum(
            row["completed_runs"] == row["expected_runs"] for row in scenario_rows
        ),
        "all_level_equal_scenario_count": sum(
            row["all_levels_equal"] for row in scenario_rows
        ),
        "all_level_equal_scenario_rate": (
            sum(row["all_levels_equal"] for row in scenario_rows)
            / len(scenario_rows)
            if scenario_rows
            else None
        ),
        "mean_within_scenario_score_std": (
            float(np.mean(scenario_stds)) if scenario_stds else None
        ),
        "median_within_scenario_score_std": (
            float(np.median(scenario_stds)) if scenario_stds else None
        ),
        "maximum_within_scenario_score_std": (
            float(np.max(scenario_stds)) if scenario_stds else None
        ),
        "mean_within_scenario_score_range": (
            float(np.mean(scenario_ranges)) if scenario_ranges else None
        ),
        "seed_mean_score_range": (
            float(max(seed_means) - min(seed_means)) if seed_means else None
        ),
        "most_variable_scenario": (
            {
                "sample_id": most_variable_scenario["sample_id"],
                "score_std": most_variable_scenario["score_std"],
                "score_range": most_variable_scenario["score_range"],
            }
            if most_variable_scenario
            else None
        ),
        "mean_scores_strictly_increasing": (
            bool(ordered_means)
            and all(value is not None for value in ordered_means)
            and all(left < right for left, right in zip(ordered_means, ordered_means[1:]))
        ),
        "per_target_level": per_target_level,
        "scenario_rows": scenario_rows,
        "seed_rows": seed_rows,
    }


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_number(value, digits=3):
    return "-" if value is None else f"{value:.{digits}f}"


def write_report(path, analysis):
    lines = [
        "# CVAE CARLA 多种子重复性分析",
        "",
        f"- 仿真完成：`{analysis['completed_runs']}/{analysis['expected_run_count']}`",
        f"- 严格验收通过：`{analysis['accepted_runs']}/{analysis['expected_run_count']}`",
        f"- 完整场景：`{analysis['complete_scenario_count']}/{analysis['scenario_count']}`",
        f"- 三次实测档位完全一致：`{analysis['all_level_equal_scenario_count']}/{analysis['scenario_count']}`",
        f"- 目标档位逐次命中：`{analysis['target_matched_runs']}/{analysis['completed_runs']}`",
        f"- 目标档位序号与实测分数相关系数：`{format_number(analysis['target_score_ordinal_correlation'])}`",
        f"- 场景内分数标准差均值：`{format_number(analysis['mean_within_scenario_score_std'])}`",
        f"- 场景内分数标准差最大值：`{format_number(analysis['maximum_within_scenario_score_std'])}`",
        f"- 三个交通种子平均分极差：`{format_number(analysis['seed_mean_score_range'])}`",
        f"- 碰撞运行：`{analysis['collision_runs']}`，碰撞事件：`{analysis['collision_events']}`",
        f"- 目标档平均分严格递增：`{analysis['mean_scores_strictly_increasing']}`",
        "",
        "## 目标档统计",
        "",
        "| 目标档 | 完成 | 平均分 | 标准差 | 逐次命中率 | 实测分布 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for level in analysis["target_levels"]:
        row = analysis["per_target_level"][level]
        distribution = ", ".join(
            f"{key}:{value}"
            for key, value in sorted(
                row["observed_distribution"].items(),
                key=lambda item: RISK_INDEX[item[0]],
            )
        )
        lines.append(
            f"| {level} | {row['completed_runs']} | "
            f"{format_number(row['score_mean'])} | "
            f"{format_number(row['score_std'])} | "
            f"{format_number(row['target_match_rate'])} | {distribution} |"
        )
    lines.extend(
        [
            "",
            "## 交通种子统计",
            "",
            "| Traffic Manager 种子 | 完成 | 平均分 | 标准差 |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in analysis["seed_rows"]:
        lines.append(
            f"| {row['traffic_manager_seed']} | {row['completed_runs']} | "
            f"{format_number(row['score_mean'])} | "
            f"{format_number(row['score_std'])} |"
        )
    lines.extend(
        [
            "",
            "## 场景统计",
            "",
        "| 样本 | 目标档 | 完成 | 平均分 | 标准差 | 极差 | 众数档 | 档位一致率 | 命中率 | 碰撞运行 |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|",
        ]
    )
    for row in analysis["scenario_rows"]:
        lines.append(
            f"| {row['sample_id']} | {row['target_risk_level']} | "
            f"{row['completed_runs']}/{row['expected_runs']} | "
            f"{format_number(row['score_mean'])} | "
            f"{format_number(row['score_std'])} | "
            f"{format_number(row['score_range'])} | "
            f"{row['modal_observed_level']} | "
            f"{format_number(row['level_consistency_rate'])} | "
            f"{format_number(row['target_match_rate'])} | "
            f"{row['collision_runs']} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 三个交通种子用于工程重复性检查，不足以支持正式显著性检验。",
            "- 同一场景只改变 Traffic Manager 种子，场景参数保持固定。",
            "- `target_risk_level` 仍是设计条件，稳定性判断基于 CARLA 实测 `observed_risk`。",
            "",
        ]
    )
    if analysis["route_lock_required"]:
        lines[13:13] = [
            f"- 路线锁定验收：`{analysis['route_verified_runs']}/{analysis['total_manifest_runs']}`",
            f"- 主车平均在途率：`{format_number(analysis['route_ego_on_route_rate_mean'])}`",
            f"- 前车平均在途率：`{format_number(analysis['route_lead_on_route_rate_mean'])}`",
            f"- 双车平均同时在途率：`{format_number(analysis['route_both_on_route_rate_mean'])}`",
            f"- 主车最大路线偏差：`{format_number(analysis['route_maximum_ego_deviation_m'])} m`",
            f"- 前车最大路线偏差：`{format_number(analysis['route_maximum_lead_deviation_m'])} m`",
        ]
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def write_analysis(
    rows,
    expected_seeds,
    output_dir,
    route_lock_required=False,
):
    analysis = analyze(rows, expected_seeds, route_lock_required)
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, "repeatability_summary.json")
    scenario_csv = os.path.join(output_dir, "repeatability_by_scenario.csv")
    seed_csv = os.path.join(output_dir, "repeatability_by_seed.csv")
    report_path = os.path.join(output_dir, "repeatability_report.md")
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                key: value
                for key, value in analysis.items()
                if key not in {"scenario_rows", "seed_rows"}
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    scenario_fields = (
        tuple(analysis["scenario_rows"][0])
        if analysis["scenario_rows"]
        else ()
    )
    seed_fields = tuple(analysis["seed_rows"][0]) if analysis["seed_rows"] else ()
    if scenario_fields:
        write_csv(scenario_csv, analysis["scenario_rows"], scenario_fields)
    if seed_fields:
        write_csv(seed_csv, analysis["seed_rows"], seed_fields)
    write_report(report_path, analysis)
    return analysis, summary_path, scenario_csv, seed_csv, report_path
