#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/dual_channel_validation_v1"
smoke_script="$(find "$plan_root" -type f -name run_smoke.sh | sort | tail -n 1)"

if [[ -z "$smoke_script" || ! -f "$smoke_script" ]]; then
  echo "[SMOKE] 未找到双通道验证计划中的 run_smoke.sh" >&2
  exit 2
fi

echo "[SMOKE] 使用计划: $smoke_script"
bash "$smoke_script"
