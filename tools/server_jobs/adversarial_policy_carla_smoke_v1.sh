#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
plan_dir="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_plan_v1/$timestamp"
runtime_dir="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_comparison_v1/$timestamp"

python -m unittest \
  tests.test_adversarial_policy_carla_plan \
  tests.test_adversarial_baseline_carla_plan \
  tests.test_adversarial_proxy_executor

python -u tools/prepare_adversarial_policy_carla_plan.py \
  --config configs/adversarial_policy_carla_plan_v1.json \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-id apcv1_pair_01 \
  --output-dir "$plan_dir/execution" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

echo "[RESULT_DIR] $plan_dir"
