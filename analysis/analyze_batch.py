"""离线复算批次风险 V2，并生成统计表、图表和分析报告。"""

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.risk_metrics import evaluate_risk_v2  # noqa: E402


COMPONENT_NAMES = (
    "collision",
    "ttc",
    "lead_gap",
    "pedestrian_distance",
    "pedestrian_speed",
    "weather_visibility",
)

RUN_FIELDS = [
    "variant",
    "repeat_index",
    "traffic_manager_seed",
    "run_dir",
    "original_method",
    "original_score",
    "original_level",
    "risk_v2_score",
    "risk_v2_level",
    "score_delta_v2_minus_original",
    "collision_count",
    "minimum_ttc_seconds",
    "minimum_lead_gap_m",
    "minimum_pedestrian_distance_m",
    "pedestrian_speed_mps",
    "pedestrian_crossing_duration_seconds",
    "lead_brake_elapsed_seconds",
    "minimum_ttc_after_brake_seconds",
    "minimum_gap_after_brake_m",
    "fog_density",
    "fog_distance_m",
    "precipitation",
    "sun_altitude_angle",
]
for component_name in COMPONENT_NAMES:
    RUN_FIELDS.extend(
        [
            f"component_{component_name}",
            f"contribution_{component_name}_points",
        ]
    )

SUMMARY_FIELDS = [
    "rank",
    "variant",
    "completed_runs",
    "risk_v2_score_mean",
    "risk_v2_score_std",
    "risk_v2_score_min",
    "risk_v2_score_max",
    "original_score_mean",
    "score_delta_mean",
    "dominant_risk_level",
    "risk_level_counts",
    "minimum_ttc_seconds_mean",
    "minimum_lead_gap_m_mean",
    "minimum_pedestrian_distance_m_mean",
    "pedestrian_speed_mps_mean",
    "weather_visibility_component_mean",
]
for component_name in COMPONENT_NAMES:
    SUMMARY_FIELDS.append(f"component_{component_name}_mean")
    SUMMARY_FIELDS.append(f"contribution_{component_name}_points_mean")


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rounded(value, digits=3):
    if value is None:
        return ""
    return round(float(value), digits)


def numeric_values(rows, field_name):
    values = [as_float(row.get(field_name)) for row in rows]
    return [value for value in values if value is not None]


def mean_std(rows, field_name):
    values = numeric_values(rows, field_name)
    if not values:
        return "", ""
    mean_value = round(statistics.fmean(values), 3)
    std_value = round(statistics.stdev(values), 3) if len(values) > 1 else 0.0
    return mean_value, std_value


def dominant_level(rows):
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    counts = Counter(row["risk_v2_level"] for row in rows)
    level = max(counts, key=lambda name: (counts[name], order.get(name, -1)))
    return level, dict(sorted(counts.items()))


def analyze_run(summary_row, risk_config):
    run_dir = summary_row["run_dir"]
    metadata = load_json(os.path.join(run_dir, "metadata.json"))
    run_config = load_json(os.path.join(run_dir, "config_snapshot.json"))
    telemetry_rows = read_csv(os.path.join(run_dir, "telemetry.csv"))
    original_risk = metadata.get("result", {}).get("risk_evaluation") or {}
    collision_count = int(metadata.get("result", {}).get("collision_count", 0))

    risk_v2 = evaluate_risk_v2(
        telemetry_rows,
        collision_count,
        risk_config,
        weather_config=run_config.get("weather"),
        pedestrian_config=run_config.get("pedestrian"),
        scenario_config=run_config.get("scenario"),
        events=metadata.get("events"),
    )
    diagnostics = risk_v2["diagnostics"]
    weather = run_config.get("weather", {})
    original_score = as_float(original_risk.get("score"))
    total_weight = sum(float(value) for value in risk_v2["weights"].values())

    row = {
        "variant": summary_row["variant"],
        "repeat_index": summary_row.get("repeat_index", ""),
        "traffic_manager_seed": summary_row.get("traffic_manager_seed", ""),
        "run_dir": run_dir,
        "original_method": original_risk.get("method", ""),
        "original_score": rounded(original_score),
        "original_level": original_risk.get("level", ""),
        "risk_v2_score": risk_v2["score"],
        "risk_v2_level": risk_v2["level"],
        "score_delta_v2_minus_original": (
            rounded(risk_v2["score"] - original_score)
            if original_score is not None
            else ""
        ),
        "collision_count": collision_count,
        "minimum_ttc_seconds": rounded(diagnostics["minimum_ttc_seconds"]),
        "minimum_lead_gap_m": rounded(diagnostics["minimum_lead_gap_m"]),
        "minimum_pedestrian_distance_m": rounded(
            diagnostics["minimum_pedestrian_distance_m"]
        ),
        "pedestrian_speed_mps": rounded(diagnostics["pedestrian_speed_mps"]),
        "pedestrian_crossing_duration_seconds": rounded(
            diagnostics["pedestrian_crossing_duration_seconds"]
        ),
        "lead_brake_elapsed_seconds": rounded(
            diagnostics["lead_brake_elapsed_seconds"]
        ),
        "minimum_ttc_after_brake_seconds": rounded(
            diagnostics["minimum_ttc_after_brake_seconds"]
        ),
        "minimum_gap_after_brake_m": rounded(
            diagnostics["minimum_gap_after_brake_m"]
        ),
        "fog_density": rounded(weather.get("fog_density")),
        "fog_distance_m": rounded(weather.get("fog_distance")),
        "precipitation": rounded(weather.get("precipitation")),
        "sun_altitude_angle": rounded(weather.get("sun_altitude_angle")),
    }
    for component_name in COMPONENT_NAMES:
        component_value = float(risk_v2["components"][component_name])
        component_weight = float(risk_v2["weights"][component_name])
        row[f"component_{component_name}"] = round(component_value, 4)
        row[f"contribution_{component_name}_points"] = round(
            100.0 * component_value * component_weight / total_weight,
            3,
        )
    return row


