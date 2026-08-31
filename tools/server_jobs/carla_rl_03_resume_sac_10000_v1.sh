#!/usr/bin/env bash
set -euo pipefail

output_base="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
root="${CARLA_RL_OUTPUT_ROOT:-$output_base/carla_rl_multiscene_v1}/sac_seed_${RL_SEED:-20260824}_10000"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"

run_quality_gates() {
  local aggregate_status=0
  local episode_id

  # Preserve the historical audit while evaluating this training episode on its own.
  if "$PYTHON" -u tools/check_carla_rl_training.py \
    --output-root "$root" --expected-algorithm SAC --expected-steps 10000 \
    --output "$root/quality_gate.json"; then
    aggregate_status=0
  else
    aggregate_status=$?
  fi
  echo "[RL] all_episode_quality_gate_exit=$aggregate_status"

  episode_id="$("$PYTHON" - "$root/run_manifest.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
episode_id = payload.get("episode_id")
if not isinstance(episode_id, str) or not episode_id:
    raise SystemExit("run_manifest.json 缺少 episode_id")
print(episode_id)
PY
)"
  echo "[RL] current_episode=$episode_id"
  "$PYTHON" -u tools/check_carla_rl_training.py \
    --output-root "$root" --expected-algorithm SAC --expected-steps 10000 \
    --episode-id "$episode_id" \
    --output "$root/quality_gate_current_episode.json"
}

if [[ -f "$root/rl_training_summary.json" ]] && "$PYTHON" - "$root/rl_training_summary.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(
    0
    if payload.get("status") == "completed"
    and int(payload.get("trained_num_timesteps", -1)) == 10000
    else 1
)
PY
then
  echo "[RL] SAC 10000 训练已完成，重新生成全量/当前 episode 质量门: $root"
  run_quality_gates
  exit $?
fi

checkpoint="$(find "$root/models" -maxdepth 1 -type f -name 'sac_seed_*_steps_*.zip' -print 2>/dev/null | sort | tail -n 1)"
if [[ -z "$checkpoint" ]]; then
  echo "[RL] 未找到可恢复的 SAC checkpoint: $root/models" >&2
  exit 76
fi

echo "[RL] resume_checkpoint=$checkpoint"
bash tools/server_jobs/carla_rl_multiscene_v1.sh resume "$checkpoint"
run_quality_gates
