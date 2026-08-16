#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/risk_feedback_v4/$timestamp"
dataset_dir="$result_dir/dataset"
proxy_dir="$result_dir/proxy"
diagnostics_dir="$result_dir/diagnostics_v4_top9"
baseline_dir="$result_dir/baseline_v3_top9"
comparison_dir="$result_dir/comparison_v3_v4"
artifact_dir="$PROJECT_MODEL_ROOT/artifacts/risk_proxy_v4/$timestamp"

base_dataset="$(find "$PROJECT_OUTPUT_ROOT/risk_feedback_v3" -type f -path '*/dataset/dataset.csv' | sort | tail -n 1)"
addition_dataset="$(find "$PROJECT_OUTPUT_ROOT/collision_boundary_multisensor_v1" -type f -path '*/plan/feedback_dataset_addition.csv' | sort | tail -n 1)"

if [[ -z "$base_dataset" || ! -f "$base_dataset" ]]; then
  echo "[V4] 未找到风险反馈 V3 数据集" >&2
  exit 2
fi
if [[ -z "$addition_dataset" || ! -f "$addition_dataset" ]]; then
  echo "[V4] 未找到碰撞边界主动补样新增数据集" >&2
  exit 2
fi

python -u tools/merge_risk_feedback_datasets.py \
  --base-dataset "$base_dataset" \
  --addition-dataset "$addition_dataset" \
  --output-dir "$dataset_dir" \
  --version-label V4

python -u analysis/analyze_risk_proxy_diagnostics.py \
  --dataset "$base_dataset" \
  --output-dir "$baseline_dir" \
  --version-label V3_top9 \
  --top-k 9 \
  --repeats 50 \
  --n-estimators 300 \
  --random-state 20260816

python -u analysis/train_risk_proxy.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$proxy_dir" \
  --artifact-dir "$artifact_dir" \
  --version-label V4 \
  --random-state 20260816

python -u analysis/analyze_risk_proxy_diagnostics.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$diagnostics_dir" \
  --version-label V4 \
  --top-k 9 \
  --repeats 50 \
  --n-estimators 300 \
  --random-state 20260816

python -u analysis/compare_risk_proxy_versions_generic.py \
  --before-summary "$baseline_dir/diagnostic_summary.json" \
  --after-summary "$diagnostics_dir/diagnostic_summary.json" \
  --before-label V3 \
  --after-label V4 \
  --output-dir "$comparison_dir"

echo "[V4] base=$base_dataset"
echo "[V4] addition=$addition_dataset"
echo "[RESULT_DIR] $result_dir"
echo "[MODEL_DIR] $artifact_dir"
