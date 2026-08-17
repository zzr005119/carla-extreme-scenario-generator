#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/physical_feature_validation_v1"
smoke_script="$(find "$plan_root" -type f -path '*/plan/run_smoke.sh' | sort | tail -n 1)"

if [[ -z "$smoke_script" || ! -f "$smoke_script" ]]; then
  echo "[PHYSICAL_SMOKE] 未找到物理增强配对验证计划" >&2
  exit 2
fi

echo "[PHYSICAL_SMOKE] 使用计划: $smoke_script"
bash "$smoke_script"
