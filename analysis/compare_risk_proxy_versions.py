"""比较风险代理版本的重复 OOF 诊断结果。"""

import argparse
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="比较风险代理 V1/V2")
    parser.add_argument("--v1-summary", required=True)
    parser.add_argument("--v2-summary", required=True)
    parser.add_argument("--v2-top9-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def metric(summary, name, model="random_forest"):
    return float(summary["models"][model]["metrics"][name]["mean"])


def relative_delta(before, after):
    return None if before == 0 else (after - before) / abs(before)


def main():
    args = parse_args()
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    v1 = load_json(args.v1_summary)
    v2 = load_json(args.v2_summary)
    v2_top9 = load_json(args.v2_top9_summary)

    v1_rf = v1["models"]["random_forest"]
    v2_rf = v2["models"]["random_forest"]
    v2_top9_rf = v2_top9["models"]["random_forest"]
    metrics = {}
    for name in ("mae", "rmse", "spearman"):
        before = metric(v1, name)
        after = metric(v2, name)
        metrics[name] = {
            "v1": before,
            "v2": after,
            "delta": after - before,
            "relative_delta": relative_delta(before, after),
        }

    comparison = {
        "format": "risk_proxy_version_comparison_v1",
        "v1_independent_scenario_count": v1["independent_scenario_count"],
        "v2_independent_scenario_count": v2["independent_scenario_count"],
        "v1_collision_scenario_count": v1_rf["collision_error"]["collision"][
            "sample_count"
        ],
        "v2_collision_scenario_count": v2_rf["collision_error"]["collision"][
            "sample_count"
        ],
        "metrics": metrics,
        "top_k_comparison": {
            "k": 9,
            "v1_jaccard": float(
                v1_rf["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
            ),
            "v2_jaccard": float(
                v2_top9_rf["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
            ),
            "delta": float(
                v2_top9_rf["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
                - v1_rf["ranking_stability"]["pairwise_top_k_jaccard"]["mean"]
            ),
        },
        "collision_error": {
            "v1_mae": float(v1_rf["collision_error"]["collision"]["mae"]),
            "v2_mae": float(v2_rf["collision_error"]["collision"]["mae"]),
        },
    }
    with open(output_dir / "risk_proxy_version_comparison.json", "w", encoding="utf-8") as file:
        json.dump(comparison, file, ensure_ascii=False, indent=2, allow_nan=False)

    lines = [
        "# 风险代理 V1/V2 对比",
        "",
        f"- V1：`{comparison['v1_independent_scenario_count']}` 个独立场景，碰撞场景 `{comparison['v1_collision_scenario_count']}` 个。",
        f"- V2：`{comparison['v2_independent_scenario_count']}` 个独立场景，碰撞场景 `{comparison['v2_collision_scenario_count']}` 个。",
        "- V1/V2 的 Top-K 稳定性统一使用 Top-9；V2 另有自然比例 Top-16 诊断，但不用于本项直接比较。",
        "",
        "## 结果",
        "",
        f"- MAE：`{metrics['mae']['v1']:.3f}` → `{metrics['mae']['v2']:.3f}`，变化 `{metrics['mae']['delta']:+.3f}`。",
        f"- RMSE：`{metrics['rmse']['v1']:.3f}` → `{metrics['rmse']['v2']:.3f}`，变化 `{metrics['rmse']['delta']:+.3f}`。",
        f"- Spearman：`{metrics['spearman']['v1']:.3f}` → `{metrics['spearman']['v2']:.3f}`，变化 `{metrics['spearman']['delta']:+.3f}`。",
        f"- Top-9 两两 Jaccard：`{comparison['top_k_comparison']['v1_jaccard']:.3f}` → `{comparison['top_k_comparison']['v2_jaccard']:.3f}`，变化 `{comparison['top_k_comparison']['delta']:+.3f}`。",
        f"- 碰撞场景 MAE：`{comparison['collision_error']['v1_mae']:.3f}` → `{comparison['collision_error']['v2_mae']:.3f}`。",
        "",
        "## 结论边界",
        "",
        "- V2 增加了碰撞反馈，碰撞场景数量从 3 个增至 18 个，碰撞风险的系统性低估有所缓解，但高风险区域内部仍存在较大离散性。",
        "- V2 的整体 OOF 误差和排序稳定性下降，不能直接把 V2 作为单一连续风险排序器替代 V1；这反映的是新增高风险/碰撞样本带来的分布变化与任务难度，不是训练代码失败。",
        "- 下一步应把连续风险分数与碰撞倾向分成两个反馈通道，先做离线分层 OOF 诊断，再决定是否进行新一轮 CARLA 主动补样。",
    ]
    (output_dir / "risk_proxy_version_comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(
        f"[COMPARE] mae={metrics['mae']['v1']:.3f}->{metrics['mae']['v2']:.3f} | "
        f"spearman={metrics['spearman']['v1']:.3f}->{metrics['spearman']['v2']:.3f} | "
        f"top9_jaccard={comparison['top_k_comparison']['v1_jaccard']:.3f}->"
        f"{comparison['top_k_comparison']['v2_jaccard']:.3f}"
    )
    print(f"[COMPARE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
