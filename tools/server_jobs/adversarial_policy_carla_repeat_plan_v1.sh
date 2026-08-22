#!/usr/bin/env bash
set -euo pipefail
python -u tools/prepare_adversarial_policy_carla_repeat_plan.py \
  --config configs/adversarial_policy_carla_repeat_plan_v1.json \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"
