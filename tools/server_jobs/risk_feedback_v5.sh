#!/usr/bin/env bash
set -euo pipefail

result_root="$PROJECT_OUTPUT_ROOT/risk_feedback_v5"
mkdir -p "$result_root"
latest_result="$(find "$result_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
result_dir=""
if [[ -n "$latest_result" && -f "$latest_result/dataset/dataset.csv" ]] \
  && [[ ! -f "$latest_result/physical_feature_v5/physical_feature_summary.json" \
    || ! -f "$latest_result/proxy_physical_enhanced/proxy_summary.json" \
    || ! -f "$latest_result/comparison_v4_v5/risk_proxy_version_comparison.json" ]]; then
  result_dir="$latest_result"
  echo "[V5] 恢复未完成目录: $result_dir"
fi
if [[ -z "$result_dir" ]]; then
  timestamp="$(date +%Y%m%d_%H%M%S)"
  result_dir="$result_root/$timestamp"
fi

timestamp="$(basename "$result_dir")"
dataset_dir="$result_dir/dataset"
proxy_dir="$result_dir/proxy"
diagnostics_dir="$result_dir/diagnostics_v5_top9"
baseline_dir="$result_dir/baseline_v4_top9"
comparison_dir="$result_dir/comparison_v4_v5"
physical_dir="$result_dir/physical_feature_v5"
enhanced_proxy_dir="$result_dir/proxy_physical_enhanced"
artifact_dir="$PROJECT_MODEL_ROOT/artifacts/risk_proxy_v5/$timestamp"
enhanced_artifact_dir="$PROJECT_MODEL_ROOT/artifacts/risk_proxy_v5_physical/$timestamp"

base_dataset="$(find "$PROJECT_OUTPUT_ROOT/risk_feedback_v4" -type f -path '*/dataset/dataset.csv' | sort | tail -n 1)"
addition_dataset="$(find "$PROJECT_OUTPUT_ROOT/physical_feature_validation_v1" -type f -path '*/plan/feedback_dataset_addition.csv' | sort | tail -n 1)"

if [[ -z "$base_dataset" || ! -f "$base_dataset" ]]; then
  echo "[V5] 未找到风险反馈 V4 数据集" >&2
  exit 2
fi
if [[ -z "$addition_dataset" || ! -f "$addition_dataset" ]]; then
  echo "[V5] 未找到物理增强配对验证新增数据集" >&2
  exit 2
fi

if [[ ! -f "$dataset_dir/dataset.csv" ]]; then
  python -u tools/merge_risk_feedback_datasets.py \
    --base-dataset "$base_dataset" \
    --addition-dataset "$addition_dataset" \
    --output-dir "$dataset_dir" \
    --version-label V5
fi

if [[ ! -f "$baseline_dir/diagnostic_summary.json" ]]; then
  python -u analysis/analyze_risk_proxy_diagnostics.py \
    --dataset "$base_dataset" \
    --output-dir "$baseline_dir" \
    --version-label V4_top9 \
    --top-k 9 \
    --repeats 50 \
    --n-estimators 300 \
    --random-state 20260817
fi

if [[ ! -f "$proxy_dir/proxy_summary.json" ]]; then
  python -u analysis/train_risk_proxy.py \
    --dataset "$dataset_dir/dataset.csv" \
    --output-dir "$proxy_dir" \
    --artifact-dir "$artifact_dir" \
    --version-label V5 \
    --random-state 20260817
fi

if [[ ! -f "$diagnostics_dir/diagnostic_summary.json" ]]; then
  python -u analysis/analyze_risk_proxy_diagnostics.py \
    --dataset "$dataset_dir/dataset.csv" \
    --output-dir "$diagnostics_dir" \
    --version-label V5 \
    --top-k 9 \
    --repeats 50 \
    --n-estimators 300 \
    --random-state 20260817
fi

if [[ ! -f "$physical_dir/physical_feature_summary.json" ]]; then
  python -u -m analysis.analyze_physical_feature_enhancement \
    --dataset "$dataset_dir/dataset.csv" \
    --output-dir "$physical_dir" \
    --repeats 50 \
    --n-estimators 300 \
    --top-k 9 \
    --random-state 20260817
fi

if [[ ! -f "$enhanced_proxy_dir/proxy_summary.json" ]]; then
  python -u -m analysis.train_risk_proxy \
    --dataset "$dataset_dir/dataset.csv" \
    --output-dir "$enhanced_proxy_dir" \
    --artifact-dir "$enhanced_artifact_dir" \
    --version-label V5_physical \
    --feature-space physical_enhanced \
    --random-state 20260817
fi

if [[ ! -f "$comparison_dir/risk_proxy_version_comparison.json" ]]; then
  python -u analysis/compare_risk_proxy_versions_generic.py \
    --before-summary "$baseline_dir/diagnostic_summary.json" \
    --after-summary "$diagnostics_dir/diagnostic_summary.json" \
    --before-label V4 \
    --after-label V5 \
    --output-dir "$comparison_dir"
fi

echo "[V5] base=$base_dataset"
echo "[V5] addition=$addition_dataset"
echo "[RESULT_DIR] $result_dir"
echo "[MODEL_DIR] $artifact_dir"
echo "[PHYSICAL_MODEL_DIR] $enhanced_artifact_dir"
