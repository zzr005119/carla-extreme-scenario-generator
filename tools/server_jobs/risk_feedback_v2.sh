#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/risk_feedback_v2/$timestamp"
dataset_dir="$result_dir/dataset"
proxy_dir="$result_dir/proxy"
diagnostics_dir="$result_dir/diagnostics"
artifact_dir="$PROJECT_MODEL_ROOT/artifacts/risk_proxy_v2/$timestamp"
addition_dataset="$PWD/data/scenarios/risk_feedback_v2/external_validation_addition.csv"

python -u tools/merge_risk_feedback_datasets.py \
  --addition-dataset "$addition_dataset" \
  --output-dir "$dataset_dir" \
  --version-label V2

python -u analysis/train_risk_proxy.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$proxy_dir" \
  --artifact-dir "$artifact_dir" \
  --version-label V2 \
  --random-state 20260815

python -u analysis/analyze_risk_proxy_diagnostics.py \
  --dataset "$dataset_dir/dataset.csv" \
  --output-dir "$diagnostics_dir" \
  --version-label V2 \
  --repeats 50 \
  --n-estimators 300 \
  --random-state 20260815

echo "[MODEL_DIR] $artifact_dir"
echo "[RESULT_DIR] $result_dir"
