#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/dual_channel_validation_v1/$timestamp"
latest_scoring="$(find "$PROJECT_OUTPUT_ROOT/dual_candidate_scoring_v2" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
scoring_dir="$latest_scoring/scoring"

if [[ -z "$latest_scoring" || ! -f "$scoring_dir/single_channel_selected.jsonl" ]]; then
  echo "缺少双通道评分结果目录" >&2
  exit 2
fi

python -u tools/prepare_dual_channel_validation.py \
  --single-records "$scoring_dir/single_channel_selected.jsonl" \
  --single-selection "$scoring_dir/single_channel_selection_manifest.csv" \
  --dual-records "$scoring_dir/dual_channel_selected.jsonl" \
  --dual-selection "$scoring_dir/dual_channel_selection_manifest.csv" \
  --output-dir "$result_dir/plan" \
  --runtime-output-root "$result_dir/runtime" \
  --carla-root "$PWD" \
  --run-seed 20260816 \
  --validate-runner

echo "[RESULT_DIR] $result_dir"
