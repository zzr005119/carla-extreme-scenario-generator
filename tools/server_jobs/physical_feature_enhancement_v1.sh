#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/physical_feature_enhancement_v1/$timestamp"
dataset="$(find "$PROJECT_OUTPUT_ROOT/risk_feedback_v4" -type f -path '*/dataset/dataset.csv' | sort | tail -n 1)"

if [[ -z "$dataset" || ! -f "$dataset" ]]; then
  echo "[PHYSICAL] 未找到风险反馈 V4 数据集" >&2
  exit 2
fi

python -u -m analysis.analyze_physical_feature_enhancement \
  --dataset "$dataset" \
  --output-dir "$result_dir" \
  --repeats 50 \
  --n-estimators 300 \
  --top-k 9 \
  --random-state 20260817

echo "[PHYSICAL] dataset=$dataset"
echo "[RESULT_DIR] $result_dir"
