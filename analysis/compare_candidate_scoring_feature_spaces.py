"""比较原始 15 维与物理增强特征空间的候选重评分结果。"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


MODES = ("single_channel", "dual_channel")


def parse_args():
    parser = argparse.ArgumentParser(description="候选重评分特征空间比较")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--enhanced-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def read_summary(path):
    with open(Path(path) / "scoring_summary.json", encoding="utf-8") as file:
        return json.load(file)


def read_scored(path):
    frame = pd.read_csv(Path(path) / "scored_candidates.csv")
    if frame["sample_id"].duplicated().any():
        raise ValueError(f"候选 sample_id 重复: {path}")
    return frame.set_index("sample_id", drop=False)


def jaccard(left, right):
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def selection_metrics(path, mode):
    frame = pd.read_csv(Path(path) / f"{mode}_selected.csv")
    selected = set(frame["sample_id"].astype(str))
    collision = frame["predicted_collision_probability_mean"]
    return {
        "count": int(len(frame)),
        "sample_ids": sorted(selected),
        "mean_predicted_risk": float(frame["predicted_risk_mean"].mean()),
        "mean_robust_risk": float(frame["robust_predicted_risk_score"].mean()),
        "mean_collision_probability": float(collision.mean()),
        "mean_selection_diversity_distance": float(
            frame["selection_diversity_distance"].mean()
        ),
    }


def metric_summary(baseline, enhanced):
    delta = enhanced - baseline
    return {
        "baseline": float(baseline),
        "enhanced": float(enhanced),
        "delta_enhanced_minus_baseline": float(delta),
    }


def main():
    args = parse_args()
    baseline_dir = Path(os.path.abspath(args.baseline_dir))
    enhanced_dir = Path(os.path.abspath(args.enhanced_dir))
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_summary = read_summary(baseline_dir)
    enhanced_summary = read_summary(enhanced_dir)
    baseline_frame = read_scored(baseline_dir)
    enhanced_frame = read_scored(enhanced_dir)
    if set(baseline_frame.index) != set(enhanced_frame.index):
        raise ValueError("原始与增强评分的候选 sample_id 集合不一致")
    enhanced_frame = enhanced_frame.loc[baseline_frame.index]

    risk_delta = (
        enhanced_frame["predicted_risk_mean"]
        - baseline_frame["predicted_risk_mean"]
    )
    collision_delta = (
        enhanced_frame["predicted_collision_probability_mean"]
        - baseline_frame["predicted_collision_probability_mean"]
    )
    spearman = spearmanr(
        baseline_frame["predicted_risk_mean"],
        enhanced_frame["predicted_risk_mean"],
    )
    spearman_value = getattr(spearman, "statistic", spearman[0])

    comparison_modes = {}
    for mode in MODES:
        baseline_selection = selection_metrics(baseline_dir, mode)
        enhanced_selection = selection_metrics(enhanced_dir, mode)
        baseline_ids = set(baseline_selection["sample_ids"])
        enhanced_ids = set(enhanced_selection["sample_ids"])
        comparison_modes[mode] = {
            "baseline": baseline_selection,
            "enhanced": enhanced_selection,
            "intersection_count": int(len(baseline_ids & enhanced_ids)),
            "jaccard": float(jaccard(baseline_ids, enhanced_ids)),
            "changed_out_count": int(len(baseline_ids - enhanced_ids)),
            "changed_in_count": int(len(enhanced_ids - baseline_ids)),
        }

    summary = {
        "format": "candidate_scoring_feature_space_comparison_v1",
        "baseline": {
            "directory": str(baseline_dir),
            "feature_space": baseline_summary.get("feature_space"),
            "dataset": baseline_summary["dataset"],
        },
        "enhanced": {
            "directory": str(enhanced_dir),
            "feature_space": enhanced_summary.get("feature_space"),
            "dataset": enhanced_summary["dataset"],
        },
        "candidate_count": int(len(baseline_frame)),
        "candidate_prediction_comparison": {
            "risk_mean_mae_delta": float(np.mean(np.abs(risk_delta))),
            "risk_mean_delta_mean": float(risk_delta.mean()),
            "risk_mean_delta_std": float(risk_delta.std(ddof=1)),
            "risk_mean_rank_spearman": None
            if np.isnan(spearman_value)
            else float(spearman_value),
            "collision_probability_mae_delta": float(
                np.mean(np.abs(collision_delta))
            ),
            "collision_probability_delta_mean": float(collision_delta.mean()),
            "enhanced_higher_risk_count": int(np.sum(risk_delta > 0)),
            "enhanced_lower_risk_count": int(np.sum(risk_delta < 0)),
        },
        "selection_comparison": comparison_modes,
        "interpretation_limits": [
            "比较只反映同一候选池和同一 V4 训练集下的离线排序变化，不是 CARLA 实测效果。",
            "碰撞概率是候选预排序通道，不是跨地图真实碰撞概率。",
            "候选生成器优劣仍需后续小规模 CARLA 配对验证，不能由离线重评分直接下结论。",
        ],
    }
    with open(output_dir / "feature_space_comparison.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2, allow_nan=False)

    rows = []
    for mode, values in comparison_modes.items():
        rows.append(
            {
                "mode": mode,
                "baseline_count": values["baseline"]["count"],
                "enhanced_count": values["enhanced"]["count"],
                "intersection_count": values["intersection_count"],
                "jaccard": values["jaccard"],
                "changed_out_count": values["changed_out_count"],
                "changed_in_count": values["changed_in_count"],
                "baseline_mean_collision_probability": values["baseline"][
                    "mean_collision_probability"
                ],
                "enhanced_mean_collision_probability": values["enhanced"][
                    "mean_collision_probability"
                ],
                "baseline_mean_selection_diversity_distance": values["baseline"][
                    "mean_selection_diversity_distance"
                ],
                "enhanced_mean_selection_diversity_distance": values["enhanced"][
                    "mean_selection_diversity_distance"
                ],
            }
        )
    pd.DataFrame(rows).to_csv(
        output_dir / "selection_comparison.csv", index=False, encoding="utf-8-sig"
    )

    lines = [
        "# 候选重评分特征空间比较 V1",
        "",
        f"- 候选数：`{summary['candidate_count']}`。",
        "- 基线：原始 15 维参数；增强：原始参数加 12 个物理交互派生特征。",
        f"- 候选风险均值绝对变化：`{summary['candidate_prediction_comparison']['risk_mean_mae_delta']:.3f}`。",
        f"- 两套风险排序 Spearman：`{summary['candidate_prediction_comparison']['risk_mean_rank_spearman']:.3f}`。",
        f"- 增强评分更高的候选：`{summary['candidate_prediction_comparison']['enhanced_higher_risk_count']}`；更低的候选：`{summary['candidate_prediction_comparison']['enhanced_lower_risk_count']}`。",
        "",
        "## 短名单变化",
        "",
        "| 模式 | 基线/增强数量 | 交集 | Jaccard | 淘汰 | 新增 | 基线碰撞概率 | 增强碰撞概率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, values in comparison_modes.items():
        lines.append(
            f"| {mode} | {values['baseline']['count']}/{values['enhanced']['count']} | "
            f"{values['intersection_count']} | {values['jaccard']:.3f} | "
            f"{values['changed_out_count']} | {values['changed_in_count']} | "
            f"{values['baseline']['mean_collision_probability']:.3f} | "
            f"{values['enhanced']['mean_collision_probability']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "该比较只用于决定是否形成小规模 CARLA 验证短名单，不把离线候选变化直接解释为真实风险改善。",
            "",
        ]
    )
    (output_dir / "feature_space_comparison.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(
        f"[COMPARE] candidates={len(baseline_frame)} | "
        f"risk_spearman={float(spearman_value):.3f}"
    )
    print(f"[COMPARE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
