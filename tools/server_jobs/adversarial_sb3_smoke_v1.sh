#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/adversarial_sb3_smoke_v1/$timestamp"

python - <<'PY'
import gymnasium
import stable_baselines3
import torch

assert stable_baselines3.__version__ == "2.9.0"
print(f"gymnasium={gymnasium.__version__}")
print(f"stable_baselines3={stable_baselines3.__version__}")
print(f"torch={torch.__version__}")
PY

python -m unittest \
  tests.test_adversarial_gym_env \
  tests.test_adversarial_sb3_training

python -u tools/train_adversarial_sb3_smoke.py \
  --output-root "$result_dir" \
  --algorithms ppo sac \
  --total-timesteps 64 \
  --max-steps 8 \
  --seed 20260821 \
  --device cpu

echo "[RESULT_DIR] $result_dir"