def aggregate_runs(run_rows):
    grouped = defaultdict(list)
    for row in run_rows:
        grouped[row["variant"]].append(row)

    summaries = []
    for variant, rows in grouped.items():
        score_values = numeric_values(rows, "risk_v2_score")
        score_mean, score_std = mean_std(rows, "risk_v2_score")
        original_mean, _ = mean_std(rows, "original_score")
        delta_mean, _ = mean_std(rows, "score_delta_v2_minus_original")
        level, level_counts = dominant_level(rows)
        summary = {
            "rank": 0,
            "variant": variant,
            "completed_runs": len(rows),
            "risk_v2_score_mean": score_mean,
            "risk_v2_score_std": score_std,
            "risk_v2_score_min": round(min(score_values), 3),
            "risk_v2_score_max": round(max(score_values), 3),
            "original_score_mean": original_mean,
            "score_delta_mean": delta_mean,
            "dominant_risk_level": level,
            "risk_level_counts": json.dumps(
                level_counts,
                ensure_ascii=False,
                sort_keys=True,
            ),
        }
        for field_name in (
            "minimum_ttc_seconds",
            "minimum_lead_gap_m",
            "minimum_pedestrian_distance_m",
            "pedestrian_speed_mps",
            "component_weather_visibility",
        ):
            mean_value, _ = mean_std(rows, field_name)
            output_name = (
                "weather_visibility_component_mean"
                if field_name == "component_weather_visibility"
                else f"{field_name}_mean"
            )
            summary[output_name] = mean_value
        for component_name in COMPONENT_NAMES:
            component_mean, _ = mean_std(
                rows,
                f"component_{component_name}",
            )
            contribution_mean, _ = mean_std(
                rows,
                f"contribution_{component_name}_points",
            )
            summary[f"component_{component_name}_mean"] = component_mean
            summary[
                f"contribution_{component_name}_points_mean"
            ] = contribution_mean
        summaries.append(summary)

    summaries.sort(
        key=lambda row: float(row["risk_v2_score_mean"]),
        reverse=True,
    )
    for rank, summary in enumerate(summaries, 1):
        summary["rank"] = rank
    return summaries


def score_color(score):
    if score >= 75:
        return "#b91c1c"
    if score >= 50:
        return "#ea580c"
    if score >= 25:
        return "#d4a017"
    return "#15803d"


