"""Calibrate the frozen LHS/high proxy against independent CARLA evidence.

The independent candidate runs are the calibration unit. Repeated Traffic
Manager measurements are reported separately as directional evidence only.
"""

import argparse
import csv
import json
import math
import os
import statistics
from datetime import datetime


LEVELS = ("low", "medium", "high", "critical")
LEVEL_INDEX = {level: index for index, level in enumerate(LEVELS)}
THRESHOLDS = {"medium": 25.0, "high": 50.0, "critical": 75.0}


def _rounded(value, digits=6):
    return None if value is None else round(float(value), digits)


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_csv(path, rows):
    if not rows:
        raise ValueError("Cannot write an empty CSV")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _load_json_rows(paths):
    rows = []
    for path in paths:
        with open(os.path.abspath(path), "r", encoding="utf-8") as file:
            value = json.load(file)
        if isinstance(value, dict):
            value = value.get("runs")
        if not isinstance(value, list) or not value:
            raise ValueError(f"Independent results must contain a non-empty list: {path}")
        rows.extend(value)
    return rows


def _load_csv(path):
    with open(os.path.abspath(path), "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _as_float(value, field):
    if value in (None, "", "null"):
        raise ValueError(f"Missing numeric field: {field}")
    return float(value)


def score_to_level(score):
    score = float(score)
    if score >= THRESHOLDS["critical"]:
        return "critical"
    if score >= THRESHOLDS["high"]:
        return "high"
    if score >= THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _rank_descending(values):
    ordered = sorted(enumerate(values), key=lambda item: (-item[1], item[0]))
    ranks = [0] * len(values)
    for rank, (index, _) in enumerate(ordered, 1):
        ranks[index] = rank
    return ranks


def _spearman(x, y):
    if len(x) != len(y) or len(x) < 2:
        return None
    xr = _rank_descending(x)
    yr = _rank_descending(y)
    n = len(xr)
    denominator = n * (n * n - 1)
    if denominator == 0:
        return None
    return 1.0 - 6.0 * sum((a - b) ** 2 for a, b in zip(xr, yr)) / denominator


def _kendall_tau(x, y):
    concordant = discordant = ties = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            first = (x[i] - x[j]) * (y[i] - y[j])
            if first > 0:
                concordant += 1
            elif first < 0:
                discordant += 1
            else:
                ties += 1
    denominator = concordant + discordant + ties
    return None if denominator == 0 else (concordant - discordant) / denominator


def _confusion(predicted, observed):
    return {
        "true_positive": sum(bool(p) and bool(o) for p, o in zip(predicted, observed)),
        "true_negative": sum(not p and not o for p, o in zip(predicted, observed)),
        "false_positive": sum(bool(p) and not o for p, o in zip(predicted, observed)),
        "false_negative": sum(not p and bool(o) for p, o in zip(predicted, observed)),
    }


def _rates(confusion):
    tp = confusion["true_positive"]
    tn = confusion["true_negative"]
    fp = confusion["false_positive"]
    fn = confusion["false_negative"]
    return {
        "accuracy": _rounded((tp + tn) / max(tp + tn + fp + fn, 1)),
        "precision": _rounded(tp / (tp + fp)) if tp + fp else None,
        "recall": _rounded(tp / (tp + fn)) if tp + fn else None,
        "specificity": _rounded(tn / (tn + fp)) if tn + fp else None,
    }


def _validate_independent_row(row):
    if row.get("strict_acceptance_passed") is not True:
        raise ValueError(f"Independent run failed strict acceptance: {row.get('run_id')}")
    if row.get("risk_method") != "heuristic_v2":
        raise ValueError(f"Unexpected risk method for {row.get('run_id')}: {row.get('risk_method')}")
    if row.get("carla_client_version") != "0.9.16" or row.get("carla_server_version") != "0.9.16":
        raise ValueError(f"CARLA version mismatch for {row.get('run_id')}")
    metadata = row.get("selection_metadata") or {}
    return {
        "sample_id": row["sample_id"],
        "proxy_robust_score": _as_float(metadata.get("robust_predicted_risk_score"), "robust_predicted_risk_score"),
        "proxy_risk_mean": _as_float(metadata.get("predicted_risk_mean"), "predicted_risk_mean"),
        "proxy_risk_std": _as_float(metadata.get("predicted_risk_std"), "predicted_risk_std"),
        "proxy_collision_probability": _as_float(metadata.get("predicted_collision_probability_mean"), "predicted_collision_probability_mean"),
        "proxy_collision_boundary_score": _as_float(metadata.get("collision_boundary_score"), "collision_boundary_score"),
        "observed_risk_score": _as_float(row.get("risk_score"), "risk_score"),
        "observed_risk_level": row.get("observed_risk_level"),
        "collision_observed": bool(row.get("collision_observed")) or int(row.get("collision_count") or 0) > 0,
        "collision_count": int(row.get("collision_count") or 0),
        "selection_reason": metadata.get("reason"),
    }


def build_independent_calibration(rows, ranked_rows=None):
    if not rows:
        raise ValueError("At least one independent runtime row is required")
    normalized = [_validate_independent_row(row) for row in rows]
    ids = [row["sample_id"] for row in normalized]
    if len(set(ids)) != len(ids):
        raise ValueError("Independent calibration rows contain duplicate sample_id")
    if ranked_rows is not None:
        ranked_by_id = {row["sample_id"]: row for row in ranked_rows}
        missing = sorted(set(ids) - set(ranked_by_id))
        if missing:
            raise ValueError(f"Candidates missing from ranked proxy table: {missing}")

    proxy_scores = [row["proxy_robust_score"] for row in normalized]
    observed_scores = [row["observed_risk_score"] for row in normalized]
    proxy_probabilities = [row["proxy_collision_probability"] for row in normalized]
    collisions = [row["collision_observed"] for row in normalized]
    predicted_levels = [score_to_level(score) for score in proxy_scores]
    observed_levels = [row["observed_risk_level"] for row in normalized]
    if any(level not in LEVEL_INDEX for level in observed_levels):
        raise ValueError("Observed risk levels must be one of low/medium/high/critical")

    risk_errors = [observed - proxy for observed, proxy in zip(observed_scores, proxy_scores)]
    proxy_ranks = _rank_descending(proxy_scores)
    observed_ranks = _rank_descending(observed_scores)
    calibration_rows = []
    for row, predicted_level, proxy_rank, observed_rank, error in zip(
        normalized, predicted_levels, proxy_ranks, observed_ranks, risk_errors
    ):
        proxy_score = row["proxy_robust_score"]
        calibration_rows.append({
            **row,
            "proxy_predicted_level": predicted_level,
            "proxy_rank_descending": proxy_rank,
            "observed_rank_descending": observed_rank,
            "rank_displacement": observed_rank - proxy_rank,
            "risk_error_observed_minus_proxy": _rounded(error),
            "absolute_risk_error": _rounded(abs(error)),
            "ordinal_level_error": abs(LEVEL_INDEX[predicted_level] - LEVEL_INDEX[row["observed_risk_level"]]),
            "proxy_danger_prediction": proxy_score >= THRESHOLDS["high"],
            "observed_danger": row["observed_risk_score"] >= THRESHOLDS["high"],
            "collision_probability_prediction": row["proxy_collision_probability"] >= 0.5,
        })

    danger_confusion = _confusion(
        [row["proxy_danger_prediction"] for row in calibration_rows],
        [row["observed_danger"] for row in calibration_rows],
    )
    collision_confusion = _confusion(
        [row["collision_probability_prediction"] for row in calibration_rows],
        collisions,
    )
    brier = statistics.fmean(
        (probability - float(actual)) ** 2
        for probability, actual in zip(proxy_probabilities, collisions)
    )
    summary = {
        "sample_count": len(normalized),
        "sample_ids": ids,
        "risk_score": {
            "mae": _rounded(statistics.fmean(abs(value) for value in risk_errors)),
            "rmse": _rounded(math.sqrt(statistics.fmean(value * value for value in risk_errors))),
            "bias_observed_minus_proxy": _rounded(statistics.fmean(risk_errors)),
            "spearman_rho": _rounded(_spearman(proxy_scores, observed_scores)),
            "kendall_tau": _rounded(_kendall_tau(proxy_scores, observed_scores)),
            "exact_level_match_count": sum(a == b for a, b in zip(predicted_levels, observed_levels)),
            "within_one_level_count": sum(
                abs(LEVEL_INDEX[a] - LEVEL_INDEX[b]) <= 1
                for a, b in zip(predicted_levels, observed_levels)
            ),
        },
        "danger_threshold_high": {
            "threshold": THRESHOLDS["high"],
            **danger_confusion,
            **_rates(danger_confusion),
        },
        "collision_probability": {
            "threshold": 0.5,
            "brier_score": _rounded(brier),
            "mae": _rounded(statistics.fmean(abs(probability - float(actual)) for probability, actual in zip(proxy_probabilities, collisions))),
            **collision_confusion,
            **_rates(collision_confusion),
        },
        "interpretation_boundary": "Descriptive calibration only. The independent sample is too small for inferential claims, confidence intervals, or proxy retraining decisions.",
    }
    return summary, calibration_rows


def summarize_repeat_direction(proxy_rows, repeat_rows):
    if not proxy_rows or not repeat_rows:
        raise ValueError("Both proxy and repeated measurement rows are required")
    proxy = {row["strategy"]: _as_float(row.get("proxy_score_delta"), "proxy_score_delta") for row in proxy_rows}
    grouped = {}
    for row in repeat_rows:
        strategy = row.get("strategy")
        grouped.setdefault(strategy, []).append(_as_float(row.get("risk_delta"), "risk_delta"))
    rows = []
    for strategy, deltas in sorted(grouped.items()):
        if strategy not in proxy:
            continue
        mean_measured = statistics.fmean(deltas)
        proxy_delta = proxy[strategy]
        rows.append({
            "strategy": strategy,
            "repeat_measurement_count": len(deltas),
            "proxy_score_delta": _rounded(proxy_delta),
            "measured_risk_delta_mean": _rounded(mean_measured),
            "measured_risk_delta_median": _rounded(statistics.median(deltas)),
            "delta_amplification_measured_over_proxy": _rounded(mean_measured / proxy_delta) if proxy_delta else None,
            "measured_risk_increase_count": sum(delta > 0 for delta in deltas),
            "collision_introduced_count": sum(row.get("collision_change") == "introduced" for row in repeat_rows if row.get("strategy") == strategy),
        })
    if not rows:
        raise ValueError("No overlapping strategy rows between proxy and repeated measurements")
    proxy_order = [row["strategy"] for row in sorted(rows, key=lambda row: row["proxy_score_delta"], reverse=True)]
    measured_order = [row["strategy"] for row in sorted(rows, key=lambda row: row["measured_risk_delta_mean"], reverse=True)]
    return {
        "strategies": rows,
        "proxy_order_descending": proxy_order,
        "measured_order_descending": measured_order,
        "direction_consistent": proxy_order == measured_order,
        "interpretation_boundary": "Repeated Traffic Manager seeds reuse one source scene and are directional evidence, not additional independent calibration samples.",
    }


def calibrate(
    independent_rows,
    ranked_rows,
    proxy_rows,
    repeat_rows,
    calibration_format="lhs_high_proxy_calibration_v1",
):
    independent_summary, calibration_rows = build_independent_calibration(independent_rows, ranked_rows)
    repeat_summary = summarize_repeat_direction(proxy_rows, repeat_rows)
    summary = {
        "format": calibration_format,
        "evidence_kind": "offline_calibration_with_carla_runtime_inputs",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_mode": "offline_cpu_only",
        "independent_calibration": independent_summary,
        "repeated_direction_check": repeat_summary,
        "conclusion": {
            "proxy_usable_for_screening": True,
            "proxy_usable_as_measured_risk": False,
            "proxy_usable_for_online_training_reward": False,
            "reason": "The small independent set preserves a useful danger ordering but shows score bias and collision-boundary misses; keep the proxy as a screening signal only until more independent evidence is collected.",
        },
    }
    return summary, calibration_rows


def _report(summary, rows):
    independent = summary["independent_calibration"]
    collision = independent["collision_probability"]
    lines = [
        f"# LHS/high 风险代理校准 {summary.get('calibration_version', 'V1')}",
        "",
        "## 证据口径",
        "",
        f"- 独立校准样本：`{independent['sample_count']}` 条。",
        "- 重复 Traffic Manager 测量单独用于方向检查，不计入独立样本量。",
        "- 本轮为 CPU-only 离线分析，不启动 CARLA、不启动在线训练。",
        "",
        "## 独立样本校准结果",
        "",
        "| sample_id | 选择理由 | 代理稳健分 | 实测分 | 代理档位 | 实测档位 | 风险误差 | 预测碰撞概率 | 实测碰撞 |",
        "|---|---|---:|---:|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} | {row.get('selection_reason') or ''} | "
            f"{row['proxy_robust_score']:.3f} | {row['observed_risk_score']:.3f} | "
            f"{row['proxy_predicted_level']} | {row['observed_risk_level']} | "
            f"{row['risk_error_observed_minus_proxy']:+.3f} | "
            f"{row['proxy_collision_probability']:.3f} | "
            f"{'yes' if row['collision_observed'] else 'no'} |"
        )
    lines.extend([
        "",
        f"风险 MAE `{independent['risk_score']['mae']:.3f}`，RMSE `{independent['risk_score']['rmse']:.3f}`，",
        f"实测分相对代理分平均偏差 `{independent['risk_score']['bias_observed_minus_proxy']:+.3f}`；",
        f"Spearman `rho={independent['risk_score']['spearman_rho']:.3f}`，Kendall `tau={independent['risk_score']['kendall_tau']:.3f}`。",
        f"high 以上危险筛选准确率 `{independent['danger_threshold_high']['accuracy']:.3f}`；",
        f"碰撞概率 Brier 分数 `{collision['brier_score']:.3f}`，0.5 阈值召回率 `{collision['recall'] if collision['recall'] is not None else 'n/a'}`。",
        "",
        "## 重复方向检查",
        "",
        f"代理增量排序：`{' > '.join(summary['repeated_direction_check']['proxy_order_descending'])}`；",
        f"重复实测增量排序：`{' > '.join(summary['repeated_direction_check']['measured_order_descending'])}`；",
        f"方向一致：`{summary['repeated_direction_check']['direction_consistent']}`。",
        "重复种子结果只说明同一源场景上的方向关系，不提供新的独立样本量。",
        "",
        "## 决策",
        "",
        "当前代理可以继续用于候选筛选和边界观察，但不能直接当作 CARLA 实测风险，也不能作为在线训练 reward。下一轮若继续，只增加未使用的独立场景并保持相同严格验收门。",
        "",
    ])
    return "\n".join(lines)


def run_calibration(
    independent_paths,
    ranked_path,
    proxy_path,
    repeat_path,
    output_dir,
    calibration_format="lhs_high_proxy_calibration_v1",
):
    independent_rows = _load_json_rows(independent_paths)
    ranked_rows = _load_csv(ranked_path)
    proxy_rows = _load_csv(proxy_path)
    repeat_rows = [
        row for row in _load_csv(repeat_path)
        if row.get("generator") == "lhs"
        and row.get("target_risk_level") == "high"
    ]
    if not repeat_rows:
        raise ValueError("No LHS/high repeated measurements found")
    summary, calibration_rows = calibrate(
        independent_rows,
        ranked_rows,
        proxy_rows,
        repeat_rows,
        calibration_format=calibration_format,
    )
    summary["calibration_version"] = calibration_format.rsplit("_", 1)[-1].upper()
    os.makedirs(os.path.abspath(output_dir), exist_ok=False)
    _write_json(os.path.join(output_dir, "summary.json"), summary)
    _write_csv(os.path.join(output_dir, "independent_calibration.csv"), calibration_rows)
    _write_csv(os.path.join(output_dir, "repeat_direction_check.csv"), summary["repeated_direction_check"]["strategies"])
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8", newline="\n") as file:
        file.write(_report(summary, calibration_rows))
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--independent-results", action="append", required=True)
    parser.add_argument("--ranked-candidates", required=True)
    parser.add_argument("--runtime-proxy-comparison", required=True)
    parser.add_argument("--repeat-comparisons", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--calibration-format",
        default="lhs_high_proxy_calibration_v1",
        choices=("lhs_high_proxy_calibration_v1", "lhs_high_proxy_calibration_v2"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    summary = run_calibration(
        args.independent_results,
        args.ranked_candidates,
        args.runtime_proxy_comparison,
        args.repeat_comparisons,
        args.output_dir,
        calibration_format=args.calibration_format,
    )
    print(
        f"[CALIBRATION] independent={summary['independent_calibration']['sample_count']} "
        f"spearman={summary['independent_calibration']['risk_score']['spearman_rho']} "
        f"brier={summary['independent_calibration']['collision_probability']['brier_score']}",
        flush=True,
    )
    print(f"[RESULT_DIR] {os.path.abspath(args.output_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
