#!/usr/bin/env bash
set -euo pipefail

output_base="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
root="${CARLA_RL_OUTPUT_ROOT:-$output_base/carla_rl_multiscene_v1}/canary_sac_seed_${RL_SEED:-20260824}"

if [[ -f "$root/quality_gate.json" ]] && python - "$root/quality_gate.json" <<'PY'
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1], encoding="utf-8")).get("status") == "passed" else 1)
PY
then
  echo "[RL] SAC 256 canary 已通过，不重复运行: $root"
  exit 0
fi

bash tools/server_jobs/carla_rl_multiscene_v1.sh canary
python -u tools/check_carla_rl_training.py \
  --output-root "$root" --expected-algorithm SAC --expected-steps 256
