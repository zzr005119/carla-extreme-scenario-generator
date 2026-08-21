#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/adversarial_sb3_proxy_smoke_v1/$timestamp"

python -m unittest \
  tests.test_adversarial_proxy_executor \
  tests.test_adversarial_sb3_training

python -u tools/train_adversarial_sb3_proxy_smoke.py \
  --output-root "$result_dir" \
  --algorithms ppo sac \
  --total-timesteps 64 \
  --seed 20260821 \
  --device cpu

echo "[RESULT_DIR] $result_dir"
