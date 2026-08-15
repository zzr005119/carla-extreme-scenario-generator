#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/risk_feedback_v2_top9/$timestamp"

python -u analysis/analyze_risk_proxy_diagnostics.py \
  --dataset "$PWD/data/scenarios/risk_feedback_v2/dataset.csv" \
  --output-dir "$result_dir" \
  --version-label V2_TOP9 \
  --repeats 50 \
  --n-estimators 300 \
  --top-k 9 \
  --random-state 20260815

echo "[RESULT_DIR] $result_dir"
