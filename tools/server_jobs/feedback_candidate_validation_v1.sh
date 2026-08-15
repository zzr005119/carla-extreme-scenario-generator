#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
experiment_root="$PROJECT_OUTPUT_ROOT/feedback_candidate_validation_v1/$timestamp"
plan_dir="$experiment_root/plan"
runtime_dir="$experiment_root/runtime"

python -u tools/prepare_feedback_candidate_validation.py \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --carla-root "$PWD" \
  --run-seed 20260815 \
  --validate-runner

python -u tools/run_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json" \
  --limit 1

python -u tools/collect_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json" \
  --allow-missing

python -u tools/run_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json"

python -u tools/collect_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json"

echo "[RESULT_DIR] $experiment_root"
