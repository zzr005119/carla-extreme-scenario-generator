"""诊断风险代理误差与候选排序稳定性。"""

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
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DATASET = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
    "dataset.csv",
)
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
    "diagnostics_v1",
)
FEATURE_PREFIX = "feature_"
TARGET_COLUMN = "observed_risk_score_mean"
RISK_LEVELS = ("low", "medium", "high", "critical")
MODEL_NAMES = ("random_forest", "ridge")


def parse_args():
    parser = argparse.ArgumentParser(description="风险代理误差与排序稳定性诊断")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--random-state", type=int, default=20260815)
    return parser.parse_args()


def make_model(model_name, random_state, n_estimators):
    if model_name == "random_forest":
        return RandomForestRegressor(
            n_estimators=n_estimators,
            min_samples_leaf=2,
            max_features=0.7,
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == "ridge":
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        )
    raise ValueError(f"未知模型: {model_name}")


def spearman_score(actual, predicted):
    result = spearmanr(actual, predicted)
    value = getattr(result, "statistic", result[0])
    return None if np.isnan(value) else float(value)


def ranked_indices(values, sample_ids):
    return sorted(
        range(len(values)),
        key=lambda index: (-float(values[index]), str(sample_ids[index])),
    )


def rank_values(values, sample_ids):
    order = ranked_indices(values, sample_ids)
    ranks = np.empty(len(values), dtype=float)
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank
    return ranks


def top_indices(values, sample_ids, top_k):
    return set(ranked_indices(values, sample_ids)[:top_k])


def jaccard(left, right):
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def pairwise_jaccard(sets):
    values = []
    for left_index in range(len(sets)):
        for right_index in range(left_index + 1, len(sets)):
            values.append(jaccard(sets[left_index], sets[right_index]))
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


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prediction_metrics(actual, predicted, top_k, sample_ids, target_levels):
    actual_high = actual >= 50.0
    predicted_high = predicted >= 50.0
    observed_top = top_indices(actual, sample_ids, top_k)
    predicted_top = top_indices(predicted, sample_ids, top_k)
    target_means = pd.Series(predicted).groupby(target_levels).mean().reindex(
        RISK_LEVELS
    )
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r2": float(r2_score(actual, predicted)),
        "spearman": spearman_score(actual, predicted),
        "mean_bias": float(np.mean(predicted - actual)),
        "high_or_critical_recall": float(
            np.sum(predicted_high & actual_high) / max(1, np.sum(actual_high))
        ),
        "high_or_critical_precision": float(
            np.sum(predicted_high & actual_high) / max(1, np.sum(predicted_high))
        ),
        "top_k_observed_recall": float(
            len(observed_top & predicted_top) / max(1, top_k)
        ),
        "target_mean_ordering_strict": bool(
            target_means.notna().all()
            and all(
                left < right
                for left, right in zip(target_means, target_means.iloc[1:])
            )
        ),
    }


def validate_frame(frame):
    feature_columns = [
        column for column in frame.columns if column.startswith(FEATURE_PREFIX)
    ]
    if len(feature_columns) != 15:
        raise ValueError(f"需要 15 个归一化参数特征，实际为 {len(feature_columns)}")
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        TARGET_COLUMN,
        "observed_risk_score_std",
        "collision_event_total",
        "collision_run_rate",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"数据集缺少字段: {missing}")
    if frame[feature_columns + [TARGET_COLUMN]].isna().any().any():
        raise ValueError("模型输入或目标列存在缺失值")
    if frame["observed_risk_score_std"].isna().any():
        raise ValueError("仿真重复测量标准差存在缺失值")
    invalid_levels = sorted(set(frame["target_risk_level"]) - set(RISK_LEVELS))
    if invalid_levels:
        raise ValueError(f"存在未知目标风险档: {invalid_levels}")
    if frame["sample_id"].duplicated().any():
        raise ValueError("sample_id 必须对应独立场景且不可重复")
    return feature_columns


