#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
plan_dir="$PROJECT_OUTPUT_ROOT/adversarial_baseline_carla_plan_v1/$timestamp"
runtime_dir="$PROJECT_OUTPUT_ROOT/adversarial_baseline_carla_comparison_v1/$timestamp"
execution_dir="$plan_dir/execution"

python -u tools/prepare_adversarial_baseline_carla_plan.py \
  --config configs/adversarial_baseline_carla_plan_v1.json \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

# Keep the five-run gate explicit before expanding to the remaining pairs.
python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-id abcv1_pair_01 \
  --output-dir "$execution_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-count 12 \
  --output-dir "$execution_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

echo "[RESULT_DIR] $plan_dir"
