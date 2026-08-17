"""从原始与物理增强短名单中选择平衡差异候选对。"""

import argparse
import csv
import json
import os
from pathlib import Path

import pandas as pd


GENERATORS = ("lhs", "gmm", "cvae")
CHANNEL_BASE_COLUMNS = {
    "stable_high_score": "stable_high_score_base",
    "high_uncertainty": "high_uncertainty_base",
    "collision_propensity": "collision_propensity_base",
}


def parse_args():
    parser = argparse.ArgumentParser(description="选择物理增强差异候选配对")
    parser.add_argument("--baseline-scored", required=True)
    parser.add_argument("--baseline-selection", required=True)
    parser.add_argument("--enhanced-scored", required=True)
    parser.add_argument("--enhanced-selection", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def load_frame(path, unique_columns):
    frame = pd.read_csv(os.path.abspath(path))
    missing = sorted(set(unique_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{path} 缺少字段: {missing}")
    if frame.duplicated(unique_columns).any():
        raise ValueError(f"{path} 的唯一键重复: {unique_columns}")
    return frame


def slot_map(frame):
    result = {}
    for row in frame.to_dict(orient="records"):
        key = (
            str(row["generator"]),
            str(row["selection_channel"]),
            int(row["selection_order"]),
        )
        result[key] = row
    return result


def build_options(
    baseline_scored,
    enhanced_scored,
    baseline_selected,
    enhanced_selected,
):
    baseline_scores = baseline_scored.set_index("sample_id", drop=False)
    enhanced_scores = enhanced_scored.set_index("sample_id", drop=False)
    if set(baseline_scores.index) != set(enhanced_scores.index):
        raise ValueError("两套评分的候选 sample_id 集合不一致")

    baseline_slots = slot_map(baseline_selected)
    enhanced_slots = slot_map(enhanced_selected)
    if set(baseline_slots) != set(enhanced_slots):
        raise ValueError("两套短名单的生成器、通道和序号槽位不一致")

    grouped = {
        (generator, channel): []
        for generator in GENERATORS
        for channel in CHANNEL_BASE_COLUMNS
    }
    for slot in sorted(baseline_slots):
        generator, channel, order = slot
        baseline_row = baseline_slots[slot]
        enhanced_row = enhanced_slots[slot]
        baseline_id = str(baseline_row["sample_id"])
        enhanced_id = str(enhanced_row["sample_id"])
        if baseline_id == enhanced_id:
            continue
        if baseline_row["target_risk_level"] != enhanced_row["target_risk_level"]:
            continue
        base_column = CHANNEL_BASE_COLUMNS[channel]
        for frame, name in (
            (baseline_scores, "baseline"),
            (enhanced_scores, "enhanced"),
        ):
            if base_column not in frame.columns:
                raise ValueError(f"{name} 评分缺少通道基础分: {base_column}")

        baseline_preference = float(
            baseline_scores.at[baseline_id, base_column]
            - baseline_scores.at[enhanced_id, base_column]
        )
        enhanced_preference = float(
            enhanced_scores.at[enhanced_id, base_column]
            - enhanced_scores.at[baseline_id, base_column]
        )
        risk_disagreement = float(
            abs(
                enhanced_scores.at[baseline_id, "predicted_risk_mean"]
                - baseline_scores.at[baseline_id, "predicted_risk_mean"]
            )
            + abs(
                enhanced_scores.at[enhanced_id, "predicted_risk_mean"]
                - baseline_scores.at[enhanced_id, "predicted_risk_mean"]
            )
        )
        collision_disagreement = float(
            abs(
                enhanced_scores.at[
                    baseline_id, "predicted_collision_probability_mean"
                ]
                - baseline_scores.at[
                    baseline_id, "predicted_collision_probability_mean"
                ]
            )
            + abs(
                enhanced_scores.at[
                    enhanced_id, "predicted_collision_probability_mean"
                ]
                - baseline_scores.at[
                    enhanced_id, "predicted_collision_probability_mean"
                ]
            )
        )
        grouped[(generator, channel)].append(
            {
                "generator": generator,
                "selection_channel": channel,
                "slot_order": order,
                "target_risk_level": baseline_row["target_risk_level"],
                "baseline_sample_id": baseline_id,
                "enhanced_sample_id": enhanced_id,
                "base_column": base_column,
                "baseline_preference": baseline_preference,
                "enhanced_preference": enhanced_preference,
                "crossover_strength": baseline_preference
                + enhanced_preference,
                "risk_disagreement": risk_disagreement,
                "collision_disagreement": collision_disagreement,
            }
        )

    missing_cells = [cell for cell, options in grouped.items() if not options]
    if missing_cells:
        raise ValueError(f"以下生成器×通道没有差异槽位: {missing_cells}")
    for options in grouped.values():
        options.sort(
            key=lambda row: (
                row["crossover_strength"],
                row["risk_disagreement"],
                row["collision_disagreement"],
                -row["slot_order"],
            ),
            reverse=True,
        )
    return grouped


def select_unique_pairs(grouped):
    cells = sorted(grouped)
    best = None

    def search(position, used_ids, chosen, objective):
        nonlocal best
        if position == len(cells):
            if best is None or objective > best[0]:
                best = (objective, list(chosen))
            return
        cell = cells[position]
        for option in grouped[cell]:
            pair_ids = {
                option["baseline_sample_id"],
                option["enhanced_sample_id"],
            }
            if used_ids & pair_ids:
                continue
            search(
                position + 1,
                used_ids | pair_ids,
                chosen + [option],
                (
                    objective[0] + option["crossover_strength"],
                    objective[1] + option["risk_disagreement"],
                    objective[2] + option["collision_disagreement"],
                ),
            )

    search(0, set(), [], (0.0, 0.0, 0.0))
    if best is None:
        raise ValueError("无法为 9 个生成器×通道单元选择互不重复的候选对")
    pairs = []
    for pair_index, row in enumerate(best[1], 1):
        pairs.append(
            {
                "pair_index": pair_index,
                "pair_id": (
                    f"pair_{pair_index:02d}_{row['generator']}_"
                    f"{row['selection_channel']}"
                ),
                **row,
            }
        )
    return pairs, best[0]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_scored = load_frame(args.baseline_scored, ["sample_id"])
    enhanced_scored = load_frame(args.enhanced_scored, ["sample_id"])
    selection_key = ["generator", "selection_channel", "selection_order"]
    baseline_selected = load_frame(args.baseline_selection, selection_key)
    enhanced_selected = load_frame(args.enhanced_selection, selection_key)
    pairs, objective = select_unique_pairs(
        build_options(
            baseline_scored,
            enhanced_scored,
            baseline_selected,
            enhanced_selected,
        )
    )
    selected_ids = {
        sample_id
        for row in pairs
        for sample_id in (
            row["baseline_sample_id"],
            row["enhanced_sample_id"],
        )
    }
    if len(pairs) != 9 or len(selected_ids) != 18:
        raise RuntimeError("配对选择必须得到 9 对、18 个唯一场景")

    write_csv(output_dir / "pair_selection.csv", pairs)
    summary = {
        "format": "physical_feature_candidate_pair_selection_v1",
        "pair_count": len(pairs),
        "independent_scenario_count": len(selected_ids),
        "generators": list(GENERATORS),
        "selection_channels": list(CHANNEL_BASE_COLUMNS),
        "objective": {
            "crossover_strength_sum": objective[0],
            "risk_disagreement_sum": objective[1],
            "collision_disagreement_sum": objective[2],
        },
        "pairs": pairs,
        "interpretation_limits": [
            "每个生成器×选择通道只保留一个差异槽位，用于小规模配对验证。",
            "配对优先最大化两套评分对各自候选的交叉偏好，不代表 CARLA 实测优劣。",
            "18 个场景均保持唯一，避免同一场景跨配对重复计数。",
        ],
    }
    with open(output_dir / "pair_selection.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2, allow_nan=False)
    lines = [
        "# 物理增强候选差异配对 V1",
        "",
        "- 设计：3 个生成器 × 3 个选择通道，每个单元选择 1 对。",
        f"- 配对：`{len(pairs)}` 对；独立场景：`{len(selected_ids)}` 个。",
        "- 所有候选 sample_id 唯一，不跨配对复用。",
        "",
        "| 配对 | 生成器 | 通道 | 槽位 | 目标档 | 原始候选 | 增强候选 | 交叉强度 |",
        "|---|---|---|---:|---|---|---|---:|",
    ]
    for row in pairs:
        lines.append(
            f"| {row['pair_id']} | {row['generator']} | "
            f"{row['selection_channel']} | {row['slot_order']} | "
            f"{row['target_risk_level']} | `{row['baseline_sample_id']}` | "
            f"`{row['enhanced_sample_id']}` | {row['crossover_strength']:.3f} |"
        )
    (output_dir / "pair_selection.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(
        f"[PAIR_SELECT] pairs={len(pairs)} | scenarios={len(selected_ids)} | "
        f"crossover_sum={objective[0]:.3f}"
    )
    print(f"[PAIR_SELECT] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
