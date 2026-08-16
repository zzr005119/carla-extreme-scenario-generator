#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/dual_channel_validation_v1"
run_script="$(find "$plan_root" -type f -name run_all.sh | sort | tail -n 1)"

if [[ -z "$run_script" || ! -f "$run_script" ]]; then
  echo "[FULL] 未找到双通道验证计划中的 run_all.sh" >&2
  exit 2
fi

echo "[FULL] 使用计划: $run_script"
bash "$run_script"
