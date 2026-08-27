#!/usr/bin/env bash
set -u

PROJECT_ROOT="${PROJECT_ROOT:-/home/zhaozirong/projects/carla-extreme-scenario-generator}"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"
OUTPUT_BASE="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
RUN_ROOT="${OUTPUT_BASE}/carla_rl_multiscene_v1/stop_lock_recheck_$(date -u +%Y%m%d_%H%M%S)"
OLD_ROOT="${OUTPUT_BASE}/carla_rl_multiscene_v1/sac_seed_20260824_10000"

cd "$PROJECT_ROOT"
mkdir -p "$RUN_ROOT"

records=(
  "$OLD_ROOT/episodes/rl_multiscene_sac_seed_20260824_20260825_184913/episodes/rl_multiscene_sac_seed_20260824_20260825_184913_0038/steps/00_baseline/scenario_record.json"
  "$OLD_ROOT/episodes/rl_multiscene_sac_seed_20260824_20260825_184913/episodes/rl_multiscene_sac_seed_20260824_20260825_184913_0117/steps/14_candidate/scenario_record.json"
)
names=(
  "gmm_critical_20260816_0119_stop_lock_recheck"
  "gmm_critical_20260816_0243_adv_0013_stop_lock_recheck"
)

failed=0
for i in 0 1; do
  record="${records[$i]}"
  name="${names[$i]}"
  if [[ ! -f "$record" ]]; then
    echo "[RECHECK] missing record: $record" >&2
    failed=1
    continue
  fi
  echo "[RECHECK] sample=${name}"
  "$PYTHON" -u tools/recheck_carla_record.py \
    --record "$record" \
    --output-root "$RUN_ROOT" \
    --name "$name" \
    --traffic-manager-port "${CARLA_TRAFFIC_MANAGER_PORT:-8100}" \
    --timeout 300 || failed=1
done

echo "[RECHECK] output_root=$RUN_ROOT"
exit "$failed"
