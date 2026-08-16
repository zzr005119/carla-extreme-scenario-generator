"""按统一 Top-K 诊断结果比较两个风险代理版本。"""

import argparse
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="比较两个风险代理版本")
    parser.add_argument("--before-summary", required=True)
    parser.add_argument("--after-summary", required=True)
    parser.add_argument("--before-label", required=True)
    parser.add_argument("--after-label", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def rf(summary):
    return summary["models"]["random_forest"]


def mean_metric(summary, name):
    return float(rf(summary)["metrics"][name]["mean"])


def collision_mae(summary):
    collision = rf(summary).get("collision_error", {}).get("collision")
    return None if not collision else float(collision["mae"])


def delta(before, after):
    return after - before


def main():
    args = parse_args()
    before = load_json(args.before_summary)
    after = load_json(args.after_summary)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    metric_rows = []
    for name in ("mae", "rmse", "spearman"):
        before_value = mean_metric(before, name)
        after_value = mean_metric(after, name)
        metric_rows.append(
            {
                "metric": name,
                "before": before_value,
                "after": after_value,
                "delta_after_minus_before": delta(before_value, after_value),
            }
        )

    before_jaccard = float(
        rf(before)["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
    )
    after_jaccard = float(
        rf(after)["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
    )
    before_collision = collision_mae(before)
    after_collision = collision_mae(after)
    comparison = {
        "format": "risk_proxy_version_comparison_generic_v1",
        "before": {
            "label": args.before_label,
            "summary": os.path.abspath(args.before_summary),
            "independent_scenario_count": before["independent_scenario_count"],
            "collision_scenario_count": (
                rf(before)["collision_error"]["collision"]["sample_count"]
            ),
        },
        "after": {
            "label": args.after_label,
            "summary": os.path.abspath(args.after_summary),
            "independent_scenario_count": after["independent_scenario_count"],
            "collision_scenario_count": (
                rf(after)["collision_error"]["collision"]["sample_count"]
            ),
        },
        "top_k": before["top_k"],
        "metrics": metric_rows,
        "ranking_stability": {
            "before_jaccard": before_jaccard,
            "after_jaccard": after_jaccard,
            "delta_after_minus_before": after_jaccard - before_jaccard,
        },
        "collision_error": {
            "before_mae": before_collision,
            "after_mae": after_collision,
            "delta_after_minus_before": (
                None
                if before_collision is None or after_collision is None
                else after_collision - before_collision
            ),
        },
    }
    with open(output_dir / "risk_proxy_version_comparison.json", "w", encoding="utf-8") as file:
        json.dump(comparison, file, ensure_ascii=False, indent=2, allow_nan=False)

    metric_lines = []
    for row in metric_rows:
        metric_lines.append(
            f"- {row['metric'].upper()}：`{row['before']:.3f}` → "
            f"`{row['after']:.3f}`，变化 `{row['delta_after_minus_before']:+.3f}`。"
        )
    lines = [
        f"# 风险代理 {args.before_label}/{args.after_label} 对比",
        "",
        f"- {args.before_label}：`{before['independent_scenario_count']}` 个独立场景，"
        f"碰撞场景 `{comparison['before']['collision_scenario_count']}` 个。",
        f"- {args.after_label}：`{after['independent_scenario_count']}` 个独立场景，"
        f"碰撞场景 `{comparison['after']['collision_scenario_count']}` 个。",
        f"- 两个版本均使用固定 Top-`{before['top_k']}` 和 50 次重复分层三折 OOF。",
        "",
        "## 指标变化",
        "",
        *metric_lines,
        f"- Top-{before['top_k']} 两两 Jaccard：`{before_jaccard:.3f}` → "
        f"`{after_jaccard:.3f}`，变化 `{after_jaccard - before_jaccard:+.3f}`。",
        (
            f"- 碰撞场景 MAE：`{before_collision:.3f}` → `{after_collision:.3f}`，"
            f"变化 `{after_collision - before_collision:+.3f}`。"
            if before_collision is not None and after_collision is not None
            else "- 碰撞场景 MAE：缺少可比结果。"
        ),
        "",
        "## 解释边界",
        "",
        "- 两个版本的独立场景集合不同，指标用于工程诊断，不作统计显著性结论。",
        "- Traffic Manager 种子已在场景级预聚合，不能作为独立样本重复计数。",
        "- `target_risk_level` 与 `observed_risk` 保持分离；本比较不修改实测标签。",
    ]
    (output_dir / "risk_proxy_version_comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(
        f"[COMPARE] {args.before_label}->{args.after_label} | "
        f"mae={mean_metric(before, 'mae'):.3f}->{mean_metric(after, 'mae'):.3f} | "
        f"spearman={mean_metric(before, 'spearman'):.3f}->{mean_metric(after, 'spearman'):.3f} | "
        f"top_k_jaccard={before_jaccard:.3f}->{after_jaccard:.3f}"
    )
    print(f"[COMPARE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
