#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/risk_feedback_v3/$timestamp"
dataset_dir="$result_dir/dataset"
proxy_dir="$result_dir/proxy"
diagnostics_dir="$result_dir/diagnostics"
artifact_dir="$PROJECT_MODEL_ROOT/artifacts/risk_proxy_v3/$timestamp"
base_dataset="$PWD/data/scenarios/risk_feedback_v2/dataset.csv"
addition_dataset="$(find "$PROJECT_OUTPUT_ROOT/dual_channel_validation_v1" -type f -path '*/plan/feedback_dataset_addition.csv' | sort | tail -n 1)"

if [[ ! -f "$base_dataset" ]]; then
  echo "[V3] 缺少基础风险反馈数据集: $base_dataset" >&2
  exit 2
fi
if [[ -z "$addition_dataset" || ! -f "$addition_dataset" ]]; then
  echo "[V3] 未找到双通道验证新增数据集" >&2
  exit 2
fi

python -u tools/merge_risk_feedback_datasets.py \
  --base-dataset "$base_dataset" \
  --addition-dataset "$addition_dataset" \
  --output-dir "$dataset_dir" \
  --version-label V3

python -u analysis/train_risk_proxy.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$proxy_dir" \
  --artifact-dir "$artifact_dir" \
  --version-label V3 \
  --random-state 20260816

python -u analysis/analyze_risk_proxy_diagnostics.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$diagnostics_dir" \
  --version-label V3 \
  --repeats 50 \
  --n-estimators 300 \
  --random-state 20260816

echo "[V3] addition=$addition_dataset"
echo "[RESULT_DIR] $result_dir"
echo "[MODEL_DIR] $artifact_dir"
