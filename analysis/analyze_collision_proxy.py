"""评估独立碰撞倾向代理的重复 OOF 可行性。"""

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    PROJECT_ROOT / "data" / "scenarios" / "risk_feedback_v2" / "dataset.csv"
)
FEATURE_PREFIX = "feature_"
TARGET_COLUMN = "collision_event_total"
MODEL_NAMES = ("random_forest", "logistic_regression")


def parse_args():
    parser = argparse.ArgumentParser(description="碰撞倾向代理重复 OOF 诊断")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--random-state", type=int, default=20260815)
    return parser.parse_args()


def make_model(model_name, random_state, n_estimators):
    if model_name == "random_forest":
        return RandomForestClassifier(
            n_estimators=n_estimators,
            min_samples_leaf=2,
            max_features=0.7,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == "logistic_regression":
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=1.0,
                        class_weight="balanced",
                        max_iter=2000,
                    ),
                ),
            ]
        )
    raise ValueError(f"未知模型: {model_name}")


def metric_summary(values):
    values = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)),
        "p05": float(np.quantile(values, 0.05)),
        "p95": float(np.quantile(values, 0.95)),
    }


def evaluate(actual, probability):
    predicted = probability >= 0.5
    return {
        "roc_auc": float(roc_auc_score(actual, probability)),
        "average_precision": float(average_precision_score(actual, probability)),
        "brier": float(brier_score_loss(actual, probability)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
    }


def validate_frame(frame):
    feature_columns = [
        column for column in frame.columns if column.startswith(FEATURE_PREFIX)
    ]
    if len(feature_columns) != 15:
        raise ValueError(f"需要 15 个输入特征，实际为 {len(feature_columns)}")
    if TARGET_COLUMN not in frame:
        raise ValueError(f"缺少目标列: {TARGET_COLUMN}")
    if frame[feature_columns].isna().any().any():
        raise ValueError("输入特征存在缺失值")
    target = (frame[TARGET_COLUMN].to_numpy(dtype=int) > 0).astype(int)
    if set(target) != {0, 1}:
        raise ValueError("碰撞标签必须同时包含正负样本")
    if np.sum(target) < 3 or np.sum(target == 0) < 3:
        raise ValueError("正负样本均至少需要 3 个独立场景")
    return feature_columns, target


def main():
    args = parse_args()
    if args.repeats < 2:
        raise ValueError("--repeats 必须至少为 2")
    if args.n_estimators <= 0:
        raise ValueError("--n-estimators 必须大于 0")

    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(os.path.abspath(args.dataset))
    feature_columns, target = validate_frame(frame)
    features = frame[feature_columns].to_numpy(dtype=float)
    sample_ids = frame["sample_id"].astype(str).to_numpy()
    positive_count = int(np.sum(target))
    negative_count = int(np.sum(target == 0))
    rows = []
    prediction_rows = []
    prediction_matrices = {}

    for model_offset, model_name in enumerate(MODEL_NAMES):
        model_predictions = np.full((args.repeats, len(frame)), np.nan)
        for repeat_index in range(args.repeats):
            split_seed = args.random_state + repeat_index
            splitter = StratifiedKFold(
                n_splits=3,
                shuffle=True,
                random_state=split_seed,
            )
            probabilities = np.full(len(frame), np.nan)
            for fold_index, (train_index, test_index) in enumerate(
                splitter.split(features, target)
            ):
                model_seed = (
                    args.random_state
                    + repeat_index * 100
                    + model_offset * 10
                    + fold_index
                )
                model = make_model(model_name, model_seed, args.n_estimators)
                model.fit(features[train_index], target[train_index])
                probabilities[test_index] = model.predict_proba(
                    features[test_index]
                )[:, 1]
            if np.isnan(probabilities).any():
                raise RuntimeError("碰撞 OOF 预测存在缺失值")
            model_predictions[repeat_index] = probabilities
            metrics = evaluate(target, probabilities)
            rows.append(
                {
                    "model": model_name,
                    "repeat_index": repeat_index,
                    "split_seed": split_seed,
                    **metrics,
                }
            )
            for sample_index, sample_id in enumerate(sample_ids):
                prediction_rows.append(
                    {
                        "model": model_name,
                        "repeat_index": repeat_index,
                        "sample_id": sample_id,
                        "collision_label": int(target[sample_index]),
                        "predicted_collision_probability": float(
                            probabilities[sample_index]
                        ),
                    }
                )
        prediction_matrices[model_name] = model_predictions

    metrics_frame = pd.DataFrame(rows)
    prediction_frame = pd.DataFrame(prediction_rows)
    metrics_frame.to_csv(
        output_dir / "repeat_metrics.csv", index=False, encoding="utf-8-sig"
    )
    prediction_frame.to_csv(
        output_dir / "oof_predictions.csv", index=False, encoding="utf-8-sig"
    )

    models = {}
    for model_name in MODEL_NAMES:
        current = metrics_frame[metrics_frame["model"] == model_name]
        models[model_name] = {
            "metrics": {
                name: metric_summary(current[name])
                for name in (
                    "roc_auc",
                    "average_precision",
                    "brier",
                    "precision",
                    "recall",
                    "f1",
                )
            }
        }
    selected_model = max(
        MODEL_NAMES,
        key=lambda name: models[name]["metrics"]["average_precision"]["mean"],
    )
    summary = {
        "format": "collision_proxy_diagnostics_v1",
        "dataset": os.path.abspath(args.dataset),
        "independent_scenario_count": int(len(frame)),
        "collision_positive_count": positive_count,
        "collision_negative_count": negative_count,
        "feature_columns": feature_columns,
        "analysis_unit": "independent_scenario",
        "repeated_stratified_oof": {
            "repeats": args.repeats,
            "folds": 3,
            "strata": "collision_label",
            "random_state": args.random_state,
        },
        "selected_model": selected_model,
        "models": models,
        "interpretation_boundary": (
            f"当前只有 {positive_count} 个碰撞独立场景；本结果仅用于判断是否值得建立独立碰撞反馈通道，"
            "不代表跨地图、跨控制策略的碰撞概率预测能力。"
        ),
    }
    with open(output_dir / "collision_proxy_summary.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2, allow_nan=False)

    selected = models[selected_model]["metrics"]
    report = [
        "# 独立碰撞倾向代理可行性诊断",
        "",
        f"- 独立场景：`{len(frame)}` 个；碰撞正样本：`{positive_count}` 个；非碰撞负样本：`{negative_count}` 个。",
        f"- 诊断：`{args.repeats}` 次重复三折分层 OOF，按碰撞标签分层。",
        f"- 当前按平均 Average Precision 选择：`{selected_model}`。",
        f"- Average Precision：`{selected['average_precision']['mean']:.3f} ± {selected['average_precision']['std']:.3f}`。",
        f"- ROC-AUC：`{selected['roc_auc']['mean']:.3f} ± {selected['roc_auc']['std']:.3f}`。",
        f"- Recall：`{selected['recall']['mean']:.3f} ± {selected['recall']['std']:.3f}`；F1：`{selected['f1']['mean']:.3f} ± {selected['f1']['std']:.3f}`。",
        "",
        "## 解释边界",
        "",
        summary["interpretation_boundary"],
        "",
        "该结果只决定是否保留独立碰撞反馈通道；连续风险代理仍需单独使用，不能将碰撞概率直接解释为连续风险分数。",
    ]
    (output_dir / "collision_proxy_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print(
        f"[COLLISION] samples={len(frame)} | positive={positive_count} | "
        f"selected={selected_model} | ap={selected['average_precision']['mean']:.3f} | "
        f"roc_auc={selected['roc_auc']['mean']:.3f}"
    )
    print(f"[COLLISION] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
