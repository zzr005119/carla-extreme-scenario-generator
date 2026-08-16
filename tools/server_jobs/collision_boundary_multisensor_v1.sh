#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
experiment_root="$PROJECT_OUTPUT_ROOT/collision_boundary_multisensor_v1/$timestamp"
plan_dir="$experiment_root/plan"
runtime_dir="$experiment_root/runtime"
latest_scoring="$(find "$PROJECT_OUTPUT_ROOT/dual_candidate_scoring_v3" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"

if [[ -z "$latest_scoring" || ! -f "$latest_scoring/scoring/scored_candidates.csv" ]]; then
  echo "[ACTIVE_SAMPLE] 未找到 V3 候选评分目录" >&2
  exit 2
fi

mkdir -p "$plan_dir" "$runtime_dir"
python -u tools/prepare_collision_boundary_multisensor.py \
  --scoring-dir "$latest_scoring/scoring" \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --carla-root "$PWD" \
  --run-seed 20260816 \
  --validate-runner

python -u tools/run_feedback_candidate_validation.py \
  --manifest "$plan_dir/manifest.json" \
  --limit 1 \
  --pause-seconds 0
python -u tools/check_multisensor_manifest.py \
  --manifest "$plan_dir/manifest.json" \
  --min-completed 1

bash "$plan_dir/run_all.sh"
bash "$plan_dir/collect_results.sh"

echo "[RESULT_DIR] $experiment_root"
