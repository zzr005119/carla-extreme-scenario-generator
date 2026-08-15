#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
output_dir="$PROJECT_OUTPUT_ROOT/feedback_candidate_scoring_v1/$timestamp"

python -u tools/prepare_feedback_candidate_scoring.py \
  --output-dir "$output_dir" \
  --gmm-artifact "$PROJECT_MODEL_ROOT/gmm/seed_v1.json" \
  --cvae-artifact "$PROJECT_MODEL_ROOT/cvae/final_seed_v1/best.pt" \
  --pool-size 256 \
  --max-attempts 4096 \
  --bootstrap-models 50 \
  --n-estimators 300 \
  --select-per-channel 3 \
  --seed 20260815

echo "[RESULT_DIR] $output_dir"
