"""使用连续风险与碰撞倾向两个反馈通道评分候选场景。"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from score_feedback_candidates import (  # noqa: E402
    add_channel_scores,
    add_distance_scores,
    add_top_frequencies,
    file_sha256,
    fit_bootstrap_predictions,
    greedy_select,
    load_candidates,
    load_training_frame,
    min_distance_to_selected,
    percentile_rank,
    stratified_bootstrap_indices,
    write_json,
    write_jsonl,
    write_csv,
)
from core.physical_features import (  # noqa: E402
    PHYSICAL_FEATURE_VERSION,
    physical_feature_matrix,
    physical_feature_names,
)


TARGET_COLUMN = "observed_risk_score_mean"
FEATURE_PREFIX = "feature_"
FEATURE_SPACES = ("raw_15d", "physical_enhanced")
SELECTION_MODES = {
    "single_channel": {
        "stable_high_score": "stable_high_score_base",
        "high_uncertainty": "high_uncertainty_base",
        "collision_boundary": "collision_boundary_base",
    },
    "dual_channel": {
        "stable_high_score": "stable_high_score_base",
        "high_uncertainty": "high_uncertainty_base",
        "collision_propensity": "collision_propensity_base",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="双通道反馈候选评分 V2")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--candidates", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--feature-space",
        choices=FEATURE_SPACES,
        default="raw_15d",
        help="风险回归器和碰撞分类器使用的特征空间",
    )
    parser.add_argument("--scoring-repeats", type=int, default=5)
    parser.add_argument("--bootstrap-models", type=int, default=30)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--top-fraction", type=float, default=0.10)
    parser.add_argument("--robust-penalty", type=float, default=0.50)
    parser.add_argument("--select-per-channel", type=int, default=3)
    parser.add_argument("--min-per-target-channel", type=int, default=1)
    parser.add_argument("--diversity-weight", type=float, default=0.20)
    parser.add_argument("--random-state", type=int, default=20260815)
    return parser.parse_args()


def validate_args(args):
    if args.scoring_repeats < 2:
        raise ValueError("--scoring-repeats 至少为 2")
    if args.bootstrap_models < 2:
        raise ValueError("--bootstrap-models 至少为 2")
    if args.n_estimators < 10:
        raise ValueError("--n-estimators 至少为 10")
    if not 0.0 < args.top_fraction <= 1.0:
        raise ValueError("--top-fraction 必须位于 (0, 1]")
    if args.robust_penalty < 0.0:
        raise ValueError("--robust-penalty 不能小于 0")
    if args.select_per_channel < 1:
        raise ValueError("--select-per-channel 至少为 1")
    if args.min_per_target_channel < 0:
        raise ValueError("--min-per-target-channel 不能小于 0")
    if not 0.0 <= args.diversity_weight < 1.0:
        raise ValueError("--diversity-weight 必须位于 [0, 1)")


def fit_collision_bootstrap_predictions(
    training_features,
    collision_target,
    strata,
    candidate_features,
    bootstrap_models,
    n_estimators,
    random_state,
):
    prediction_matrix = np.empty(
        (bootstrap_models, len(candidate_features)), dtype=float
    )
    seeds = []
    for repeat_index in range(bootstrap_models):
        repeat_seed = random_state + repeat_index * 104729
        generator = np.random.default_rng(repeat_seed)
        train_indices = stratified_bootstrap_indices(strata, generator)
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            min_samples_leaf=2,
            max_features=0.7,
            class_weight="balanced",
            random_state=repeat_seed,
            n_jobs=-1,
        )
        model.fit(training_features[train_indices], collision_target[train_indices])
        prediction_matrix[repeat_index] = model.predict_proba(candidate_features)[:, 1]
        seeds.append(repeat_seed)
    return prediction_matrix, seeds


def add_collision_scores(frame, prediction_matrix):
    frame["predicted_collision_probability_mean"] = prediction_matrix.mean(axis=0)
    frame["predicted_collision_probability_std"] = prediction_matrix.std(
        axis=0, ddof=1
    )
    frame["predicted_collision_probability_min"] = prediction_matrix.min(axis=0)
    frame["predicted_collision_probability_max"] = prediction_matrix.max(axis=0)
    frame["collision_propensity_base"] = (
        0.80 * percentile_rank(frame["predicted_collision_probability_mean"])
        + 0.20
        * percentile_rank(
            -frame["predicted_collision_probability_std"]
        )
    )


def select_mode(
    frame,
    features,
    mode_name,
    per_channel,
    min_per_target_channel,
    diversity_weight,
):
    channel_columns = SELECTION_MODES[mode_name]
    selected_rows = []
    for generator_name, generator_frame in frame.groupby("generator", sort=True):
        candidate_indices = generator_frame.index.to_list()
        target_levels = sorted(generator_frame["target_risk_level"].unique())
        minimum_required = min_per_target_channel * len(target_levels)
        if minimum_required > per_channel:
            raise ValueError(
                f"{generator_name} 每通道至少需要 {minimum_required} 个名额，"
                f"当前 --select-per-channel={per_channel}"
            )
        excluded = set()
        selected_features = []
        for channel_name, base_column in channel_columns.items():
            selections = []
            for target_level in target_levels:
                target_indices = generator_frame.index[
                    generator_frame["target_risk_level"] == target_level
                ].to_list()
                selections.extend(
                    greedy_select(
                        frame,
                        features,
                        target_indices,
                        base_column,
                        min_per_target_channel,
                        diversity_weight,
                        excluded,
                        selected_features,
                    )
                )
            remaining = per_channel - len(selections)
            if remaining > 0:
                selections.extend(
                    greedy_select(
                        frame,
                        features,
                        candidate_indices,
                        base_column,
                        remaining,
                        diversity_weight,
                        excluded,
                        selected_features,
                    )
                )
            if len(selections) != per_channel:
                raise ValueError(
                    f"{generator_name} 的 {channel_name} 仅选择 {len(selections)} 个候选"
                )
            for order, selection in enumerate(selections, 1):
                selected_rows.append(
                    {
                        "index": selection["index"],
                        "mode": mode_name,
                        "generator": generator_name,
                        "selection_channel": channel_name,
                        "selection_order": order,
                        "selection_utility": selection["selection_utility"],
                        "selection_diversity_distance": selection[
                            "diversity_distance"
                        ],
                    }
                )
    return selected_rows


def selected_frame(scored_frame, selections):
    rows = []
    for selection in selections:
        row = scored_frame.loc[selection["index"]].to_dict()
        row.update({key: value for key, value in selection.items() if key != "index"})
        rows.append(row)
    return pd.DataFrame(rows)


def selection_ids(selected):
    return set(selected["sample_id"].astype(str)) if len(selected) else set()


def jaccard(left, right):
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def selection_counts(selected):
    counts = defaultdict(lambda: defaultdict(int))
    targets = defaultdict(lambda: defaultdict(int))
    for row in selected.to_dict(orient="records"):
        counts[row["generator"]][row["selection_channel"]] += 1
        targets[row["generator"]][row["target_risk_level"]] += 1
    return {
        "by_generator_channel": {
            generator: dict(channels)
            for generator, channels in counts.items()
        },
        "by_generator_target": {
            generator: dict(levels) for generator, levels in targets.items()
        },
    }


def build_scored_frame(
    base_frame,
    training_frame,
    feature_columns,
    distance_candidate_features,
    risk_predictions,
    collision_predictions,
    top_fraction,
    robust_penalty,
):
    frame = base_frame.copy()
    frame["predicted_risk_mean"] = risk_predictions.mean(axis=0)
    frame["predicted_risk_std"] = risk_predictions.std(axis=0, ddof=1)
    frame["predicted_risk_min"] = risk_predictions.min(axis=0)
    frame["predicted_risk_max"] = risk_predictions.max(axis=0)
    frame["robust_predicted_risk_score"] = (
        frame["predicted_risk_mean"]
        - robust_penalty * frame["predicted_risk_std"]
    )
    top_counts = add_top_frequencies(frame, risk_predictions, top_fraction)
    distance_summary = add_distance_scores(
        frame,
        distance_candidate_features,
        training_frame,
        feature_columns,
    )
    add_channel_scores(frame)
    add_collision_scores(frame, collision_predictions)
    return frame, top_counts, distance_summary


def selection_table(records, scored_frame, selections):
    selection_by_index = {row["index"]: row for row in selections}
    selected_records = []
    for index, source in enumerate(records):
        if index not in selection_by_index:
            continue
        selection = selection_by_index[index]
        record = json.loads(json.dumps(source, ensure_ascii=False))
        record["candidate_scoring_v2"] = {
            "mode": selection["mode"],
            "selection_channel": selection["selection_channel"],
            "selection_order": selection["selection_order"],
            "selection_utility": float(selection["selection_utility"]),
            "selection_diversity_distance": float(
                selection["selection_diversity_distance"]
            ),
            "predicted_risk_mean": float(
                scored_frame.at[index, "predicted_risk_mean"]
            ),
            "predicted_risk_std": float(
                scored_frame.at[index, "predicted_risk_std"]
            ),
            "robust_predicted_risk_score": float(
                scored_frame.at[index, "robust_predicted_risk_score"]
            ),
            "predicted_collision_probability_mean": float(
                scored_frame.at[index, "predicted_collision_probability_mean"]
            ),
            "predicted_collision_probability_std": float(
                scored_frame.at[index, "predicted_collision_probability_std"]
            ),
            "collision_boundary_score": float(
                scored_frame.at[index, "collision_boundary_score"]
            ),
        }
        selected_records.append(record)
    return selected_records


def model_summary(frame, selected, mode_name):
    collision_channel = "collision_propensity_base" if mode_name == "dual_channel" else "collision_boundary_base"
    collision_selected = selected[selected["selection_channel"] == (
        "collision_propensity" if mode_name == "dual_channel" else "collision_boundary"
    )]
    return {
        "mode": mode_name,
        "channels": list(SELECTION_MODES[mode_name]),
        "selected_count": int(len(selected)),
        "selection_counts": selection_counts(selected),
        "mean_selected_risk": float(selected["predicted_risk_mean"].mean()),
        "mean_selected_robust_risk": float(
            selected["robust_predicted_risk_score"].mean()
        ),
        "mean_selected_collision_probability": float(
            selected["predicted_collision_probability_mean"].mean()
        ),
        "collision_channel_mean": float(collision_selected[collision_channel].mean()),
        "collision_channel_selected_count": int(len(collision_selected)),
    }


def build_report(summary, single_selected, dual_selected):
    lines = [
        "# 双通道反馈候选评分 V2",
        "",
        f"- 特征空间：`{summary['feature_space']}`，模型特征数 `{summary['model_feature_count']}`。",
        f"- 训练数据：`{summary['dataset']['independent_scenario_count']}` 个独立场景，其中碰撞场景 `{summary['dataset']['collision_scenario_count']}` 个。",
        f"- 候选池：`{summary['candidate_count']}` 个；评分重复：`{summary['scoring_repeats']}` 次；每次 Bootstrap 模型：`{summary['bootstrap_models_per_repeat']}` 个。",
        "- 两种策略共享候选池、生成器、目标档配额和多样性规则，只改变第三个风险选择通道。",
        "",
        "## 通道定义",
        "",
        "- `single_channel`：稳健连续风险、高不确定性、碰撞边界距离。",
        "- `dual_channel`：稳健连续风险、高不确定性、碰撞倾向概率。",
        "- 碰撞倾向概率由独立的Bootstrap随机森林分类器估计，不解释为跨地图真实碰撞概率。",
        "",
        "## 对比",
        "",
        f"- 两种策略最终短名单交集：`{summary['comparison']['intersection_count']}` 个，Jaccard：`{summary['comparison']['jaccard']:.3f}`。",
        f"- 单通道碰撞相关通道选择的平均碰撞概率：`{summary['comparison']['single_collision_probability_mean']:.3f}`。",
        f"- 双通道碰撞倾向选择的平均碰撞概率：`{summary['comparison']['dual_collision_probability_mean']:.3f}`。",
        "",
        "## 双通道短名单",
        "",
        "| 生成器 | 通道 | 样本 | 目标档 | 连续风险均值 | 碰撞概率均值 | 碰撞边界分 |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in dual_selected.sort_values(
        ["generator", "selection_channel", "selection_order"]
    ).to_dict(orient="records"):
        lines.append(
            f"| {row['generator']} | {row['selection_channel']} | `{row['sample_id']}` | "
            f"{row['target_risk_level']} | {row['predicted_risk_mean']:.3f} | "
            f"{row['predicted_collision_probability_mean']:.3f} | "
            f"{row['collision_boundary_score']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果是候选离线预排序，不包含新增 CARLA 实测。双通道只用于构建平衡短名单与主动补样配额，不能据此声称生成器或碰撞概率模型已经完成实证验证。",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    validate_args(args)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = os.path.abspath(args.dataset)
    training_frame, feature_columns, strata = load_training_frame(dataset_path)
    records, candidate_frame, source_files = load_candidates(args.candidates)
    candidate_feature_columns = [
        column for column in candidate_frame if column.startswith(FEATURE_PREFIX)
    ]
    if candidate_feature_columns != feature_columns:
        raise ValueError("候选特征列与训练数据特征列不一致")
    raw_training_features = training_frame[feature_columns].to_numpy(dtype=float)
    raw_candidate_features = candidate_frame[feature_columns].to_numpy(dtype=float)
    if args.feature_space == "physical_enhanced":
        training_features = np.column_stack(
            (raw_training_features, physical_feature_matrix(raw_training_features))
        )
        candidate_features = np.column_stack(
            (raw_candidate_features, physical_feature_matrix(raw_candidate_features))
        )
    else:
        training_features = raw_training_features
        candidate_features = raw_candidate_features
    risk_target = training_frame[TARGET_COLUMN].to_numpy(dtype=float)
    collision_target = (
        training_frame["collision_event_total"].to_numpy(dtype=float) > 0
    ).astype(int)
    if len(np.unique(collision_target)) != 2:
        raise ValueError("碰撞训练标签必须同时包含正负样本")

    repeat_results = []
    risk_matrices = []
    collision_matrices = []
    bootstrap_seed_rows = []
    for repeat_index in range(args.scoring_repeats):
        repeat_seed = args.random_state + repeat_index * 1009
        risk_matrix, risk_seeds = fit_bootstrap_predictions(
            training_features,
            risk_target,
            strata,
            candidate_features,
            args.bootstrap_models,
            args.n_estimators,
            repeat_seed,
        )
        collision_matrix, collision_seeds = fit_collision_bootstrap_predictions(
            training_features,
            collision_target,
            strata,
            candidate_features,
            args.bootstrap_models,
            args.n_estimators,
            repeat_seed,
        )
        risk_matrices.append(risk_matrix)
        collision_matrices.append(collision_matrix)
        bootstrap_seed_rows.append(
            {
                "repeat_index": repeat_index,
                "repeat_seed": repeat_seed,
                "risk_seeds": risk_seeds,
                "collision_seeds": collision_seeds,
            }
        )
        repeat_frame, _, _ = build_scored_frame(
            candidate_frame,
            training_frame,
            feature_columns,
            raw_candidate_features,
            risk_matrix,
            collision_matrix,
            args.top_fraction,
            args.robust_penalty,
        )
        repeat_summary = {"repeat_index": repeat_index, "repeat_seed": repeat_seed}
        for mode_name in SELECTION_MODES:
            selections = select_mode(
                repeat_frame,
                raw_candidate_features,
                mode_name,
                args.select_per_channel,
                args.min_per_target_channel,
                args.diversity_weight,
            )
            selected = selected_frame(repeat_frame, selections)
            repeat_summary[mode_name] = {
                "sample_ids": sorted(selection_ids(selected)),
                "selection_count": len(selected),
            }
        repeat_results.append(repeat_summary)

    final_risk_matrix = np.vstack(risk_matrices)
    final_collision_matrix = np.vstack(collision_matrices)
    scored_frame, top_counts, distance_summary = build_scored_frame(
        candidate_frame,
        training_frame,
        feature_columns,
        raw_candidate_features,
        final_risk_matrix,
        final_collision_matrix,
        args.top_fraction,
        args.robust_penalty,
    )
    final_selections = {}
    final_selected = {}
    for mode_name in SELECTION_MODES:
        selections = select_mode(
            scored_frame,
            raw_candidate_features,
            mode_name,
            args.select_per_channel,
            args.min_per_target_channel,
            args.diversity_weight,
        )
        final_selections[mode_name] = selections
        final_selected[mode_name] = selected_frame(scored_frame, selections)

    repeat_stability = {}
    for mode_name in SELECTION_MODES:
        sets = [set(repeat[mode_name]["sample_ids"]) for repeat in repeat_results]
        pairwise = [
            jaccard(left, right)
            for index, left in enumerate(sets)
            for right in sets[index + 1 :]
        ]
        repeat_stability[mode_name] = {
            "pairwise_jaccard_mean": float(np.mean(pairwise)),
            "pairwise_jaccard_std": float(
                np.std(pairwise, ddof=1) if len(pairwise) > 1 else 0.0
            ),
            "pairwise_jaccard_min": float(np.min(pairwise)),
            "pairwise_jaccard_max": float(np.max(pairwise)),
        }

    single_ids = selection_ids(final_selected["single_channel"])
    dual_ids = selection_ids(final_selected["dual_channel"])
    comparison = {
        "intersection_count": len(single_ids & dual_ids),
        "jaccard": jaccard(single_ids, dual_ids),
        "single_collision_probability_mean": float(
            final_selected["single_channel"]["predicted_collision_probability_mean"].mean()
        ),
        "dual_collision_probability_mean": float(
            final_selected["dual_channel"]["predicted_collision_probability_mean"].mean()
        ),
    }
    summary = {
        "format": "feedback_candidate_scoring_dual_v2",
        "feature_space": args.feature_space,
        "model_feature_count": int(training_features.shape[1]),
        "model_feature_names": (
            list(feature_columns)
            if args.feature_space == "raw_15d"
            else list(feature_columns) + list(physical_feature_names())
        ),
        "physical_feature_version": (
            PHYSICAL_FEATURE_VERSION
            if args.feature_space == "physical_enhanced"
            else None
        ),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": {
            "path": dataset_path,
            "sha256": file_sha256(dataset_path),
            "independent_scenario_count": len(training_frame),
            "collision_scenario_count": int(collision_target.sum()),
            "non_collision_scenario_count": int((collision_target == 0).sum()),
        },
        "candidate_sources": source_files,
        "candidate_count": len(scored_frame),
        "scoring_repeats": args.scoring_repeats,
        "bootstrap_models_per_repeat": args.bootstrap_models,
        "n_estimators_per_model": args.n_estimators,
        "bootstrap_seed_rows": bootstrap_seed_rows,
        "top_count_by_generator_target_cell": top_counts,
        "distance_summary": distance_summary,
        "modes": {
            mode_name: model_summary(scored_frame, final_selected[mode_name], mode_name)
            for mode_name in SELECTION_MODES
        },
        "repeat_stability": repeat_stability,
        "comparison": comparison,
        "interpretation_limits": [
            "连续风险预测和碰撞倾向预测均只用于候选预排序，不能替代 CARLA 实测 observed_risk。",
            "碰撞倾向由 18 个独立碰撞场景训练，不能解释为跨地图、跨控制策略的真实碰撞概率。",
            "单通道与双通道比较只说明离线选择行为差异，不构成生成器优劣结论。",
            "物理增强特征仅由生成前可知的 15 维场景参数计算，不读取遥测、碰撞结果或风险标签。",
        ],
    }

    scored_frame.to_csv(
        output_dir / "scored_candidates.csv", index=False, encoding="utf-8-sig"
    )
    for mode_name, selected in final_selected.items():
        selected.to_csv(
            output_dir / f"{mode_name}_selected.csv",
            index=False,
            encoding="utf-8-sig",
        )
        write_csv(
            output_dir / f"{mode_name}_selection_manifest.csv",
            selected.sort_values(
                ["generator", "selection_channel", "selection_order"]
            ).to_dict(orient="records"),
        )
        write_jsonl(
            output_dir / f"{mode_name}_selected.jsonl",
            selection_table(records, scored_frame, final_selections[mode_name]),
        )
    write_json(output_dir / "scoring_summary.json", summary)
    write_json(output_dir / "repeat_selection_summary.json", {"repeats": repeat_results})
    (output_dir / "dual_channel_candidate_report.md").write_text(
        build_report(
            summary,
            final_selected["single_channel"],
            final_selected["dual_channel"],
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "repeat_index": repeat["repeat_index"],
                "repeat_seed": repeat["repeat_seed"],
                "mode": mode_name,
                "selection_count": repeat[mode_name]["selection_count"],
            }
            for repeat in repeat_results
            for mode_name in SELECTION_MODES
        ]
    ).to_csv(
        output_dir / "repeat_selection_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"[DUAL_SCORE] candidates={len(scored_frame)} | repeats={args.scoring_repeats} | "
        f"models_per_repeat={args.bootstrap_models} | "
        f"single_selected={len(final_selected['single_channel'])} | "
        f"dual_selected={len(final_selected['dual_channel'])}"
    )
    print(
        f"[DUAL_SCORE] overlap={comparison['intersection_count']} | "
        f"jaccard={comparison['jaccard']:.3f} | "
        f"dual_collision_probability={comparison['dual_collision_probability_mean']:.3f}"
    )
    print(f"[DUAL_SCORE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
