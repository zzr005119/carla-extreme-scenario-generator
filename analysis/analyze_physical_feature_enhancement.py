"""比较原始参数与物理交互派生特征对风险代理的影响。"""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
    r2_score,
)
from sklearn.model_selection import StratifiedKFold

from core.physical_features import (
    PHYSICAL_FEATURE_VERSION,
    physical_feature_matrix,
    physical_feature_names,
)


FEATURE_PREFIX = "feature_"
TARGET_COLUMN = "observed_risk_score_mean"
COLLISION_COLUMN = "collision_event_total"
MODEL_NAMES = ("baseline", "physical_enhanced")
RISK_LEVELS = ("low", "medium", "high", "critical")


def parse_args():
    parser = argparse.ArgumentParser(description="物理交互特征增强诊断")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=9)
    parser.add_argument("--random-state", type=int, default=20260817)
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


def make_classifier(random_state, n_estimators):
    return RandomForestClassifier(
        n_estimators=n_estimators,
        min_samples_leaf=2,
        max_features=0.7,
        class_weight="balanced",
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


def rank_array(values, sample_ids):
    ranks = np.empty(len(values), dtype=float)
    for rank, index in enumerate(ranked_indices(values, sample_ids), start=1):
        ranks[index] = rank
    return ranks


def top_indices(values, sample_ids, top_k):
    return set(ranked_indices(values, sample_ids)[:top_k])


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
    values = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "p05": float(np.quantile(values, 0.05)),
        "median": float(np.quantile(values, 0.5)),
        "p95": float(np.quantile(values, 0.95)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def validate_frame(frame):
    feature_columns = [
        column for column in frame.columns if column.startswith(FEATURE_PREFIX)
    ]
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        TARGET_COLUMN,
        COLLISION_COLUMN,
    }
    missing = sorted(required - set(frame.columns))
    if len(feature_columns) != 15:
        raise ValueError(f"需要 15 个归一化参数特征，实际为 {len(feature_columns)}")
    if missing:
        raise ValueError(f"数据集缺少字段: {missing}")
    if frame[feature_columns + [TARGET_COLUMN]].isna().any().any():
        raise ValueError("特征或风险目标存在缺失值")
    if frame["sample_id"].duplicated().any():
        raise ValueError("sample_id 必须唯一")
    invalid_levels = sorted(set(frame["target_risk_level"]) - set(RISK_LEVELS))
    if invalid_levels:
        raise ValueError(f"存在未知目标风险档: {invalid_levels}")
    return feature_columns


def prediction_metrics(actual, predicted, sample_ids, target_levels, top_k):
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


def collision_metrics(actual, probability):
    return {
        "average_precision": float(average_precision_score(actual, probability)),
        "roc_auc": float(roc_auc_score(actual, probability)),
    }


def run_oof(frame, feature_columns, args):
    normalized = frame[feature_columns].to_numpy(dtype=float)
    derived = physical_feature_matrix(normalized)
    enhanced = np.column_stack((normalized, derived))
    actual = frame[TARGET_COLUMN].to_numpy(dtype=float)
    collision_label = (frame[COLLISION_COLUMN].to_numpy(dtype=float) > 0).astype(int)
    sample_ids = frame["sample_id"].astype(str).to_numpy()
    target_levels = frame["target_risk_level"].astype(str).to_numpy()
    strata = (
        frame["generator"].astype(str)
        + "__"
        + frame["target_risk_level"].astype(str)
    ).to_numpy()
    if pd.Series(strata).value_counts().min() < 3:
        raise ValueError("每个生成器×目标档至少需要 3 个独立场景")

    feature_sets = {
        "baseline": normalized,
        "physical_enhanced": enhanced,
    }
    predictions = {
        name: np.full((args.repeats, len(frame)), np.nan)
        for name in MODEL_NAMES
    }
    collision_predictions = {
        name: np.full((args.repeats, len(frame)), np.nan)
        for name in MODEL_NAMES
    }
    top_sets = {name: [] for name in MODEL_NAMES}
    metric_rows = []
    collision_rows = []
    prediction_rows = []

    for repeat_index in range(args.repeats):
        split_seed = args.random_state + repeat_index
        splitter = StratifiedKFold(
            n_splits=3,
            shuffle=True,
            random_state=split_seed,
        )
        splits = list(splitter.split(normalized, strata))
        for model_offset, model_name in enumerate(MODEL_NAMES):
            current_predictions = np.full(len(frame), np.nan)
            current_collision = np.full(len(frame), np.nan)
            features = feature_sets[model_name]
            for fold_index, (train_index, test_index) in enumerate(splits):
                seed = (
                    args.random_state
                    + repeat_index * 100
                    + model_offset * 10
                    + fold_index
                )
                regressor = make_regressor(seed, args.n_estimators)
                classifier = make_classifier(seed + 1, args.n_estimators)
                regressor.fit(features[train_index], actual[train_index])
                classifier.fit(features[train_index], collision_label[train_index])
                current_predictions[test_index] = regressor.predict(
                    features[test_index]
                )
                current_collision[test_index] = classifier.predict_proba(
                    features[test_index]
                )[:, 1]
            if np.isnan(current_predictions).any() or np.isnan(current_collision).any():
                raise RuntimeError("OOF 预测存在缺失值")

            predictions[model_name][repeat_index] = current_predictions
            collision_predictions[model_name][repeat_index] = current_collision
            selected_top = top_indices(current_predictions, sample_ids, args.top_k)
            top_sets[model_name].append(selected_top)
            metric_rows.append(
                {
                    "model": model_name,
                    "repeat_index": repeat_index,
                    "split_seed": split_seed,
                    **prediction_metrics(
                        actual,
                        current_predictions,
                        sample_ids,
                        target_levels,
                        args.top_k,
                    ),
                }
            )
            collision_rows.append(
                {
                    "model": model_name,
                    "repeat_index": repeat_index,
                    "split_seed": split_seed,
                    **collision_metrics(collision_label, current_collision),
                }
            )
            ranks = np.empty(len(frame), dtype=float)
            for rank, index in enumerate(
                ranked_indices(current_predictions, sample_ids),
                start=1,
            ):
                ranks[index] = rank
            for sample_index, sample_id in enumerate(sample_ids):
                prediction_rows.append(
                    {
                        "model": model_name,
                        "repeat_index": repeat_index,
                        "sample_id": sample_id,
                        "observed_risk_score": actual[sample_index],
                        "predicted_risk_score": current_predictions[sample_index],
                        "prediction_error": (
                            current_predictions[sample_index] - actual[sample_index]
                        ),
                        "predicted_collision_probability": current_collision[
                            sample_index
                        ],
                        "predicted_rank": ranks[sample_index],
                        "selected_in_top_k": sample_index in selected_top,
                    }
                )

    return {
        "derived": derived,
        "predictions": predictions,
        "collision_predictions": collision_predictions,
        "top_sets": top_sets,
        "metric_frame": pd.DataFrame(metric_rows),
        "collision_frame": pd.DataFrame(collision_rows),
        "prediction_frame": pd.DataFrame(prediction_rows),
        "actual": actual,
        "collision_label": collision_label,
        "sample_ids": sample_ids,
    }


def build_sample_summary(frame, result, top_k):
    actual = result["actual"]
    sample_ids = result["sample_ids"]
    actual_ranks = rank_array(actual, sample_ids)
    rows = []
    for model_name in MODEL_NAMES:
        matrix = result["predictions"][model_name]
        rank_matrix = np.vstack(
            [rank_array(prediction, sample_ids) for prediction in matrix]
        )
        top_frequency = np.zeros(len(frame), dtype=float)
        for selected in result["top_sets"][model_name]:
            for index in selected:
                top_frequency[index] += 1.0
        top_frequency /= len(result["top_sets"][model_name])
        for sample_index, source in frame.iterrows():
            sample_predictions = matrix[:, sample_index]
            rows.append(
                {
                    "model": model_name,
                    "sample_id": source["sample_id"],
                    "collision_status": (
                        "collision"
                        if int(source[COLLISION_COLUMN]) > 0
                        else "no_collision"
                    ),
                    "observed_risk_score": actual[sample_index],
                    "predicted_score_mean": float(np.mean(sample_predictions)),
                    "predicted_score_std": float(
                        np.std(sample_predictions, ddof=1)
                    ),
                    "mean_bias": float(
                        np.mean(sample_predictions - actual[sample_index])
                    ),
                    "mean_absolute_error": float(
                        np.mean(np.abs(sample_predictions - actual[sample_index]))
                    ),
                    "actual_rank": actual_ranks[sample_index],
                    "predicted_rank_std": float(
                        np.std(rank_matrix[:, sample_index], ddof=1)
                    ),
                    "top_k_selection_frequency": float(
                        top_frequency[sample_index]
                    ),
                    "top_k": top_k,
                }
            )
    return pd.DataFrame(rows)


def build_summary(frame, result, args, dataset_path):
    metric_frame = result["metric_frame"]
    collision_frame = result["collision_frame"]
    sample_frame = build_sample_summary(frame, result, args.top_k)
    models = {}
    for model_name in MODEL_NAMES:
        metrics = metric_frame[metric_frame["model"] == model_name]
        samples = sample_frame[sample_frame["model"] == model_name]
        collision_metrics_frame = collision_frame[
            collision_frame["model"] == model_name
        ]
        collision_samples = samples[samples["collision_status"] == "collision"]
        no_collision_samples = samples[
            samples["collision_status"] == "no_collision"
        ]
        models[model_name] = {
            "metrics": {
                key: metric_summary(metrics[key])
                for key in (
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
                "stable_top_k_sample_count": int(
                    np.sum(samples["top_k_selection_frequency"] >= 0.8)
                ),
            },
            "collision_error": {
                "collision_mae": float(
                    collision_samples["mean_absolute_error"].mean()
                ),
                "collision_mean_bias": float(
                    collision_samples["mean_bias"].mean()
                ),
                "no_collision_mae": float(
                    no_collision_samples["mean_absolute_error"].mean()
                ),
                "no_collision_mean_bias": float(
                    no_collision_samples["mean_bias"].mean()
                ),
            },
            "collision_classifier": {
                key: metric_summary(collision_metrics_frame[key])
                for key in ("average_precision", "roc_auc")
            },
        }

    return sample_frame, {
        "format": "physical_feature_enhancement_v1",
        "feature_version": PHYSICAL_FEATURE_VERSION,
        "dataset": dataset_path,
        "dataset_sha256": file_sha256(dataset_path),
        "independent_scenario_count": int(len(frame)),
        "collision_scenario_count": int(
            np.sum(frame[COLLISION_COLUMN].to_numpy(dtype=float) > 0)
        ),
        "baseline_feature_count": 15,
        "derived_feature_count": len(physical_feature_names()),
        "derived_feature_names": list(physical_feature_names()),
        "repeated_stratified_oof": {
            "repeats": args.repeats,
            "folds": 3,
            "strata": "generator__target_risk_level",
            "random_state": args.random_state,
        },
        "top_k": args.top_k,
        "models": models,
        "interpretation_boundary": (
            f"{len(frame)} 个独立场景只支持工程特征增强诊断；"
            "所有派生特征均由生成前可知的场景参数计算，不等同于实测车辆状态。"
        ),
    }


def build_report(summary):
    baseline = summary["models"]["baseline"]
    enhanced = summary["models"]["physical_enhanced"]
    lines = [
        "# 物理交互派生特征增强 V1",
        "",
        "## 方法",
        "",
        f"- 数据：`{summary['independent_scenario_count']}` 个独立场景，碰撞场景 `{summary['collision_scenario_count']}` 个。",
        f"- 基线：原始 15 维归一化参数；增强：原始 15 维 + `{summary['derived_feature_count']}` 个物理交互特征。",
        "- 特征只使用场景生成前可知的参数，不使用 CARLA 遥测、碰撞结果或实测风险。",
        f"- 验证：`{summary['repeated_stratified_oof']['repeats']}` 次重复分层三折 OOF，按 `generator × target_risk_level` 分层。",
        "",
        "## 结果",
        "",
        f"- MAE：基线 `{baseline['metrics']['mae']['mean']:.3f}`，增强 `{enhanced['metrics']['mae']['mean']:.3f}`。",
        f"- Spearman：基线 `{baseline['metrics']['spearman']['mean']:.3f}`，增强 `{enhanced['metrics']['spearman']['mean']:.3f}`。",
        f"- Top-9 Jaccard：基线 `{baseline['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`，增强 `{enhanced['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`。",
        f"- 碰撞场景 MAE：基线 `{baseline['collision_error']['collision_mae']:.3f}`，增强 `{enhanced['collision_error']['collision_mae']:.3f}`。",
        f"- 碰撞分类 AP：基线 `{baseline['collision_classifier']['average_precision']['mean']:.3f}`，增强 `{enhanced['collision_classifier']['average_precision']['mean']:.3f}`。",
        f"- 碰撞分类 ROC-AUC：基线 `{baseline['collision_classifier']['roc_auc']['mean']:.3f}`，增强 `{enhanced['collision_classifier']['roc_auc']['mean']:.3f}`。",
        "",
        "## 决策边界",
        "",
        "只有当增强特征同时改善总体误差、碰撞子集误差或 Top-K 稳定性，才进入候选重评分；否则保留为分析特征，不追加 CARLA 批次。",
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
    feature_columns = validate_frame(frame)
    result = run_oof(frame, feature_columns, args)
    sample_frame, summary = build_summary(frame, result, args, dataset_path)
    result["metric_frame"].to_csv(
        output_dir / "repeat_metrics.csv", index=False, encoding="utf-8-sig"
    )
    result["collision_frame"].to_csv(
        output_dir / "collision_metrics.csv", index=False, encoding="utf-8-sig"
    )
    result["prediction_frame"].to_csv(
        output_dir / "repeat_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )
    sample_frame.to_csv(
        output_dir / "sample_summary.csv", index=False, encoding="utf-8-sig"
    )
    write_json(output_dir / "physical_feature_summary.json", summary)
    (output_dir / "physical_feature_report.md").write_text(
        build_report(summary), encoding="utf-8"
    )
    baseline = summary["models"]["baseline"]["metrics"]
    enhanced = summary["models"]["physical_enhanced"]["metrics"]
    print(
        f"[PHYSICAL] samples={len(frame)} | "
        f"baseline_mae={baseline['mae']['mean']:.3f} | "
        f"enhanced_mae={enhanced['mae']['mean']:.3f}"
    )
    print(f"[PHYSICAL] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
