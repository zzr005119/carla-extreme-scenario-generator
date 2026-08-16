"""诊断 heuristic_v2 连续风险与碰撞分量的可预测性。"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold


FEATURE_PREFIX = "feature_"
TOTAL_SCORE_COLUMN = "observed_risk_score_mean"
COLLISION_RATE_COLUMN = "collision_run_rate"
RISK_LEVELS = ("low", "medium", "high", "critical")
MODEL_NAMES = ("single_total", "decomposed", "oracle_collision")


def parse_args():
    parser = argparse.ArgumentParser(
        description="风险分数连续分量与碰撞分量拆解校准"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=9)
    parser.add_argument("--random-state", type=int, default=20260816)
    parser.add_argument("--collision-weight", type=float, default=0.25)
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def make_regressor(random_state, n_estimators):
    return RandomForestRegressor(
        n_estimators=n_estimators,
        min_samples_leaf=2,
        max_features=0.7,
        random_state=random_state,
        n_jobs=-1,
    )


def spearman_score(actual, predicted):
    result = spearmanr(actual, predicted)
    value = getattr(result, "statistic", result[0])
    return None if np.isnan(value) else float(value)


def ranked_indices(values, sample_ids):
    return sorted(
        range(len(values)),
        key=lambda index: (-float(values[index]), str(sample_ids[index])),
    )


def top_indices(values, sample_ids, top_k):
    return set(ranked_indices(values, sample_ids)[:top_k])


def rank_values(values, sample_ids):
    order = ranked_indices(values, sample_ids)
    ranks = np.empty(len(values), dtype=float)
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank
    return ranks


def pairwise_jaccard(sets):
    values = []
    for left_index in range(len(sets)):
        for right_index in range(left_index + 1, len(sets)):
            left = sets[left_index]
            right = sets[right_index]
            union = left | right
            values.append(len(left & right) / len(union) if union else 1.0)
    return values


def metric_summary(values):
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array, ddof=1)) if len(array) > 1 else 0.0,
        "p05": float(np.quantile(array, 0.05)),
        "median": float(np.quantile(array, 0.5)),
        "p95": float(np.quantile(array, 0.95)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def validate_frame(frame, collision_weight):
    feature_columns = [
        column for column in frame.columns if column.startswith(FEATURE_PREFIX)
    ]
    if len(feature_columns) != 15:
        raise ValueError(f"需要 15 个归一化参数特征，实际为 {len(feature_columns)}")
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        TOTAL_SCORE_COLUMN,
        COLLISION_RATE_COLUMN,
        "collision_event_total",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"数据集缺少字段: {missing}")
    if frame[feature_columns + [TOTAL_SCORE_COLUMN, COLLISION_RATE_COLUMN]].isna().any().any():
        raise ValueError("模型输入或目标列存在缺失值")
    if frame["sample_id"].duplicated().any():
        raise ValueError("sample_id 必须对应独立场景且不可重复")
    invalid_levels = sorted(set(frame["target_risk_level"]) - set(RISK_LEVELS))
    if invalid_levels:
        raise ValueError(f"存在未知目标风险档: {invalid_levels}")
    collision_rate = frame[COLLISION_RATE_COLUMN].to_numpy(dtype=float)
    if np.any((collision_rate < 0.0) | (collision_rate > 1.0)):
        raise ValueError("collision_run_rate 必须位于 [0, 1]")
    if not 0.0 < collision_weight < 1.0:
        raise ValueError("--collision-weight 必须位于 (0, 1)")
    return feature_columns


def derive_continuous_score(total_score, collision_rate, collision_weight):
    continuous_weight = 1.0 - collision_weight
    score = (
        total_score - 100.0 * collision_weight * collision_rate
    ) / continuous_weight
    if np.any((score < -0.01) | (score > 100.01)):
        raise ValueError("拆解后的连续风险分数超出合理范围，请核对碰撞权重")
    return np.clip(score, 0.0, 100.0)


def prediction_metrics(actual, predicted, top_k, sample_ids, target_levels):
    actual_high = actual >= 50.0
    predicted_high = predicted >= 50.0
    actual_top = top_indices(actual, sample_ids, top_k)
    predicted_top = top_indices(predicted, sample_ids, top_k)
    target_means = (
        pd.Series(predicted)
        .groupby(pd.Series(target_levels))
        .mean()
        .reindex(RISK_LEVELS)
    )
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r2": float(r2_score(actual, predicted)),
        "spearman": spearman_score(actual, predicted),
        "mean_bias": float(np.mean(predicted - actual)),
        "high_or_critical_recall": float(
            np.sum(actual_high & predicted_high) / max(1, np.sum(actual_high))
        ),
        "high_or_critical_precision": float(
            np.sum(actual_high & predicted_high) / max(1, np.sum(predicted_high))
        ),
        "top_k_observed_recall": float(
            len(actual_top & predicted_top) / max(1, top_k)
        ),
        "target_mean_ordering_strict": bool(
            target_means.notna().all()
            and all(
                left < right
                for left, right in zip(target_means, target_means.iloc[1:])
            )
        ),
    }


def run_repeated_oof(frame, feature_columns, args):
    features = frame[feature_columns].to_numpy(dtype=float)
    total_score = frame[TOTAL_SCORE_COLUMN].to_numpy(dtype=float)
    collision_rate = frame[COLLISION_RATE_COLUMN].to_numpy(dtype=float)
    collision_label = (
        frame["collision_event_total"].to_numpy(dtype=float) > 0.0
    ).astype(int)
    continuous_score = derive_continuous_score(
        total_score,
        collision_rate,
        args.collision_weight,
    )
    sample_ids = frame["sample_id"].astype(str).to_numpy()
    target_levels = frame["target_risk_level"].astype(str).to_numpy()
    strata = (
        frame["generator"].astype(str)
        + "__"
        + frame["target_risk_level"].astype(str)
    ).to_numpy()
    if pd.Series(strata).value_counts().min() < 3:
        raise ValueError("每个生成器×目标档至少需要 3 个独立场景")

    prediction_matrices = {
        name: np.full((args.repeats, len(frame)), np.nan, dtype=float)
        for name in MODEL_NAMES
    }
    collision_rate_matrix = np.full(
        (args.repeats, len(frame)), np.nan, dtype=float
    )
    continuous_score_matrix = np.full(
        (args.repeats, len(frame)), np.nan, dtype=float
    )
    top_sets = {name: [] for name in MODEL_NAMES}
    metric_rows = []
    prediction_rows = []
    collision_rows = []

    for repeat_index in range(args.repeats):
        split_seed = args.random_state + repeat_index
        splitter = StratifiedKFold(
            n_splits=3,
            shuffle=True,
            random_state=split_seed,
        )
        splits = list(splitter.split(features, strata))
        single_predictions = np.full(len(frame), np.nan, dtype=float)
        continuous_predictions = np.full(len(frame), np.nan, dtype=float)
        collision_rate_predictions = np.full(len(frame), np.nan, dtype=float)

        for fold_index, (train_index, test_index) in enumerate(splits):
            seed_base = args.random_state + repeat_index * 100 + fold_index * 10
            single_model = make_regressor(seed_base, args.n_estimators)
            continuous_model = make_regressor(seed_base + 1, args.n_estimators)
            collision_model = make_regressor(seed_base + 2, args.n_estimators)

            single_model.fit(features[train_index], total_score[train_index])
            continuous_model.fit(
                features[train_index], continuous_score[train_index]
            )
            collision_model.fit(
                features[train_index], collision_rate[train_index]
            )

            single_predictions[test_index] = single_model.predict(
                features[test_index]
            )
            continuous_predictions[test_index] = continuous_model.predict(
                features[test_index]
            )
            collision_rate_predictions[test_index] = np.clip(
                collision_model.predict(features[test_index]),
                0.0,
                1.0,
            )

        if any(
            np.isnan(values).any()
            for values in (
                single_predictions,
                continuous_predictions,
                collision_rate_predictions,
            )
        ):
            raise RuntimeError("重复交叉验证产生了缺失预测")

        decomposed_predictions = (
            (1.0 - args.collision_weight) * continuous_predictions
            + 100.0 * args.collision_weight * collision_rate_predictions
        )
        oracle_predictions = (
            (1.0 - args.collision_weight) * continuous_predictions
            + 100.0 * args.collision_weight * collision_rate
        )
        current_predictions = {
            "single_total": single_predictions,
            "decomposed": decomposed_predictions,
            "oracle_collision": oracle_predictions,
        }
        collision_rate_matrix[repeat_index] = collision_rate_predictions
        continuous_score_matrix[repeat_index] = continuous_predictions

        collision_rows.append(
            {
                "repeat_index": repeat_index,
                "split_seed": split_seed,
                "collision_rate_mae": float(
                    mean_absolute_error(collision_rate, collision_rate_predictions)
                ),
                "collision_rate_rmse": float(
                    mean_squared_error(
                        collision_rate, collision_rate_predictions
                    )
                    ** 0.5
                ),
                "collision_label_average_precision": float(
                    average_precision_score(
                        collision_label, collision_rate_predictions
                    )
                ),
                "collision_label_roc_auc": float(
                    roc_auc_score(collision_label, collision_rate_predictions)
                ),
            }
        )

        for model_name, predictions in current_predictions.items():
            prediction_matrices[model_name][repeat_index] = predictions
            selected_top = top_indices(predictions, sample_ids, args.top_k)
            top_sets[model_name].append(selected_top)
            metrics = prediction_metrics(
                total_score,
                predictions,
                args.top_k,
                sample_ids,
                target_levels,
            )
            metric_rows.append(
                {
                    "model": model_name,
                    "repeat_index": repeat_index,
                    "split_seed": split_seed,
                    **metrics,
                }
            )
            ranks = rank_values(predictions, sample_ids)
            for sample_index, sample_id in enumerate(sample_ids):
                prediction_rows.append(
                    {
                        "model": model_name,
                        "repeat_index": repeat_index,
                        "sample_id": sample_id,
                        "generator": frame.iloc[sample_index]["generator"],
                        "target_risk_level": target_levels[sample_index],
                        "collision_status": (
                            "collision"
                            if collision_label[sample_index]
                            else "no_collision"
                        ),
                        "observed_total_score": total_score[sample_index],
                        "observed_continuous_score": continuous_score[sample_index],
                        "observed_collision_run_rate": collision_rate[sample_index],
                        "predicted_total_score": predictions[sample_index],
                        "predicted_continuous_score": continuous_predictions[
                            sample_index
                        ],
                        "predicted_collision_run_rate": collision_rate_predictions[
                            sample_index
                        ],
                        "prediction_error": (
                            predictions[sample_index] - total_score[sample_index]
                        ),
                        "absolute_error": abs(
                            predictions[sample_index] - total_score[sample_index]
                        ),
                        "predicted_rank": ranks[sample_index],
                        "selected_in_top_k": sample_index in selected_top,
                    }
                )

    return {
        "total_score": total_score,
        "continuous_score": continuous_score,
        "collision_rate": collision_rate,
        "collision_label": collision_label,
        "sample_ids": sample_ids,
        "prediction_matrices": prediction_matrices,
        "collision_rate_matrix": collision_rate_matrix,
        "continuous_score_matrix": continuous_score_matrix,
        "top_sets": top_sets,
        "metric_frame": pd.DataFrame(metric_rows),
        "prediction_frame": pd.DataFrame(prediction_rows),
        "collision_frame": pd.DataFrame(collision_rows),
    }


def build_sample_summary(frame, result, top_k):
    rows = []
    total_score = result["total_score"]
    sample_ids = result["sample_ids"]
    actual_ranks = rank_values(total_score, sample_ids)
    for model_name in MODEL_NAMES:
        matrix = result["prediction_matrices"][model_name]
        rank_matrix = np.vstack(
            [rank_values(predictions, sample_ids) for predictions in matrix]
        )
        top_frequency = np.zeros(len(frame), dtype=float)
        for selected in result["top_sets"][model_name]:
            for index in selected:
                top_frequency[index] += 1.0
        top_frequency /= len(result["top_sets"][model_name])
        for sample_index, source in frame.iterrows():
            predictions = matrix[:, sample_index]
            errors = predictions - total_score[sample_index]
            rows.append(
                {
                    "model": model_name,
                    "sample_id": source["sample_id"],
                    "generator": source["generator"],
                    "target_risk_level": source["target_risk_level"],
                    "collision_status": (
                        "collision"
                        if int(source["collision_event_total"]) > 0
                        else "no_collision"
                    ),
                    "observed_total_score": total_score[sample_index],
                    "observed_continuous_score": result["continuous_score"][
                        sample_index
                    ],
                    "observed_collision_run_rate": result["collision_rate"][
                        sample_index
                    ],
                    "predicted_total_score_mean": float(np.mean(predictions)),
                    "predicted_total_score_std": float(
                        np.std(predictions, ddof=1)
                    ),
                    "mean_error": float(np.mean(errors)),
                    "mean_absolute_error": float(np.mean(np.abs(errors))),
                    "actual_rank": float(actual_ranks[sample_index]),
                    "predicted_rank_mean": float(
                        np.mean(rank_matrix[:, sample_index])
                    ),
                    "predicted_rank_std": float(
                        np.std(rank_matrix[:, sample_index], ddof=1)
                    ),
                    "top_k": top_k,
                    "top_k_selection_frequency": float(
                        top_frequency[sample_index]
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_summary(frame, result, args, dataset_path, dataset_sha256):
    metric_frame = result["metric_frame"]
    sample_frame = build_sample_summary(frame, result, args.top_k)
    models = {}
    for model_name in MODEL_NAMES:
        metrics = metric_frame[metric_frame["model"] == model_name]
        samples = sample_frame[sample_frame["model"] == model_name]
        collision_error = {}
        for status, group in samples.groupby("collision_status", sort=True):
            collision_error[status] = {
                "sample_count": int(len(group)),
                "observed_score_mean": float(
                    group["observed_total_score"].mean()
                ),
                "predicted_score_mean": float(
                    group["predicted_total_score_mean"].mean()
                ),
                "mean_bias": float(group["mean_error"].mean()),
                "mae": float(group["mean_absolute_error"].mean()),
            }
        models[model_name] = {
            "metrics": {
                name: metric_summary(metrics[name])
                for name in (
                    "mae",
                    "rmse",
                    "r2",
                    "spearman",
                    "mean_bias",
                    "high_or_critical_recall",
                    "high_or_critical_precision",
                    "top_k_observed_recall",
                )
            },
            "target_mean_ordering_strict_rate": float(
                metrics["target_mean_ordering_strict"].mean()
            ),
            "ranking_stability": {
                "pairwise_top_k_jaccard": metric_summary(
                    pairwise_jaccard(result["top_sets"][model_name])
                ),
                "mean_sample_rank_std": float(
                    samples["predicted_rank_std"].mean()
                ),
                "maximum_sample_rank_std": float(
                    samples["predicted_rank_std"].max()
                ),
                "stable_top_k_sample_count": int(
                    np.sum(samples["top_k_selection_frequency"] >= 0.8)
                ),
            },
            "collision_error": collision_error,
        }

    collision_metrics = {
        name: metric_summary(result["collision_frame"][name])
        for name in (
            "collision_rate_mae",
            "collision_rate_rmse",
            "collision_label_average_precision",
            "collision_label_roc_auc",
        )
    }
    return sample_frame, {
        "format": "risk_score_decomposition_v1",
        "dataset": dataset_path,
        "dataset_sha256": dataset_sha256,
        "independent_scenario_count": int(len(frame)),
        "collision_scenario_count": int(
            np.sum(frame["collision_event_total"].to_numpy(dtype=float) > 0)
        ),
        "collision_weight": args.collision_weight,
        "continuous_weight": 1.0 - args.collision_weight,
        "decomposition_formula": (
            "continuous_score = (total_score - 100 * collision_weight * "
            "collision_run_rate) / continuous_weight"
        ),
        "repeated_stratified_oof": {
            "repeats": args.repeats,
            "folds": 3,
            "strata": "generator__target_risk_level",
            "random_state": args.random_state,
        },
        "top_k": args.top_k,
        "models": models,
        "collision_rate_proxy": collision_metrics,
        "decision_rule": (
            "只有 decomposed 同时改善总体误差、碰撞子集偏差或 Top-K 稳定性，"
            "才考虑替代单一连续代理；oracle_collision 只用于估计碰撞分量预测的理论上限。"
        ),
        "interpretation_boundary": (
            f"{len(frame)} 个独立场景只支持工程校准诊断；"
            "拆解基于当前 heuristic_v2 的固定碰撞权重，不修改 CARLA 实测标签。"
        ),
    }


def build_report(summary):
    single = summary["models"]["single_total"]
    decomposed = summary["models"]["decomposed"]
    oracle = summary["models"]["oracle_collision"]
    collision = summary["collision_rate_proxy"]

    def mean(model, metric):
        return model["metrics"][metric]["mean"]

    single_collision = single["collision_error"]["collision"]
    decomposed_collision = decomposed["collision_error"]["collision"]
    oracle_collision = oracle["collision_error"]["collision"]
    lines = [
        "# 风险分数拆解校准 V1",
        "",
        "## 方法",
        "",
        f"- 独立场景：`{summary['independent_scenario_count']}` 个；碰撞场景：`{summary['collision_scenario_count']}` 个。",
        f"- 当前 `heuristic_v2` 碰撞权重：`{summary['collision_weight']:.2f}`，其余连续风险权重：`{summary['continuous_weight']:.2f}`。",
        "- `single_total`：直接预测最终风险分数。",
        "- `decomposed`：分别预测连续风险分量和碰撞运行率，再按原权重合成。",
        "- `oracle_collision`：使用真实碰撞运行率合成，仅用于判断碰撞分量预测是否为主要瓶颈。",
        f"- 重复分层三折 OOF：`{summary['repeated_stratified_oof']['repeats']}` 次；Top-`{summary['top_k']}`。",
        "",
        "## 主要结果",
        "",
        f"- 总体 MAE：单模型 `{mean(single, 'mae'):.3f}`，拆解模型 `{mean(decomposed, 'mae'):.3f}`，碰撞真值上限 `{mean(oracle, 'mae'):.3f}`。",
        f"- Spearman：单模型 `{mean(single, 'spearman'):.3f}`，拆解模型 `{mean(decomposed, 'spearman'):.3f}`，碰撞真值上限 `{mean(oracle, 'spearman'):.3f}`。",
        f"- Top-{summary['top_k']} 两两 Jaccard：单模型 `{single['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`，拆解模型 `{decomposed['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`，碰撞真值上限 `{oracle['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`。",
        f"- 碰撞场景 MAE：单模型 `{single_collision['mae']:.3f}`，拆解模型 `{decomposed_collision['mae']:.3f}`，碰撞真值上限 `{oracle_collision['mae']:.3f}`。",
        f"- 碰撞场景平均偏差：单模型 `{single_collision['mean_bias']:.3f}`，拆解模型 `{decomposed_collision['mean_bias']:.3f}`，碰撞真值上限 `{oracle_collision['mean_bias']:.3f}`。",
        f"- 碰撞运行率代理 MAE：`{collision['collision_rate_mae']['mean']:.3f}`；碰撞标签 AP：`{collision['collision_label_average_precision']['mean']:.3f}`；ROC-AUC：`{collision['collision_label_roc_auc']['mean']:.3f}`。",
        "",
        "## 决策规则",
        "",
        summary["decision_rule"],
        "",
        "不根据本实验直接修改 `heuristic_v2` 权重；先判断问题来自风险分数定义，还是来自静态参数无法稳定预测碰撞结果。",
        "",
        "## 解释边界",
        "",
        summary["interpretation_boundary"],
    ]
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    if args.repeats < 2:
        raise ValueError("--repeats 必须至少为 2")
    if args.n_estimators <= 0:
        raise ValueError("--n-estimators 必须大于 0")
    dataset_path = os.path.abspath(args.dataset)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(dataset_path)
    feature_columns = validate_frame(frame, args.collision_weight)
    result = run_repeated_oof(frame, feature_columns, args)
    sample_frame, summary = build_summary(
        frame,
        result,
        args,
        dataset_path,
        file_sha256(dataset_path),
    )

    result["metric_frame"].to_csv(
        output_dir / "repeat_metrics.csv", index=False, encoding="utf-8-sig"
    )
    result["prediction_frame"].to_csv(
        output_dir / "repeat_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )
    result["collision_frame"].to_csv(
        output_dir / "collision_rate_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    sample_frame.to_csv(
        output_dir / "sample_summary.csv", index=False, encoding="utf-8-sig"
    )
    write_json(output_dir / "decomposition_summary.json", summary)
    (output_dir / "risk_score_decomposition_report.md").write_text(
        build_report(summary), encoding="utf-8"
    )

    single = summary["models"]["single_total"]["metrics"]
    decomposed = summary["models"]["decomposed"]["metrics"]
    print(
        f"[DECOMPOSE] samples={len(frame)} | "
        f"single_mae={single['mae']['mean']:.3f} | "
        f"decomposed_mae={decomposed['mae']['mean']:.3f}"
    )
    print(f"[DECOMPOSE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
