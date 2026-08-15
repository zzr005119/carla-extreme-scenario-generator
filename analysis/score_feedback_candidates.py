"""使用重复风险代理对生成候选进行统一评分和三通道选择。"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import FEATURE_NAMES, encode_record, load_jsonl  # noqa: E402
from core.scenario_validator import require_valid_scenario  # noqa: E402


DEFAULT_DATASET = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
    "dataset.csv",
)
FEATURE_PREFIX = "feature_"
TARGET_COLUMN = "observed_risk_score_mean"
GENERATOR_NAMES = {
    "balanced_latin_hypercube_v1": "lhs",
    "conditional_diagonal_gmm_v1": "gmm",
    "conditional_tabular_cvae_v1": "cvae",
}
SELECTION_CHANNELS = (
    "stable_high_score",
    "high_uncertainty",
    "collision_boundary",
)


def parse_args():
    parser = argparse.ArgumentParser(description="反馈引导候选统一评分 V1")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument(
        "--candidates",
        action="append",
        required=True,
        help="候选 JSONL，可重复指定",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap-models", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--top-fraction", type=float, default=0.10)
    parser.add_argument("--robust-penalty", type=float, default=0.50)
    parser.add_argument("--select-per-channel", type=int, default=3)
    parser.add_argument("--diversity-weight", type=float, default=0.20)
    parser.add_argument("--random-state", type=int, default=20260815)
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_args(args):
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
    if not 0.0 <= args.diversity_weight < 1.0:
        raise ValueError("--diversity-weight 必须位于 [0, 1)")


def load_training_frame(path):
    frame = pd.read_csv(path)
    feature_columns = [column for column in frame if column.startswith(FEATURE_PREFIX)]
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        TARGET_COLUMN,
        "collision_event_total",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"风险反馈数据集缺少列: {missing}")
    if len(feature_columns) != len(FEATURE_NAMES):
        raise ValueError(
            f"需要 {len(FEATURE_NAMES)} 个归一化特征，实际为 {len(feature_columns)}"
        )
    if frame[feature_columns + [TARGET_COLUMN]].isna().any().any():
        raise ValueError("风险反馈数据集存在特征或目标缺失值")
    strata = (
        frame["generator"].astype(str)
        + "__"
        + frame["target_risk_level"].astype(str)
    )
    if strata.value_counts().min() < 2:
        raise ValueError("每个生成器×目标档至少需要 2 个独立场景")
    return frame, feature_columns, strata.to_numpy()


def load_candidates(paths):
    records = []
    rows = []
    seen_ids = set()
    source_files = []
    for source_path in paths:
        absolute_path = os.path.abspath(source_path)
        source_records = load_jsonl(absolute_path)
        source_files.append(
            {
                "path": absolute_path,
                "sha256": file_sha256(absolute_path),
                "record_count": len(source_records),
            }
        )
        for record in source_records:
            require_valid_scenario(record)
            sample_id = str(record["sample_id"])
            if sample_id in seen_ids:
                raise ValueError(f"候选 sample_id 重复: {sample_id}")
            seen_ids.add(sample_id)
            generator_id = record["provenance"]["generator"]
            if generator_id not in GENERATOR_NAMES:
                raise ValueError(f"未知生成器标识: {generator_id}")
            vector = encode_record(record).astype(float)
            generator = GENERATOR_NAMES[generator_id]
            target_level = record["conditions"]["target_risk_level"]
            row = {
                "sample_id": sample_id,
                "generator": generator,
                "target_risk_level": target_level,
                "generator_target_cell": f"{generator}__{target_level}",
                "source_path": absolute_path,
            }
            for index, (feature_name, value) in enumerate(
                zip(FEATURE_NAMES, vector), 1
            ):
                row[f"feature_{index:02d}_{feature_name.replace('.', '_')}"] = float(
                    value
                )
            records.append(record)
            rows.append(row)
    if not records:
        raise ValueError("候选池为空")
    return records, pd.DataFrame(rows), source_files


def make_model(random_state, n_estimators):
    return RandomForestRegressor(
        n_estimators=n_estimators,
        min_samples_leaf=2,
        max_features=0.7,
        random_state=random_state,
        n_jobs=-1,
    )


def stratified_bootstrap_indices(strata, generator):
    sampled = []
    for stratum in sorted(set(strata)):
        indices = np.flatnonzero(strata == stratum)
        sampled.extend(generator.choice(indices, size=len(indices), replace=True))
    generator.shuffle(sampled)
    return np.asarray(sampled, dtype=int)


def fit_bootstrap_predictions(
    training_features,
    target,
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
        model = make_model(repeat_seed, n_estimators)
        model.fit(training_features[train_indices], target[train_indices])
        prediction_matrix[repeat_index] = model.predict(candidate_features)
        seeds.append(repeat_seed)
    return prediction_matrix, seeds


def normalized_distances(left, right):
    differences = left[:, None, :] - right[None, :, :]
    return np.linalg.norm(differences, axis=2) / math.sqrt(left.shape[1])


def percentile_rank(values):
    series = pd.Series(np.asarray(values, dtype=float))
    if len(series) == 1:
        return np.ones(1, dtype=float)
    return series.rank(method="average", pct=True).to_numpy(dtype=float)


def add_top_frequencies(frame, prediction_matrix, top_fraction):
    frequencies = np.zeros(len(frame), dtype=float)
    top_counts = {}
    for cell, cell_frame in frame.groupby("generator_target_cell", sort=True):
        indices = cell_frame.index.to_numpy(dtype=int)
        top_count = max(1, int(math.ceil(len(indices) * top_fraction)))
        top_counts[cell] = top_count
        selected_counts = np.zeros(len(indices), dtype=int)
        sample_ids = frame.loc[indices, "sample_id"].astype(str).to_numpy()
        for predictions in prediction_matrix[:, indices]:
            order = np.lexsort((sample_ids, -predictions))
            selected_counts[order[:top_count]] += 1
        frequencies[indices] = selected_counts / prediction_matrix.shape[0]
    frame["bootstrap_top_k_frequency"] = frequencies
    return top_counts


def add_distance_scores(frame, candidate_features, training_frame, feature_columns):
    training_features = training_frame[feature_columns].to_numpy(dtype=float)
    collision_mask = training_frame["collision_event_total"].to_numpy(dtype=float) > 0
    if not collision_mask.any():
        raise ValueError("风险反馈数据集中没有碰撞样本，无法建立碰撞边界通道")
    if collision_mask.all():
        raise ValueError("风险反馈数据集中没有非碰撞样本，无法建立碰撞边界通道")

    all_distances = normalized_distances(candidate_features, training_features)
    collision_distances = normalized_distances(
        candidate_features, training_features[collision_mask]
    )
    non_collision_distances = normalized_distances(
        candidate_features, training_features[~collision_mask]
    )
    nearest_observed = all_distances.min(axis=1)
    nearest_collision = collision_distances.min(axis=1)
    nearest_non_collision = non_collision_distances.min(axis=1)
    margin = nearest_non_collision - nearest_collision

    collision_scale = max(float(np.median(nearest_collision)), 1e-6)
    margin_scale = max(float(np.median(np.abs(margin))), 1e-6)
    collision_affinity = np.exp(-nearest_collision / collision_scale)
    boundary_balance = np.exp(-np.abs(margin) / margin_scale)
    boundary_score = np.sqrt(collision_affinity * boundary_balance)

    frame["nearest_observed_distance"] = nearest_observed
    frame["nearest_collision_distance"] = nearest_collision
    frame["nearest_non_collision_distance"] = nearest_non_collision
    frame["collision_distance_margin"] = margin
    frame["collision_affinity"] = collision_affinity
    frame["collision_boundary_balance"] = boundary_balance
    frame["collision_boundary_score"] = boundary_score
    return {
        "collision_sample_count": int(collision_mask.sum()),
        "non_collision_sample_count": int((~collision_mask).sum()),
        "collision_distance_scale": collision_scale,
        "collision_margin_scale": margin_scale,
    }


def add_channel_scores(frame):
    frame["stable_high_score_base"] = 0.70 * percentile_rank(
        frame["robust_predicted_risk_score"]
    ) + 0.30 * percentile_rank(frame["bootstrap_top_k_frequency"])
    frame["high_uncertainty_base"] = 0.75 * percentile_rank(
        frame["predicted_risk_std"]
    ) + 0.25 * percentile_rank(frame["predicted_risk_mean"])
    frame["collision_boundary_base"] = 0.70 * percentile_rank(
        frame["collision_boundary_score"]
    ) + 0.20 * percentile_rank(frame["predicted_risk_std"]) + 0.10 * percentile_rank(
        frame["predicted_risk_mean"]
    )


def min_distance_to_selected(candidate, selected_features, nearest_observed):
    if not selected_features:
        return float(nearest_observed)
    selected = np.asarray(selected_features, dtype=float)
    distances = np.linalg.norm(selected - candidate, axis=1) / math.sqrt(
        candidate.shape[0]
    )
    return float(distances.min())


def greedy_select(
    frame,
    features,
    candidate_indices,
    base_column,
    count,
    diversity_weight,
    excluded,
    selected_features,
):
    available = [index for index in candidate_indices if index not in excluded]
    selections = []
    while available and len(selections) < count:
        best = None
        for index in available:
            diversity_distance = min_distance_to_selected(
                features[index],
                selected_features,
                frame.at[index, "nearest_observed_distance"],
            )
            utility = (
                (1.0 - diversity_weight) * float(frame.at[index, base_column])
                + diversity_weight * diversity_distance
            )
            key = (
                utility,
                float(frame.at[index, base_column]),
                str(frame.at[index, "sample_id"]),
            )
            if best is None or key > best[0]:
                best = (key, index, diversity_distance, utility)
        _, selected_index, diversity_distance, utility = best
        selections.append(
            {
                "index": selected_index,
                "diversity_distance": diversity_distance,
                "selection_utility": utility,
            }
        )
        excluded.add(selected_index)
        selected_features.append(features[selected_index])
        available.remove(selected_index)
    return selections


def select_channels(frame, features, per_channel, diversity_weight):
    channel_columns = {
        "stable_high_score": "stable_high_score_base",
        "high_uncertainty": "high_uncertainty_base",
        "collision_boundary": "collision_boundary_base",
    }
    selected_rows = []
    for generator, generator_frame in frame.groupby("generator", sort=True):
        candidate_indices = generator_frame.index.to_list()
        excluded = set()
        selected_features = []
        for channel in SELECTION_CHANNELS:
            selections = greedy_select(
                frame,
                features,
                candidate_indices,
                channel_columns[channel],
                per_channel,
                diversity_weight,
                excluded,
                selected_features,
            )
            if len(selections) != per_channel:
                raise ValueError(
                    f"{generator} 的 {channel} 通道仅能选择 {len(selections)} 个候选"
                )
            for order, selection in enumerate(selections, 1):
                selected_rows.append(
                    {
                        "index": selection["index"],
                        "generator": generator,
                        "selection_channel": channel,
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


def augmented_records(records, scored_frame, selections):
    selection_by_index = {selection["index"]: selection for selection in selections}
    scored_records = []
    selected_records = []
    score_columns = (
        "predicted_risk_mean",
        "predicted_risk_std",
        "predicted_risk_min",
        "predicted_risk_max",
        "robust_predicted_risk_score",
        "bootstrap_top_k_frequency",
        "nearest_observed_distance",
        "nearest_collision_distance",
        "nearest_non_collision_distance",
        "collision_distance_margin",
        "collision_boundary_score",
    )
    for index, source in enumerate(records):
        record = json.loads(json.dumps(source, ensure_ascii=False))
        scoring = {
            "format": "feedback_candidate_score_v1",
            **{
                column: float(scored_frame.at[index, column])
                for column in score_columns
            },
        }
        if index in selection_by_index:
            selection = selection_by_index[index]
            scoring["selected"] = True
            scoring["selection_channel"] = selection["selection_channel"]
            scoring["selection_order"] = selection["selection_order"]
            scoring["selection_utility"] = float(selection["selection_utility"])
            scoring["selection_diversity_distance"] = float(
                selection["selection_diversity_distance"]
            )
        else:
            scoring["selected"] = False
        record["candidate_scoring"] = scoring
        scored_records.append(record)
        if scoring["selected"]:
            selected_records.append(record)
    return scored_records, selected_records


def build_summary(
    args,
    dataset_path,
    source_files,
    training_frame,
    scored_frame,
    selected,
    top_counts,
    distance_summary,
    bootstrap_seeds,
):
    selection_counts = defaultdict(lambda: defaultdict(int))
    selected_targets = defaultdict(lambda: defaultdict(int))
    for row in selected.to_dict(orient="records"):
        selection_counts[row["generator"]][row["selection_channel"]] += 1
        selected_targets[row["generator"]][row["target_risk_level"]] += 1
    candidate_counts = (
        scored_frame.groupby(["generator", "target_risk_level"])
        .size()
        .to_dict()
    )
    return {
        "format": "feedback_candidate_scoring_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": {
            "path": dataset_path,
            "sha256": file_sha256(dataset_path),
            "independent_scenario_count": len(training_frame),
            "collision_scenario_count": distance_summary["collision_sample_count"],
            "non_collision_scenario_count": distance_summary[
                "non_collision_sample_count"
            ],
        },
        "candidate_sources": source_files,
        "candidate_count": len(scored_frame),
        "candidate_count_by_generator_target": {
            f"{generator}__{target}": int(count)
            for (generator, target), count in sorted(candidate_counts.items())
        },
        "bootstrap": {
            "method": "generator_target_stratified_bootstrap_random_forest",
            "model_count": args.bootstrap_models,
            "n_estimators_per_model": args.n_estimators,
            "min_samples_leaf": 2,
            "max_features": 0.7,
            "random_state": args.random_state,
            "seeds": bootstrap_seeds,
        },
        "scoring": {
            "robust_score": (
                f"predicted_mean - {args.robust_penalty} * predicted_std"
            ),
            "top_fraction_per_generator_target_cell": args.top_fraction,
            "top_count_by_cell": top_counts,
            "distance_metric": "normalized_euclidean_divided_by_sqrt_15",
            "collision_boundary": {
                "definition": (
                    "sqrt(exp(-d_collision/scale_collision) * "
                    "exp(-abs(d_non_collision-d_collision)/scale_margin))"
                ),
                "collision_distance_scale": distance_summary[
                    "collision_distance_scale"
                ],
                "collision_margin_scale": distance_summary[
                    "collision_margin_scale"
                ],
            },
        },
        "selection": {
            "channels": list(SELECTION_CHANNELS),
            "per_generator_channel": args.select_per_channel,
            "diversity_weight": args.diversity_weight,
            "selected_count": len(selected),
            "counts_by_generator_channel": {
                generator: dict(channels)
                for generator, channels in selection_counts.items()
            },
            "target_counts_by_generator": {
                generator: dict(targets)
                for generator, targets in selected_targets.items()
            },
        },
        "interpretation_limits": [
            "预测分数仅用于候选预排序，不能替代 CARLA 实测 observed_risk。",
            "碰撞边界通道仅由 3 个已知碰撞场景提供邻域线索，不是碰撞概率模型。",
            "三种生成器使用相同评分、Top-K 和多样性规则。",
        ],
    }


def build_report(summary, selected):
    lines = [
        "# 反馈候选评分 V1",
        "",
        f"- 风险反馈训练样本：`{summary['dataset']['independent_scenario_count']}` 个独立场景。",
        f"- 已知碰撞场景：`{summary['dataset']['collision_scenario_count']}` 个。",
        f"- 候选池：`{summary['candidate_count']}` 个场景。",
        f"- Bootstrap 随机森林：`{summary['bootstrap']['model_count']}` 个。",
        f"- 最终短名单：`{summary['selection']['selected_count']}` 个场景。",
        "",
        "## 三通道",
        "",
        "1. `stable_high_score`：优先选择稳健预测分高且重复 Top-K 入选频率高的候选。",
        "2. `high_uncertainty`：优先选择模型间预测分歧大、同时具有一定风险水平的候选。",
        "3. `collision_boundary`：优先选择靠近已知碰撞样本且接近碰撞/非碰撞邻域边界的候选。",
        "",
        "## 选择结果",
        "",
        "| 生成器 | 通道 | 样本 | 目标档 | 均值 | 标准差 | 稳健分 | Top-K频率 | 碰撞距离 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in selected.sort_values(
        ["generator", "selection_channel", "selection_order"]
    ).to_dict(orient="records"):
        lines.append(
            "| {generator} | {selection_channel} | `{sample_id}` | {target_risk_level} | "
            "{predicted_risk_mean:.3f} | {predicted_risk_std:.3f} | "
            "{robust_predicted_risk_score:.3f} | {bootstrap_top_k_frequency:.3f} | "
            "{nearest_collision_distance:.3f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果只形成 CARLA 外部验证短名单。预测分、碰撞邻域分和目标风险档都不能替代实测风险；碰撞通道尤其不能解释为碰撞概率。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    args = parse_args()
    validate_args(args)
    dataset_path = os.path.abspath(args.dataset)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    training_frame, feature_columns, strata = load_training_frame(dataset_path)
    records, scored_frame, source_files = load_candidates(args.candidates)
    candidate_feature_columns = [
        column for column in scored_frame if column.startswith(FEATURE_PREFIX)
    ]
    training_features = training_frame[feature_columns].to_numpy(dtype=float)
    candidate_features = scored_frame[candidate_feature_columns].to_numpy(dtype=float)
    target = training_frame[TARGET_COLUMN].to_numpy(dtype=float)

    prediction_matrix, bootstrap_seeds = fit_bootstrap_predictions(
        training_features,
        target,
        strata,
        candidate_features,
        args.bootstrap_models,
        args.n_estimators,
        args.random_state,
    )
    scored_frame["predicted_risk_mean"] = prediction_matrix.mean(axis=0)
    scored_frame["predicted_risk_std"] = prediction_matrix.std(axis=0, ddof=1)
    scored_frame["predicted_risk_min"] = prediction_matrix.min(axis=0)
    scored_frame["predicted_risk_max"] = prediction_matrix.max(axis=0)
    scored_frame["robust_predicted_risk_score"] = (
        scored_frame["predicted_risk_mean"]
        - args.robust_penalty * scored_frame["predicted_risk_std"]
    )
    top_counts = add_top_frequencies(
        scored_frame, prediction_matrix, args.top_fraction
    )
    distance_summary = add_distance_scores(
        scored_frame,
        candidate_features,
        training_frame,
        feature_columns,
    )
    add_channel_scores(scored_frame)
    selections = select_channels(
        scored_frame,
        candidate_features,
        args.select_per_channel,
        args.diversity_weight,
    )
    selected = selected_frame(scored_frame, selections)
    scored_records, selected_records = augmented_records(
        records, scored_frame, selections
    )

    scored_frame.to_csv(
        output_dir / "scored_candidates.csv", index=False, encoding="utf-8-sig"
    )
    selected.to_csv(
        output_dir / "selected_candidates.csv", index=False, encoding="utf-8-sig"
    )
    write_jsonl(output_dir / "scored_candidates.jsonl", scored_records)
    write_jsonl(output_dir / "selected_candidates.jsonl", selected_records)
    write_json(output_dir / "selected_candidates.json", selected_records)
    summary = build_summary(
        args,
        dataset_path,
        source_files,
        training_frame,
        scored_frame,
        selected,
        top_counts,
        distance_summary,
        bootstrap_seeds,
    )
    write_json(output_dir / "scoring_summary.json", summary)
    (output_dir / "feedback_candidate_report.md").write_text(
        build_report(summary, selected) + "\n", encoding="utf-8"
    )
    write_csv(
        output_dir / "selection_manifest.csv",
        selected.sort_values(
            ["generator", "selection_channel", "selection_order"]
        ).to_dict(orient="records"),
    )

    print(
        f"[SCORE] candidates={len(scored_frame)} | "
        f"bootstrap_models={args.bootstrap_models} | selected={len(selected)}"
    )
    print(f"[SCORE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
