"""Analyze paired CARLA results for the four non-learning baselines."""

import argparse
import csv
import json
import os
import statistics
from collections import Counter
from datetime import datetime


EXPECTED_STRATEGIES = ("fixed", "random", "lhs", "rule_guided_lhs")


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_csv(path, rows):
    if not rows:
        raise ValueError("Cannot write an empty CSV")
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _rounded(value, digits=6):
    return round(float(value), digits)


def analyze_results(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Runtime results must be a non-empty list")
    pair_ids = list(dict.fromkeys(row["pair_id"] for row in rows))
    baselines = {}
    comparisons = []
    for pair_id in pair_ids:
        pair_rows = [row for row in rows if row["pair_id"] == pair_id]
        baseline_rows = [row for row in pair_rows if row["phase"] == "baseline"]
        candidate_rows = [row for row in pair_rows if row["phase"] == "candidate"]
        if len(baseline_rows) != 1:
            raise ValueError(f"{pair_id} must contain exactly one baseline")
        strategy_names = tuple(row["strategy"] for row in candidate_rows)
        if strategy_names != EXPECTED_STRATEGIES:
            raise ValueError(
                f"{pair_id} strategy order must be {EXPECTED_STRATEGIES}, "
                f"got {strategy_names}"
            )
        baseline = baseline_rows[0]
        baselines[pair_id] = baseline
        baseline_collision = bool(baseline.get("collision_observed"))
        for row in candidate_rows:
            candidate_collision = bool(row.get("collision_observed"))
            if not baseline_collision and candidate_collision:
                collision_change = "introduced"
            elif baseline_collision and not candidate_collision:
                collision_change = "removed"
            elif baseline_collision and candidate_collision:
                collision_change = "both"
            else:
                collision_change = "neither"
            comparisons.append(
                {
                    "pair_id": pair_id,
                    "generator": row["generator"],
                    "target_risk_level": row["target_risk_level"],
                    "strategy": row["strategy"],
                    "baseline_risk_score": float(baseline["risk_score"]),
                    "candidate_risk_score": float(row["risk_score"]),
                    "risk_delta": float(row["risk_delta"]),
                    "reward": float(row["reward"]),
                    "baseline_collision_observed": baseline_collision,
                    "candidate_collision_observed": candidate_collision,
                    "collision_change": collision_change,
                    "candidate_collision_callback_count": int(
                        row.get("collision_count") or 0
                    ),
                    "strict_acceptance_passed": bool(
                        row.get("strict_acceptance_passed")
                    ),
                }
            )

    highest_risk_counts = Counter()
    highest_reward_counts = Counter()
    for pair_id in pair_ids:
        pair_comparisons = [row for row in comparisons if row["pair_id"] == pair_id]
        highest_risk = max(row["candidate_risk_score"] for row in pair_comparisons)
        highest_reward = max(row["reward"] for row in pair_comparisons)
        for row in pair_comparisons:
            if row["candidate_risk_score"] == highest_risk:
                highest_risk_counts[row["strategy"]] += 1
            if row["reward"] == highest_reward:
                highest_reward_counts[row["strategy"]] += 1

    strategy_rows = []
    for strategy in EXPECTED_STRATEGIES:
        selected = [row for row in comparisons if row["strategy"] == strategy]
        risk_deltas = [row["risk_delta"] for row in selected]
        rewards = [row["reward"] for row in selected]
        collision_changes = Counter(row["collision_change"] for row in selected)
        strategy_rows.append(
            {
                "strategy": strategy,
                "run_count": len(selected),
                "mean_candidate_risk": _rounded(
                    statistics.fmean(row["candidate_risk_score"] for row in selected)
                ),
                "mean_risk_delta": _rounded(statistics.fmean(risk_deltas)),
                "median_risk_delta": _rounded(statistics.median(risk_deltas)),
                "minimum_risk_delta": _rounded(min(risk_deltas)),
                "maximum_risk_delta": _rounded(max(risk_deltas)),
                "risk_increase_count": sum(value > 0 for value in risk_deltas),
                "risk_decrease_count": sum(value < 0 for value in risk_deltas),
                "mean_reward": _rounded(statistics.fmean(rewards)),
                "median_reward": _rounded(statistics.median(rewards)),
                "positive_reward_count": sum(value > 0 for value in rewards),
                "negative_reward_count": sum(value < 0 for value in rewards),
                "collision_introduced_count": collision_changes["introduced"],
                "collision_removed_count": collision_changes["removed"],
                "collision_both_count": collision_changes["both"],
                "collision_neither_count": collision_changes["neither"],
                "highest_candidate_risk_pair_count": highest_risk_counts[strategy],
                "highest_reward_pair_count": highest_reward_counts[strategy],
            }
        )

    baseline_rows = list(baselines.values())
    summary = {
        "format": "adversarial_baseline_carla_analysis_v1",
        "evidence_kind": "carla_runtime_paired_analysis",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pair_count": len(pair_ids),
        "baseline_run_count": len(baseline_rows),
        "candidate_run_count": len(comparisons),
        "total_run_count": len(rows),
        "strictly_accepted_run_count": sum(
            row.get("strict_acceptance_passed") is True for row in rows
        ),
        "mean_baseline_risk": _rounded(
            statistics.fmean(float(row["risk_score"]) for row in baseline_rows)
        ),
        "baseline_collision_run_count": sum(
            bool(row.get("collision_observed")) for row in baseline_rows
        ),
        "runtime_boundary": (
            "Each generator-target stratum contains one pair. Results describe this "
            "12-pair plan and do not establish general strategy superiority."
        ),
    }
    return summary, strategy_rows, comparisons


def write_report(path, summary, strategies):
    lines = [
        "# 对抗性非学习基线 CARLA 成对分析 V1",
        "",
        f"- 实机运行：`{summary['total_run_count']}`",
        f"- 严格验收：`{summary['strictly_accepted_run_count']}/{summary['total_run_count']}`",
        f"- 共享基线平均风险：`{summary['mean_baseline_risk']:.3f}`",
        f"- 发生碰撞的共享基线：`{summary['baseline_collision_run_count']}/{summary['baseline_run_count']}`",
        "",
        "| 策略 | 平均风险增量 | 中位风险增量 | 风险升高 | 平均 reward | 新增碰撞 | 消除碰撞 | 最高风险次数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in strategies:
        lines.append(
            f"| {row['strategy']} | {row['mean_risk_delta']:+.3f} | "
            f"{row['median_risk_delta']:+.3f} | {row['risk_increase_count']}/"
            f"{row['run_count']} | {row['mean_reward']:+.4f} | "
            f"{row['collision_introduced_count']} | "
            f"{row['collision_removed_count']} | "
            f"{row['highest_candidate_risk_pair_count']} |"
        )
    lines.extend(
        [
            "",
            "均值会受到少数大幅变化的 pair 影响，必须同时查看中位数、风险升高次数和碰撞状态变化。",
            "每个生成器与目标风险分层当前只有一个 pair，本报告不能证明任一策略具有普遍优势，也不能替代后续 RL 训练对照。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze paired adversarial baseline CARLA results"
    )
    parser.add_argument("--results", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    with open(os.path.abspath(args.results), "r", encoding="utf-8") as file:
        rows = json.load(file)
    summary, strategy_rows, comparisons = analyze_results(rows)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=False)
    _write_json(os.path.join(output_dir, "summary.json"), summary)
    _write_csv(os.path.join(output_dir, "strategy_summary.csv"), strategy_rows)
    _write_csv(os.path.join(output_dir, "pair_comparisons.csv"), comparisons)
    write_report(os.path.join(output_dir, "report.md"), summary, strategy_rows)
    print(
        f"[ANALYZE] accepted={summary['strictly_accepted_run_count']}/"
        f"{summary['total_run_count']} pairs={summary['pair_count']}",
        flush=True,
    )
    print(f"[RESULT_DIR] {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
