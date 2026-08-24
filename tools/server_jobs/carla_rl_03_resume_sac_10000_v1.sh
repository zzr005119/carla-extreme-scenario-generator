#!/usr/bin/env bash
set -euo pipefail

output_base="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
root="${CARLA_RL_OUTPUT_ROOT:-$output_base/carla_rl_multiscene_v1}/sac_seed_${RL_SEED:-20260824}_10000"
checkpoint="$(find "$root/models" -maxdepth 1 -type f -name 'sac_seed_*_steps_*.zip' -print 2>/dev/null | sort | tail -n 1)"
if [[ -z "$checkpoint" ]]; then
  echo "[RL] 未找到可恢复的 SAC checkpoint: $root/models" >&2
  exit 76
fi

echo "[RL] resume_checkpoint=$checkpoint"
bash tools/server_jobs/carla_rl_multiscene_v1.sh resume "$checkpoint"
python -u tools/check_carla_rl_training.py \
  --output-root "$root" --expected-algorithm SAC --expected-steps 10000
