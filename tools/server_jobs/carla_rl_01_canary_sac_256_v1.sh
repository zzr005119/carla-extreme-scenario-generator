#!/usr/bin/env bash
set -euo pipefail

output_base="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
output_parent="${CARLA_RL_OUTPUT_ROOT:-$output_base/carla_rl_multiscene_v1}"
seed="${RL_SEED:-20260824}"
root="$output_parent/canary_sac_seed_${seed}"

if [[ -f "$root/quality_gate.json" ]] && python - "$root/quality_gate.json" <<'PY'
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1], encoding="utf-8")).get("status") == "passed" else 1)
PY
then
  echo "[RL] SAC 256 canary 已通过，不重复运行: $root"
  exit 0
fi

suffix="${RL_CANARY_SUFFIX:-}"
if [[ -f "$root/quality_gate.json" && -z "$suffix" ]]; then
  suffix="retry_$(date -u +%Y%m%d_%H%M%S)"
fi
RL_CANARY_SUFFIX="$suffix" bash tools/server_jobs/carla_rl_multiscene_v1.sh canary
if [[ -n "$suffix" ]]; then
  root="${root}_${suffix}"
fi
python -u tools/check_carla_rl_training.py \
  --output-root "$root" --expected-algorithm SAC --expected-steps 256
