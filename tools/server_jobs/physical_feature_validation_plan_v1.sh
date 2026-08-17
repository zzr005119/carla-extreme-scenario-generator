#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/physical_feature_validation_v1/$timestamp"
latest_scoring="$(find "$PROJECT_OUTPUT_ROOT/physical_candidate_scoring_v1" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"

if [[ -z "$latest_scoring" || ! -f "$latest_scoring/raw_15d/scored_candidates.csv" ]]; then
  echo "[PHYSICAL_PLAN] 未找到物理增强候选重评分结果" >&2
  exit 2
fi

python -u -m analysis.select_physical_feature_candidate_pairs \
  --baseline-scored "$latest_scoring/raw_15d/scored_candidates.csv" \
  --baseline-selection "$latest_scoring/raw_15d/dual_channel_selected.csv" \
  --enhanced-scored "$latest_scoring/physical_enhanced/scored_candidates.csv" \
  --enhanced-selection "$latest_scoring/physical_enhanced/dual_channel_selected.csv" \
  --output-dir "$result_dir/pair_selection"

python -u tools/prepare_physical_feature_paired_validation.py \
  --pair-selection "$result_dir/pair_selection/pair_selection.csv" \
  --baseline-records "$latest_scoring/raw_15d/dual_channel_selected.jsonl" \
  --baseline-selection "$latest_scoring/raw_15d/dual_channel_selected.csv" \
  --enhanced-records "$latest_scoring/physical_enhanced/dual_channel_selected.jsonl" \
  --enhanced-selection "$latest_scoring/physical_enhanced/dual_channel_selected.csv" \
  --output-dir "$result_dir/plan" \
  --runtime-output-root "$result_dir/runtime" \
  --carla-root "$PWD" \
  --sensor-profile rgb_collision \
  --run-seed 20260817 \
  --validate-runner

echo "[PHYSICAL_PLAN] scoring=$latest_scoring"
echo "[RESULT_DIR] $result_dir"
