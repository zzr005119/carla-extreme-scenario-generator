"""分析生成场景的 CARLA 实测风险与目标条件偏差。"""

import argparse
import csv
import json
import os
from collections import Counter

import numpy as np


RISK_LEVELS = ("low", "medium", "high", "critical")
RISK_INDEX = {level: index for index, level in enumerate(RISK_LEVELS)}


def parse_optional(value):
    return None if value in (None, "", "None") else value


def load_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        for field in (
            "risk_score",
            "minimum_ttc_seconds",
            "minimum_lead_gap_m",
            "minimum_pedestrian_distance_m",
        ):
            row[field] = (
                float(row[field])
                if parse_optional(row.get(field)) is not None
                else None
            )
        row["collision_count"] = (
            int(row["collision_count"])
            if parse_optional(row.get("collision_count")) is not None
            else None
        )
        row["target_match"] = {
            "True": True,
            "False": False,
        }.get(row.get("target_match"))
    return rows


def analyze_rows(rows):
    completed = [
        row
        for row in rows
        if row["status"] == "completed"
        and row.get("observed_risk_level") in RISK_INDEX
        and row.get("risk_score") is not None
    ]
    per_level = {}
    level_means = []
    for level in RISK_LEVELS:
        level_rows = [row for row in completed if row["target_risk_level"] == level]
        scores = [row["risk_score"] for row in level_rows]
        observed_counts = Counter(row["observed_risk_level"] for row in level_rows)
        mean_score = float(np.mean(scores)) if scores else None
        if mean_score is not None:
            level_means.append((level, mean_score))
        per_level[level] = {
            "planned": sum(row["target_risk_level"] == level for row in rows),
            "completed": len(level_rows),
            "matches": sum(row["target_match"] is True for row in level_rows),
            "match_rate": (
                sum(row["target_match"] is True for row in level_rows)
                / len(level_rows)
                if level_rows
                else None
            ),
            "score_mean": mean_score,
            "score_min": float(np.min(scores)) if scores else None,
            "score_max": float(np.max(scores)) if scores else None,
            "observed_distribution": dict(observed_counts),
        }

    target_indices = np.asarray(
        [RISK_INDEX[row["target_risk_level"]] for row in completed],
        dtype=np.float64,
    )
    observed_indices = np.asarray(
        [RISK_INDEX[row["observed_risk_level"]] for row in completed],
        dtype=np.float64,
    )
    scores = np.asarray([row["risk_score"] for row in completed], dtype=np.float64)
    if len(completed) >= 2 and np.std(target_indices) > 0 and np.std(scores) > 0:
        target_score_correlation = float(np.corrcoef(target_indices, scores)[0, 1])
    else:
        target_score_correlation = None

    ordered_means = [per_level[level]["score_mean"] for level in RISK_LEVELS]
    monotonic = (
        all(value is not None for value in ordered_means)
        and all(left < right for left, right in zip(ordered_means, ordered_means[1:]))
    )
    return {
        "total": len(rows),
        "completed": len(completed),
        "failed": sum(row["status"] == "failed" for row in rows),
        "missing": sum(row["status"] == "missing" for row in rows),
        "sensor_completed": sum(row.get("sensor_status") == "completed" for row in rows),
        "server_healthy": sum(row.get("server_status") == "healthy" for row in rows),
        "collision_events": sum(row.get("collision_count") or 0 for row in completed),
        "collision_runs": sum((row.get("collision_count") or 0) > 0 for row in completed),
        "target_level_matches": sum(row["target_match"] is True for row in completed),
        "target_level_match_rate": (
            sum(row["target_match"] is True for row in completed) / len(completed)
            if completed
            else None
        ),
        "ordinal_mean_absolute_error": (
            float(np.mean(np.abs(observed_indices - target_indices)))
            if completed
            else None
        ),
        "ordinal_mean_bias": (
            float(np.mean(observed_indices - target_indices))
            if completed
            else None
        ),
        "target_score_correlation": target_score_correlation,
        "mean_scores_strictly_increasing": monotonic,
        "per_target_level": per_level,
    }


def format_number(value, digits=3):
    return "-" if value is None else f"{value:.{digits}f}"


def write_markdown(path, analysis, source_path):
    lines = [
        "# CVAE CARLA 实测分析",
        "",
        f"- 数据源：`{source_path}`",
        f"- 完成：`{analysis['completed']}/{analysis['total']}`",
        f"- 目标档位命中率：`{format_number(analysis['target_level_match_rate'])}`",
        f"- 档位序数平均绝对误差：`{format_number(analysis['ordinal_mean_absolute_error'])}`",
        f"- 目标档位与实测分数相关系数：`{format_number(analysis['target_score_correlation'])}`",
        f"- 四档平均分严格递增：`{analysis['mean_scores_strictly_increasing']}`",
        f"- 碰撞运行：`{analysis['collision_runs']}`，碰撞事件：`{analysis['collision_events']}`",
        "",
        "| 目标档 | 完成 | 命中率 | 平均分 | 最低分 | 最高分 | 实测档分布 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for level in RISK_LEVELS:
        item = analysis["per_target_level"][level]
        distribution = ", ".join(
            f"{name}:{count}"
            for name, count in sorted(
                item["observed_distribution"].items(),
                key=lambda pair: RISK_INDEX[pair[0]],
            )
        ) or "-"
        lines.append(
            f"| {level} | {item['completed']}/{item['planned']} | "
            f"{format_number(item['match_rate'])} | "
            f"{format_number(item['score_mean'])} | "
            f"{format_number(item['score_min'])} | "
            f"{format_number(item['score_max'])} | {distribution} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 本报告分析 `heuristic_v2` 实测结果，不把 `target_risk_level` 当作真实标签。",
            "- 每档 3 条仍属于小样本工程验证，只用于发现系统偏差和决定是否扩大实验。",
            "- Traffic Manager 单种子结果不能估计场景重复性；稳定性需要下一轮多种子运行。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def write_analysis(result_csv, output_dir=None):
    result_csv = os.path.abspath(result_csv)
    output_dir = os.path.abspath(output_dir or os.path.dirname(result_csv))
    os.makedirs(output_dir, exist_ok=True)
    analysis = analyze_rows(load_rows(result_csv))
    json_path = os.path.join(output_dir, "validation_analysis.json")
    markdown_path = os.path.join(output_dir, "validation_analysis.md")
    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(analysis, file, ensure_ascii=False, indent=2)
    write_markdown(markdown_path, analysis, result_csv)
    return analysis, json_path, markdown_path


def main():
    parser = argparse.ArgumentParser(description="分析 CARLA 生成场景实测结果")
    parser.add_argument("result_csv")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    analysis, json_path, markdown_path = write_analysis(
        args.result_csv,
        args.output_dir,
    )
    print(
        f"[ANALYZE] completed={analysis['completed']}/{analysis['total']} | "
        f"match_rate={analysis['target_level_match_rate']}"
    )
    print(f"[ANALYZE] JSON: {json_path}")
    print(f"[ANALYZE] 报告: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