def plot_scores(summary_rows, output_path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    variants = [row["variant"] for row in summary_rows]
    means = [float(row["risk_v2_score_mean"]) for row in summary_rows]
    stds = [float(row["risk_v2_score_std"]) for row in summary_rows]
    colors = [score_color(score) for score in means]

    figure, axis = plt.subplots(figsize=(10, 5.5))
    bars = axis.bar(variants, means, yerr=stds, capsize=5, color=colors)
    axis.set_ylim(0, 100)
    axis.set_ylabel("Risk score (0-100)")
    axis.set_title("Heuristic V2 risk by scenario variant")
    axis.grid(axis="y", alpha=0.25)
    axis.axhline(25, color="#d4a017", linewidth=1, linestyle="--")
    axis.axhline(50, color="#ea580c", linewidth=1, linestyle="--")
    axis.axhline(75, color="#b91c1c", linewidth=1, linestyle="--")
    axis.tick_params(axis="x", rotation=20)
    for bar, value in zip(bars, means):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def plot_components(summary_rows, output_path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    variants = [row["variant"] for row in summary_rows]
    palette = {
        "collision": "#7f1d1d",
        "ttc": "#dc2626",
        "lead_gap": "#f97316",
        "pedestrian_distance": "#eab308",
        "pedestrian_speed": "#84cc16",
        "weather_visibility": "#2563eb",
    }
    labels = {
        "collision": "Collision",
        "ttc": "TTC",
        "lead_gap": "Lead gap",
        "pedestrian_distance": "Pedestrian distance",
        "pedestrian_speed": "Pedestrian speed",
        "weather_visibility": "Weather visibility",
    }
    bottoms = [0.0] * len(summary_rows)

    figure, axis = plt.subplots(figsize=(10, 6))
    for component_name in COMPONENT_NAMES:
        values = [
            float(row[f"contribution_{component_name}_points_mean"])
            for row in summary_rows
        ]
        axis.bar(
            variants,
            values,
            bottom=bottoms,
            color=palette[component_name],
            label=labels[component_name],
        )
        bottoms = [left + right for left, right in zip(bottoms, values)]

    axis.set_ylim(0, 100)
    axis.set_ylabel("Weighted contribution (score points)")
    axis.set_title("Heuristic V2 component contributions")
    axis.tick_params(axis="x", rotation=20)
    axis.grid(axis="y", alpha=0.2)
    axis.legend(loc="upper right", fontsize=8)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def format_number(value):
    if value in (None, ""):
        return "-"
    return f"{float(value):.3f}"


def build_findings(summary_rows):
    by_variant = {row["variant"]: row for row in summary_rows}
    findings = []
    highest = summary_rows[0]
    findings.append(
        f"V2 平均风险最高的是 `{highest['variant']}`，"
        f"得分为 {format_number(highest['risk_v2_score_mean'])}。"
    )

    baseline = by_variant.get("baseline")
    dense_fog = by_variant.get("dense_fog")
    if baseline and dense_fog:
        delta = float(dense_fog["risk_v2_score_mean"]) - float(
            baseline["risk_v2_score_mean"]
        )
        findings.append(
            f"`dense_fog` 相对 baseline 的 V2 平均分变化为 {delta:+.3f}，"
            "天气可见度代理已进入评分，能够区分额外浓雾暴露。"
        )

    fast_pedestrian = by_variant.get("fast_pedestrian")
    if baseline and fast_pedestrian:
        delta = float(fast_pedestrian["risk_v2_score_mean"]) - float(
            baseline["risk_v2_score_mean"]
        )
        findings.append(
            f"`fast_pedestrian` 相对 baseline 的 V2 平均分变化为 {delta:+.3f}，"
            "行人速度不再被最小距离指标完全掩盖。"
        )

    late_braking = by_variant.get("late_braking")
    if late_braking:
        findings.append(
            f"`late_braking` 的标准差为 "
            f"{format_number(late_braking['risk_v2_score_std'])}，"
            "若仍明显高于其他变体，应继续按随机种子检查交通流波动。"
        )
    return findings


def write_report(
    path,
    batch_dir,
    risk_config_path,
    batch_rows,
    run_rows,
    summary_rows,
    output_dir,
):
    completed_count = len(run_rows)
    planned_count = len(batch_rows)
    weights = load_json(risk_config_path)["risk_evaluation"]["v2"]["weights"]
    findings = build_findings(summary_rows)

    lines = [
        "# CARLA 批次风险指标 V2 分析报告",
        "",
        f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 批次目录：`{batch_dir}`",
        f"- 风险配置：`{risk_config_path}`",
        f"- 可分析运行：`{completed_count}/{planned_count}`",
        "- 方法：`heuristic_v2`，用于同一场景族内部工程筛选",
        "",
        "## 指标结构",
        "",
        "| 指标 | 权重 | 含义 |",
        "|---|---:|---|",
        f"| Collision | {weights['collision']:.2f} | 是否发生碰撞 |",
        f"| TTC | {weights['ttc']:.2f} | 最小碰撞时间风险 |",
        f"| Lead gap | {weights['lead_gap']:.2f} | 最小前车净间距风险 |",
        f"| Pedestrian distance | {weights['pedestrian_distance']:.2f} | 最小人车距离风险 |",
        f"| Pedestrian speed | {weights['pedestrian_speed']:.2f} | 行人横穿速度风险 |",
        f"| Weather visibility | {weights['weather_visibility']:.2f} | 雾、降雨和夜间暴露代理 |",
        "",
        "## 变体结果",
        "",
        "| 排名 | 变体 | V2均值 | 标准差 | 原评分均值 | 等级 | 最小TTC均值 | 最小间距均值 |",
        "|---:|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {rank} | {variant} | {v2_mean} | {v2_std} | {old_mean} | "
            "{level} | {ttc} | {gap} |".format(
                rank=row["rank"],
                variant=row["variant"],
                v2_mean=format_number(row["risk_v2_score_mean"]),
                v2_std=format_number(row["risk_v2_score_std"]),
                old_mean=format_number(row["original_score_mean"]),
                level=row["dominant_risk_level"],
                ttc=format_number(row["minimum_ttc_seconds_mean"]),
                gap=format_number(row["minimum_lead_gap_m_mean"]),
            )
        )

    lines.extend(["", "## 主要发现", ""])
    lines.extend(f"- {finding}" for finding in findings)
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 天气可见度是根据 CARLA 天气参数计算的暴露代理，不是从 RGB 图像测得的真实能见度。",
            "- 当前每个变体只有 3 个随机种子，均值和标准差适合 Demo 对比，不足以形成统计显著性结论。",
            "- V2 是透明的启发式指标，不等同于 ISO 26262、SOTIF 或法规认证指标。",
            "",
            "## 输出文件",
            "",
            f"- 逐次结果：`{os.path.join(output_dir, 'risk_v2_runs.csv')}`",
            f"- 聚合统计：`{os.path.join(output_dir, 'risk_v2_summary.csv')}`",
            f"- 风险排名图：`{os.path.join(output_dir, 'risk_v2_scores.png')}`",
            f"- 组成贡献图：`{os.path.join(output_dir, 'risk_v2_components.png')}`",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="离线复算 CARLA 批次风险 V2 并生成分析结果",
    )
    parser.add_argument("--batch-dir", required=True, help="批次运行目录")
    parser.add_argument(
        "--config",
        default=os.path.join(
            PROJECT_ROOT,
            "configs",
            "multi_hazard_rainy_night.json",
        ),
        help="包含 risk_evaluation.v2 的配置文件",
    )
    parser.add_argument(
        "--output-dir",
        help="分析输出目录，默认位于批次目录下 risk_v2_analysis",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="仅生成 CSV 和 Markdown，不生成 PNG 图表",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    batch_dir = os.path.abspath(args.batch_dir)
    risk_config_path = os.path.abspath(args.config)
    output_dir = os.path.abspath(
        args.output_dir or os.path.join(batch_dir, "risk_v2_analysis")
    )
    os.makedirs(output_dir, exist_ok=True)

    batch_summary_path = os.path.join(batch_dir, "batch_summary.csv")
    batch_rows = read_csv(batch_summary_path)
    risk_config = load_json(risk_config_path)["risk_evaluation"]
    completed_rows = [row for row in batch_rows if row["status"] == "completed"]
    run_rows = [analyze_run(row, risk_config) for row in completed_rows]
    summary_rows = aggregate_runs(run_rows)

    runs_path = os.path.join(output_dir, "risk_v2_runs.csv")
    summary_path = os.path.join(output_dir, "risk_v2_summary.csv")
    report_path = os.path.join(output_dir, "risk_v2_report.md")
    write_csv(runs_path, RUN_FIELDS, run_rows)
    write_csv(summary_path, SUMMARY_FIELDS, summary_rows)

    if not args.no_plots:
        plot_scores(summary_rows, os.path.join(output_dir, "risk_v2_scores.png"))
        plot_components(
            summary_rows,
            os.path.join(output_dir, "risk_v2_components.png"),
        )

    write_report(
        report_path,
        batch_dir,
        risk_config_path,
        batch_rows,
        run_rows,
        summary_rows,
        output_dir,
    )
    print(f"[ANALYSIS] 运行数: {len(run_rows)}/{len(batch_rows)}")
    print(f"[ANALYSIS] 逐次结果: {runs_path}")
    print(f"[ANALYSIS] 聚合统计: {summary_path}")
    print(f"[ANALYSIS] 分析报告: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
