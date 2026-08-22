#!/usr/bin/env bash
set -euo pipefail

plan_dir="$(find "$PROJECT_OUTPUT_ROOT/lhs_high_independent_carla_plan_v1" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [ -z "$plan_dir" ] || [ ! -f "$plan_dir/run_plan.json" ]; then
    echo "[JOB] no independent LHS/high plan found" >&2
    exit 2
fi
execution_dir="$plan_dir/execution_smoke_v1"

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-id lhs_high_boundary_v1_01 \
  --output-dir "$execution_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT" \
  --pause-seconds 0

echo "[RESULT_DIR] $execution_dir"