def repeated_oof_predictions(
    frame,
    feature_columns,
    repeats,
    random_state,
    n_estimators,
    top_k,
):
    features = frame[feature_columns].to_numpy(dtype=float)
    actual = frame[TARGET_COLUMN].to_numpy(dtype=float)
    sample_ids = frame["sample_id"].astype(str).to_numpy()
    target_levels = frame["target_risk_level"].astype(str)
    strata = (
        frame["generator"].astype(str)
        + "__"
        + frame["target_risk_level"].astype(str)
    ).to_numpy()
    counts = pd.Series(strata).value_counts()
    if counts.min() < 3:
        raise ValueError("每个生成器×目标档至少需要 3 个独立场景")

    prediction_rows = []
    metric_rows = []
    prediction_matrices = {
        model_name: np.full((repeats, len(frame)), np.nan, dtype=float)
        for model_name in MODEL_NAMES
    }
    top_sets = {model_name: [] for model_name in MODEL_NAMES}

    for repeat_index in range(repeats):
        split_seed = random_state + repeat_index
        splitter = StratifiedKFold(
            n_splits=3,
            shuffle=True,
            random_state=split_seed,
        )
        splits = list(splitter.split(features, strata))
        for model_offset, model_name in enumerate(MODEL_NAMES):
            predictions = np.full(len(frame), np.nan, dtype=float)
            for fold_index, (train_index, test_index) in enumerate(splits):
                model_seed = (
                    random_state
                    + repeat_index * 100
                    + model_offset * 10
                    + fold_index
                )
                model = make_model(model_name, model_seed, n_estimators)
                model.fit(features[train_index], actual[train_index])
                predictions[test_index] = model.predict(features[test_index])
            if np.isnan(predictions).any():
                raise RuntimeError("重复交叉验证产生了缺失预测")

            prediction_matrices[model_name][repeat_index] = predictions
            ranks = rank_values(predictions, sample_ids)
            selected_top = top_indices(predictions, sample_ids, top_k)
            top_sets[model_name].append(selected_top)
            metrics = prediction_metrics(
                actual,
                predictions,
                top_k,
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
            for sample_index, row in frame.iterrows():
                prediction = float(predictions[sample_index])
                prediction_rows.append(
                    {
                        "model": model_name,
                        "repeat_index": repeat_index,
                        "split_seed": split_seed,
                        "sample_id": row["sample_id"],
                        "generator": row["generator"],
                        "target_risk_level": row["target_risk_level"],
                        "observed_risk_score": float(row[TARGET_COLUMN]),
                        "predicted_risk_score": prediction,
                        "prediction_error": prediction
                        - float(row[TARGET_COLUMN]),
                        "absolute_error": abs(
                            prediction - float(row[TARGET_COLUMN])
                        ),
                        "predicted_rank": float(ranks[sample_index]),
                        "selected_in_top_k": sample_index in selected_top,
                    }
                )
    return prediction_rows, metric_rows, prediction_matrices, top_sets


def build_sample_diagnostics(frame, prediction_matrices, top_sets, top_k):
    sample_ids = frame["sample_id"].astype(str).to_numpy()
    actual = frame[TARGET_COLUMN].to_numpy(dtype=float)
    actual_ranks = rank_values(actual, sample_ids)
    rows = []
    for model_name in MODEL_NAMES:
        matrix = prediction_matrices[model_name]
        rank_matrix = np.vstack(
            [rank_values(predictions, sample_ids) for predictions in matrix]
        )
        top_frequency = np.zeros(len(frame), dtype=float)
        for selected_top in top_sets[model_name]:
            for index in selected_top:
                top_frequency[index] += 1.0
        top_frequency /= len(top_sets[model_name])
        for sample_index, source in frame.iterrows():
            predictions = matrix[:, sample_index]
            errors = predictions - actual[sample_index]
            rows.append(
                {
                    "model": model_name,
                    "sample_id": source["sample_id"],
                    "generator": source["generator"],
                    "target_risk_level": source["target_risk_level"],
                    "observed_risk_score": actual[sample_index],
                    "simulation_score_std": float(
                        source["observed_risk_score_std"]
                    ),
                    "collision_status": (
                        "collision"
                        if int(source["collision_event_total"]) > 0
                        else "no_collision"
                    ),
                    "collision_event_total": int(source["collision_event_total"]),
                    "collision_run_rate": float(source["collision_run_rate"]),
                    "predicted_score_mean": float(np.mean(predictions)),
                    "predicted_score_std": float(
                        np.std(predictions, ddof=1)
                    ),
                    "predicted_score_p05": float(np.quantile(predictions, 0.05)),
                    "predicted_score_p95": float(np.quantile(predictions, 0.95)),
                    "mean_error": float(np.mean(errors)),
                    "mean_absolute_error": float(np.mean(np.abs(errors))),
                    "actual_rank": float(actual_ranks[sample_index]),
                    "predicted_rank_mean": float(
                        np.mean(rank_matrix[:, sample_index])
                    ),
                    "predicted_rank_std": float(
                        np.std(rank_matrix[:, sample_index], ddof=1)
                    ),
                    "predicted_rank_min": float(
                        np.min(rank_matrix[:, sample_index])
                    ),
                    "predicted_rank_max": float(
                        np.max(rank_matrix[:, sample_index])
                    ),
                    "top_k": top_k,
                    "top_k_selection_frequency": float(
                        top_frequency[sample_index]
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_group_summary(sample_frame):
    rows = []
    grouping_sets = [
        ("generator",),
        ("target_risk_level",),
        ("collision_status",),
        ("generator", "target_risk_level"),
    ]
    for model_name in MODEL_NAMES:
        model_frame = sample_frame[sample_frame["model"] == model_name]
        for grouping in grouping_sets:
            grouped = model_frame.groupby(list(grouping), sort=True)
            for keys, group in grouped:
                if not isinstance(keys, tuple):
                    keys = (keys,)
                row = {
                    "model": model_name,
                    "grouping": "__".join(grouping),
                    "generator": "all",
                    "target_risk_level": "all",
                    "collision_status": "all",
                    "sample_count": int(len(group)),
                    "observed_score_mean": float(
                        group["observed_risk_score"].mean()
                    ),
                    "predicted_score_mean": float(
                        group["predicted_score_mean"].mean()
                    ),
                    "mean_bias": float(group["mean_error"].mean()),
                    "mae": float(group["mean_absolute_error"].mean()),
                    "rmse_of_mean_prediction": float(
                        math.sqrt(np.mean(group["mean_error"] ** 2))
                    ),
                    "mean_prediction_std": float(
                        group["predicted_score_std"].mean()
                    ),
                    "mean_rank_std": float(group["predicted_rank_std"].mean()),
                    "mean_top_k_frequency": float(
                        group["top_k_selection_frequency"].mean()
                    ),
                }
                for column, key in zip(grouping, keys):
                    row[column] = key
                rows.append(row)
    return pd.DataFrame(rows)


def build_model_agreement(prediction_matrices, sample_ids, top_k):
    rows = []
    for repeat_index in range(prediction_matrices[MODEL_NAMES[0]].shape[0]):
        left = prediction_matrices[MODEL_NAMES[0]][repeat_index]
        right = prediction_matrices[MODEL_NAMES[1]][repeat_index]
        rows.append(
            {
                "repeat_index": repeat_index,
                "prediction_spearman": spearman_score(left, right),
                "top_k_jaccard": jaccard(
                    top_indices(left, sample_ids, top_k),
                    top_indices(right, sample_ids, top_k),
                ),
            }
        )
    return pd.DataFrame(rows)


def build_summary(
    frame,
    dataset_path,
    dataset_sha256,
    feature_columns,
    metric_frame,
    sample_frame,
    agreement_frame,
    top_sets,
    repeats,
    top_k,
    random_state,
    n_estimators,
):
    models = {}
    for model_name in MODEL_NAMES:
        current_metrics = metric_frame[metric_frame["model"] == model_name]
        current_samples = sample_frame[sample_frame["model"] == model_name]
        jaccards = pairwise_jaccard(top_sets[model_name])
        collision_error = {}
        for collision_status, group in current_samples.groupby(
            "collision_status", sort=True
        ):
            collision_error[collision_status] = {
                "sample_count": int(len(group)),
                "observed_score_mean": float(group["observed_risk_score"].mean()),
                "predicted_score_mean": float(group["predicted_score_mean"].mean()),
                "mean_bias": float(group["mean_error"].mean()),
                "mae": float(group["mean_absolute_error"].mean()),
            }
        models[model_name] = {
            "metrics": {
                column: metric_summary(current_metrics[column])
                for column in (
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
                current_metrics["target_mean_ordering_strict"].mean()
            ),
            "ranking_stability": {
                "pairwise_top_k_jaccard": metric_summary(jaccards),
                "mean_sample_rank_std": float(
                    current_samples["predicted_rank_std"].mean()
                ),
                "maximum_sample_rank_std": float(
                    current_samples["predicted_rank_std"].max()
                ),
                "stable_top_k_sample_count": int(
                    np.sum(current_samples["top_k_selection_frequency"] >= 0.8)
                ),
                "never_top_k_sample_count": int(
                    np.sum(current_samples["top_k_selection_frequency"] == 0.0)
                ),
            },
            "collision_error": collision_error,
        }
    return {
        "format": "risk_proxy_diagnostics_v1",
        "dataset": dataset_path,
        "dataset_sha256": dataset_sha256,
        "independent_scenario_count": int(len(frame)),
        "feature_columns": feature_columns,
        "analysis_unit": "independent_scenario",
        "repeated_measurements_are_preaggregated": True,
        "repeated_stratified_oof": {
            "repeats": repeats,
            "folds": 3,
            "strata": "generator__target_risk_level",
            "random_state": random_state,
        },
        "random_forest_n_estimators": n_estimators,
        "top_k": top_k,
        "models": models,
        "model_agreement": {
            "prediction_spearman": metric_summary(
                agreement_frame["prediction_spearman"]
            ),
            "top_k_jaccard": metric_summary(agreement_frame["top_k_jaccard"]),
        },
        "interpretation_boundary": (
            "36 个独立场景只支持工程误差诊断和候选排序稳定性评估，"
            "不支持统计显著性结论；Traffic Manager 种子已先聚合为场景级重复测量。"
        ),
    }


def build_report(summary, group_frame, sample_frame):
    random_forest = summary["models"]["random_forest"]
    ridge = summary["models"]["ridge"]
    rf_groups = group_frame[
        (group_frame["model"] == "random_forest")
        & (group_frame["grouping"] == "generator__target_risk_level")
    ].sort_values("mae", ascending=False)
    rf_samples = sample_frame[sample_frame["model"] == "random_forest"].sort_values(
        "mean_absolute_error", ascending=False
    )
    unstable_samples = sample_frame[
        sample_frame["model"] == "random_forest"
    ].sort_values("predicted_rank_std", ascending=False)
    worst_group = rf_groups.iloc[0]
    worst_sample = rf_samples.iloc[0]
    unstable_sample = unstable_samples.iloc[0]
    rf_metrics = random_forest["metrics"]
    collision_error = random_forest["collision_error"]
    lines = [
        "# 风险代理误差与排序稳定性诊断 V1",
        "",
        "## 方法",
        "",
        f"- 独立场景：`{summary['independent_scenario_count']}` 个；Traffic Manager 种子已先聚合为场景级重复测量。",
        f"- 重复分层三折 OOF：`{summary['repeated_stratified_oof']['repeats']}` 次，按 `generator × target_risk_level` 分层。",
        "- 对照模型：随机森林与 Ridge；目标档和生成器均不作为模型输入。",
        f"- 候选排序稳定性：按预测风险取 Top-`{summary['top_k']}`，统计重合率、样本排名波动和模型间一致性。",
        "",
        "## 主要结果",
        "",
        f"- 随机森林重复 OOF MAE：`{rf_metrics['mae']['mean']:.3f} ± {rf_metrics['mae']['std']:.3f}`，RMSE：`{rf_metrics['rmse']['mean']:.3f} ± {rf_metrics['rmse']['std']:.3f}`。",
        f"- 随机森林 Spearman：均值 `{rf_metrics['spearman']['mean']:.3f}`，5%—95% 区间 `{rf_metrics['spearman']['p05']:.3f}—{rf_metrics['spearman']['p95']:.3f}`。",
        f"- 随机森林 Top-{summary['top_k']} 两两 Jaccard：均值 `{random_forest['ranking_stability']['pairwise_top_k_jaccard']['mean']:.3f}`；稳定入选率至少 80% 的样本有 `{random_forest['ranking_stability']['stable_top_k_sample_count']}` 个。",
        f"- 随机森林目标档均值严格递增比例：`{random_forest['target_mean_ordering_strict_rate']:.1%}`；Ridge 为 `{ridge['target_mean_ordering_strict_rate']:.1%}`。",
        f"- 两模型预测排序 Spearman 均值：`{summary['model_agreement']['prediction_spearman']['mean']:.3f}`；Top-{summary['top_k']} Jaccard 均值：`{summary['model_agreement']['top_k_jaccard']['mean']:.3f}`。",
        f"- 随机森林在 `{collision_error['collision']['sample_count']}` 个碰撞场景上的 MAE 为 `{collision_error['collision']['mae']:.3f}`、平均偏差 `{collision_error['collision']['mean_bias']:.3f}`；其余 `{collision_error['no_collision']['sample_count']}` 个非碰撞场景 MAE 为 `{collision_error['no_collision']['mae']:.3f}`。",
        f"- 随机森林误差最大的分组：`{worst_group['generator']} × {worst_group['target_risk_level']}`，MAE `{worst_group['mae']:.3f}`，平均偏差 `{worst_group['mean_bias']:.3f}`。",
        f"- 随机森林误差最大的场景：`{worst_sample['sample_id']}`，实测 `{worst_sample['observed_risk_score']:.3f}`，重复 OOF 预测均值 `{worst_sample['predicted_score_mean']:.3f}`，平均绝对误差 `{worst_sample['mean_absolute_error']:.3f}`。",
        f"- 排名最不稳定场景：`{unstable_sample['sample_id']}`，排名标准差 `{unstable_sample['predicted_rank_std']:.3f}`，Top-{summary['top_k']} 入选频率 `{unstable_sample['top_k_selection_frequency']:.1%}`。",
        "",
        "## 工程结论",
        "",
        "- 随机森林仍可作为候选预排序器，但单次三折结果不足以代表稳定性能；后续候选应同时保存预测均值、重复预测标准差和 Top-K 入选频率。",
        "- 当前主要误差来自碰撞带来的风险分数离散跃迁；在碰撞样本增加前，不训练独立碰撞分类器，而是把碰撞边界作为主动补样通道，与连续风险分数排序分开管理。",
        "- 优先实测预测分高且排名稳定的候选，同时保留少量高不确定性候选用于主动补样，不能只按单个模型的一次预测分数排序。",
        "- 分组系统偏差和最差样本应作为下一轮外部验证的定向补样依据；本轮不修改实测标签，也不通过弱化控制器提高风险命中率。",
        "",
        "## 解释边界",
        "",
        summary["interpretation_boundary"],
        "",
        "## 输出",
        "",
        "- `repeat_metrics.csv`：每次重复 OOF 的模型指标。",
        "- `repeat_predictions.csv`：每次重复、每个场景的预测、误差、排名和 Top-K 状态。",
        "- `sample_ranking_stability.csv`：样本级预测区间、误差和排名稳定性。",
        "- `group_error_summary.csv`：按生成器、目标档及其交叉分组的误差。",
        "- `model_agreement.csv`：随机森林与 Ridge 的排序和 Top-K 一致性。",
        "- `diagnostic_summary.json`：机器可读汇总。",
    ]
    return "\n".join(lines) + "\n"


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


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
    top_k = args.top_k or max(3, math.ceil(len(frame) * 0.25))
    if not 1 <= top_k < len(frame):
        raise ValueError("--top-k 必须位于 1 和场景数减 1 之间")

    prediction_rows, metric_rows, prediction_matrices, top_sets = (
        repeated_oof_predictions(
            frame=frame,
            feature_columns=feature_columns,
            repeats=args.repeats,
            random_state=args.random_state,
            n_estimators=args.n_estimators,
            top_k=top_k,
        )
    )
    prediction_frame = pd.DataFrame(prediction_rows)
    metric_frame = pd.DataFrame(metric_rows)
    sample_frame = build_sample_diagnostics(
        frame,
        prediction_matrices,
        top_sets,
        top_k,
    )
    group_frame = build_group_summary(sample_frame)
    agreement_frame = build_model_agreement(
        prediction_matrices,
        frame["sample_id"].astype(str).to_numpy(),
        top_k,
    )
    summary = build_summary(
        frame=frame,
        dataset_path=dataset_path,
        dataset_sha256=file_sha256(dataset_path),
        feature_columns=feature_columns,
        metric_frame=metric_frame,
        sample_frame=sample_frame,
        agreement_frame=agreement_frame,
        top_sets=top_sets,
        repeats=args.repeats,
        top_k=top_k,
        random_state=args.random_state,
        n_estimators=args.n_estimators,
    )

    metric_frame.to_csv(
        output_dir / "repeat_metrics.csv", index=False, encoding="utf-8-sig"
    )
    prediction_frame.to_csv(
        output_dir / "repeat_predictions.csv", index=False, encoding="utf-8-sig"
    )
    sample_frame.to_csv(
        output_dir / "sample_ranking_stability.csv",
        index=False,
        encoding="utf-8-sig",
    )
    group_frame.to_csv(
        output_dir / "group_error_summary.csv", index=False, encoding="utf-8-sig"
    )
    agreement_frame.to_csv(
        output_dir / "model_agreement.csv", index=False, encoding="utf-8-sig"
    )
    write_json(output_dir / "diagnostic_summary.json", summary)
    (output_dir / "risk_proxy_diagnostic_report.md").write_text(
        build_report(summary, group_frame, sample_frame),
        encoding="utf-8",
    )

    rf_metrics = summary["models"]["random_forest"]["metrics"]
    rf_stability = summary["models"]["random_forest"]["ranking_stability"]
    print(
        f"[DIAGNOSTIC] samples={len(frame)} | repeats={args.repeats} | "
        f"top_k={top_k}"
    )
    print(
        f"[DIAGNOSTIC] rf_mae={rf_metrics['mae']['mean']:.3f} | "
        f"rf_spearman={rf_metrics['spearman']['mean']:.3f} | "
        f"top_k_jaccard={rf_stability['pairwise_top_k_jaccard']['mean']:.3f}"
    )
    print(f"[DIAGNOSTIC] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
