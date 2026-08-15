#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/risk_feedback_v2/collision_proxy_v1/$timestamp"

python -u analysis/analyze_collision_proxy.py \
  --dataset "$PWD/data/scenarios/risk_feedback_v2/dataset.csv" \
  --output-dir "$result_dir" \
  --repeats 50 \
  --n-estimators 300 \
  --random-state 20260815

echo "[RESULT_DIR] $result_dir"
