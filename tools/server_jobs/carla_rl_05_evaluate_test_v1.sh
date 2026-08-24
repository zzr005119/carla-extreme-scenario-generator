#!/usr/bin/env bash
set -euo pipefail

output_base="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
base="${CARLA_RL_OUTPUT_ROOT:-$output_base/carla_rl_multiscene_v1}"
model="$base/sac_seed_${RL_SEED:-20260824}_10000/sac_seed_${RL_SEED:-20260824}_final.zip"
test -f "$model"
test -f "$base/dev_sac_seed_${RL_SEED:-20260824}/test_evaluation_summary.json"
EVAL_SPLIT=test bash tools/server_jobs/carla_rl_multiscene_v1.sh evaluate "$model"
