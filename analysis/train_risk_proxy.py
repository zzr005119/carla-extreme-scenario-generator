"""训练并评估轻量 CARLA 实测风险代理基线。"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.physical_features import (  # noqa: E402
    PHYSICAL_FEATURE_VERSION,
    physical_feature_matrix,
    physical_feature_names,
)


DEFAULT_DATASET = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
    "dataset.csv",
)
DEFAULT_OUTPUT_DIR = os.path.dirname(DEFAULT_DATASET)
DEFAULT_ARTIFACT_DIR = os.path.join(PROJECT_ROOT, "artifacts", "risk_proxy_v1")
FEATURE_PREFIX = "feature_"
TARGET_COLUMN = "observed_risk_score_mean"


def parse_args():
    parser = argparse.ArgumentParser(description="训练风险代理基线")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--version-label", default="V1")
    parser.add_argument("--random-state", type=int, default=20260815)
    parser.add_argument(
        "--feature-space",
        choices=("baseline", "physical_enhanced"),
        default="baseline",
    )
    return parser.parse_args()


def version_slug(version_label):
    value = re.sub(r"[^a-zA-Z0-9]+", "_", version_label.strip()).strip("_")
    if not value:
        raise ValueError("--version-label 不能为空")
    return value.lower()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def spearman_score(actual, predicted):
    result = spearmanr(actual, predicted)
    value = getattr(result, "statistic", result[0])
    return None if np.isnan(value) else float(value)


def make_models(random_state):
    return {
        "dummy_mean": DummyRegressor(strategy="mean"),
        "ridge": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=300,
            min_samples_leaf=2,
            max_features=0.7,
            random_state=random_state,
            n_jobs=-1,
        ),
    }


def evaluate_predictions(actual, predicted):
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r2": float(r2_score(actual, predicted)),
        "spearman": spearman_score(actual, predicted),
        "high_or_critical_recall": float(
            np.sum((predicted >= 50.0) & (actual >= 50.0))
            / max(1, np.sum(actual >= 50.0))
        ),
    }


def build_target_summary(frame, prediction_column):
    grouped = (
        frame.groupby(["generator", "target_risk_level"], as_index=False)
        .agg(
            independent_scenario_count=(TARGET_COLUMN, "size"),
            observed_score_mean=(TARGET_COLUMN, "mean"),
            predicted_score_mean=(prediction_column, "mean"),
            observed_score_std=(TARGET_COLUMN, "std"),
        )
        .fillna(0.0)
    )
    return grouped


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    label = args.version_label.strip()
    label_slug = version_slug(label)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(os.path.abspath(args.dataset))
    feature_columns = [column for column in frame if column.startswith(FEATURE_PREFIX)]
    if len(feature_columns) != 15:
        raise ValueError(f"需要 15 个归一化参数特征，实际为 {len(feature_columns)}")
    if TARGET_COLUMN not in frame:
        raise ValueError(f"数据集缺少目标列: {TARGET_COLUMN}")
    if frame[TARGET_COLUMN].isna().any():
        raise ValueError("风险代理目标列存在缺失值")
    if frame[feature_columns].isna().any().any():
        raise ValueError("模型输入特征存在缺失值")

    features = frame[feature_columns].to_numpy(dtype=float)
    model_feature_names = list(feature_columns)
    derived_feature_count = 0
    if args.feature_space == "physical_enhanced":
        derived = physical_feature_matrix(features)
        features = np.column_stack((features, derived))
        derived_names = list(physical_feature_names())
        model_feature_names.extend(derived_names)
        derived_feature_count = len(derived_names)
    target = frame[TARGET_COLUMN].to_numpy(dtype=float)
    strata = (
        frame["generator"].astype(str)
        + "__"
        + frame["target_risk_level"].astype(str)
    ).to_numpy()
    stratum_counts = pd.Series(strata).value_counts()
    if stratum_counts.min() < 3:
        raise ValueError("每个生成器×目标档至少需要 3 个独立场景")

    splitter = StratifiedKFold(
        n_splits=3,
        shuffle=True,
        random_state=args.random_state,
    )
    model_predictions = {}
    metrics = []
    for model_name, model in make_models(args.random_state).items():
        predictions = np.full(len(frame), np.nan, dtype=float)
        for train_index, test_index in splitter.split(features, strata):
            model.fit(features[train_index], target[train_index])
            predictions[test_index] = model.predict(features[test_index])
        model_predictions[model_name] = predictions
        row = {"model": model_name}
        row.update(evaluate_predictions(target, predictions))
        metrics.append(row)

    metrics.sort(key=lambda row: (row["mae"], row["rmse"]))
    selected_model_name = metrics[0]["model"]
    selected_predictions = model_predictions[selected_model_name]
    frame["oof_predicted_risk_score"] = selected_predictions
    frame["oof_absolute_error"] = np.abs(
        frame[TARGET_COLUMN] - frame["oof_predicted_risk_score"]
    )
    frame.to_csv(output_dir / "oof_predictions.csv", index=False, encoding="utf-8-sig")
    write_csv(output_dir / "model_comparison.csv", metrics)
    build_target_summary(frame, "oof_predicted_risk_score").to_csv(
        output_dir / "target_summary.csv", index=False, encoding="utf-8-sig"
    )

    final_model = make_models(args.random_state)[selected_model_name]
    final_model.fit(features, target)
    artifact_dir = Path(os.path.abspath(args.artifact_dir))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, artifact_dir / "selected_model.joblib")

    if selected_model_name == "ridge":
        coefficients = final_model.named_steps["model"].coef_
        importance = np.abs(coefficients)
        importance_type = "absolute_standardized_ridge_coefficient"
    elif selected_model_name == "random_forest":
        importance = final_model.feature_importances_
        importance_type = "random_forest_feature_importance"
    else:
        importance = np.zeros(len(model_feature_names))
        importance_type = "not_applicable"
    importance_rows = [
        {
            "feature": feature,
            "importance": float(value),
            "importance_type": importance_type,
        }
        for feature, value in sorted(
            zip(model_feature_names, importance),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    write_csv(output_dir / "feature_importance.csv", importance_rows)

    target_means = (
        frame.groupby("target_risk_level")["oof_predicted_risk_score"]
        .mean()
        .reindex(["low", "medium", "high", "critical"])
    )
    observed_means = (
        frame.groupby("target_risk_level")[TARGET_COLUMN]
        .mean()
        .reindex(["low", "medium", "high", "critical"])
    )
    summary = {
        "format": f"risk_proxy_{args.feature_space}_{label_slug}",
        "version_label": label,
        "feature_space": args.feature_space,
        "physical_feature_version": (
            PHYSICAL_FEATURE_VERSION
            if args.feature_space == "physical_enhanced"
            else None
        ),
        "dataset": os.path.abspath(args.dataset),
        "independent_scenario_count": len(frame),
        "feature_count": len(model_feature_names),
        "baseline_feature_count": len(feature_columns),
        "derived_feature_count": derived_feature_count,
        "target_column": TARGET_COLUMN,
        "target_risk_level_used_as_input": False,
        "generator_used_as_input": False,
        "cv": {
            "method": "StratifiedKFold",
            "n_splits": 3,
            "strata": "generator__target_risk_level",
            "random_state": args.random_state,
        },
        "selected_model": selected_model_name,
        "selected_model_metrics": metrics[0],
        "all_model_metrics": metrics,
        "observed_score_mean_by_target": {
            key: float(value) for key, value in observed_means.dropna().items()
        },
        "oof_predicted_score_mean_by_target": {
            key: float(value) for key, value in target_means.dropna().items()
        },
        "target_ordering_is_strict_for_observed_mean": bool(
            observed_means.dropna().is_monotonic_increasing
        ),
        "target_ordering_is_strict_for_oof_prediction_mean": bool(
            target_means.dropna().is_monotonic_increasing
        ),
        "artifact": str(artifact_dir / "selected_model.joblib"),
    }
    write_json(output_dir / "proxy_summary.json", summary)
    report_lines = [
        f"# 风险代理基线 {label}",
        "",
        f"- 独立场景：`{len(frame)}` 个。",
        "- 重复测量：每个场景的 3 个 Traffic Manager 种子先聚合为场景均值。",
        (
            "- 输入：15 维归一化场景参数；`target_risk_level` 和 `generator` 不作为模型输入。"
            if args.feature_space == "baseline"
            else f"- 输入：15 维归一化场景参数 + {derived_feature_count} 个生成前物理交互派生特征；`target_risk_level` 和 `generator` 不作为模型输入。"
        ),
        "- 目标：场景级 `observed_risk_score_mean`。",
        "- 交叉验证：按 `generator × target_risk_level` 分层的 3 折交叉验证。",
        f"- 当前选择模型：`{selected_model_name}`。",
        f"- MAE：`{metrics[0]['mae']:.3f}`；RMSE：`{metrics[0]['rmse']:.3f}`；"
        f"Spearman：`{metrics[0]['spearman']}`。",
        "",
        "## 解释边界",
        "",
        f"该基线用于对候选场景进行风险排序，不替代 CARLA 实测，也不证明生成器已经学会真实交通风险分布。当前独立场景为 {len(frame)} 个，本结果只作工程基线和误差诊断，不作统计显著性结论。",
        "",
        "## 输出文件",
        "",
        f"- `dataset.csv`：{len(frame)} 个独立场景的聚合特征和风险标签。",
        "- `oof_predictions.csv`：交叉验证折外预测。",
        "- `model_comparison.csv`：均值基线、Ridge 和随机森林对照。",
        "- `target_summary.csv`：按生成器和目标档的实测/预测汇总。",
        "- `feature_importance.csv`：选中模型的特征重要性。",
        "- `proxy_summary.json`：机器可读汇总。",
    ]
    (output_dir / "risk_proxy_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    print(
        f"[PROXY] samples={len(frame)} | selected={selected_model_name} | "
        f"MAE={metrics[0]['mae']:.3f} | RMSE={metrics[0]['rmse']:.3f}"
    )
    print(f"[PROXY] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
