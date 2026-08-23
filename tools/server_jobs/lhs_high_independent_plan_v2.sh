#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
plan_dir="$PROJECT_OUTPUT_ROOT/lhs_high_independent_carla_plan_v2/$timestamp"
runtime_dir="$PROJECT_OUTPUT_ROOT/lhs_high_independent_carla_runtime_v2/$timestamp"

python -u tools/prepare_lhs_high_independent_carla_plan.py \
  --config configs/lhs_high_independent_carla_plan_v2.json \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

echo "[RESULT_DIR] $plan_dir"
