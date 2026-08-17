#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/physical_feature_validation_v1"
plan_dir="$(find "$plan_root" -type f -path '*/plan/manifest.json' | sort | tail -n 1 | xargs -r dirname)"

if [[ -z "$plan_dir" || ! -f "$plan_dir/manifest.json" ]]; then
  echo "[PHYSICAL_FULL] 未找到物理增强配对验证计划" >&2
  exit 2
fi

echo "[PHYSICAL_FULL] 使用计划: $plan_dir"
bash "$plan_dir/run_all.sh"
python -u tools/collect_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json"

echo "[RESULT_DIR] $plan_dir"
