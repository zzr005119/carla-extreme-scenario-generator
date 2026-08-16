#!/usr/bin/env bash
set -euo pipefail

experiment_root="$(find "$PROJECT_OUTPUT_ROOT/collision_boundary_multisensor_v1" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [[ -z "$experiment_root" || ! -f "$experiment_root/plan/manifest.json" ]]; then
  echo "[ACTIVE_SAMPLE_COLLECT] 未找到已完成实验清单" >&2
  exit 2
fi

plan_dir="$experiment_root/plan"
python -u tools/collect_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json"
python -u tools/check_multisensor_manifest.py \
  --manifest "$plan_dir/manifest.json" \
  --require-all

echo "[RESULT_DIR] $experiment_root"
