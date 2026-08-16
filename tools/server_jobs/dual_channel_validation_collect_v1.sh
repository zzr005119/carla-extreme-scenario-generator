#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/dual_channel_validation_v1"
collect_script="$(find "$plan_root" -type f -name collect_results.sh | sort | tail -n 1)"

if [[ -z "$collect_script" || ! -f "$collect_script" ]]; then
  echo "[COLLECT] 未找到双通道验证计划中的 collect_results.sh" >&2
  exit 2
fi

echo "[COLLECT] 使用计划: $collect_script"
bash "$collect_script"
