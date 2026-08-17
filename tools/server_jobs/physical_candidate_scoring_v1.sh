#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/physical_candidate_scoring_v1/$timestamp"
candidate_dir="$result_dir/candidate_pools"
baseline_dir="$result_dir/raw_15d"
enhanced_dir="$result_dir/physical_enhanced"
comparison_dir="$result_dir/comparison"
dataset="$(find "$PROJECT_OUTPUT_ROOT/risk_feedback_v4" -type f -path '*/dataset/dataset.csv' | sort | tail -n 1)"

if [[ -z "$dataset" || ! -f "$dataset" ]]; then
  echo "[PHYSICAL_SCORE] 未找到风险反馈 V4 数据集" >&2
  exit 2
fi

mkdir -p "$candidate_dir"
for level_index in 0 1; do
  if [[ "$level_index" == "0" ]]; then
    level="high"
    weather_tags="heavy_rain,fog,night,wet_road"
  else
    level="critical"
    weather_tags="heavy_rain,dense_fog,night,wet_road,strong_wind"
  fi
  level_seed=$((20260817 + level_index))
  for generator in lhs gmm cvae; do
    output_path="$candidate_dir/${generator}_${level}.jsonl"
    args=(
      --model "$generator"
      --risk "$level"
      --weather-tags "$weather_tags"
      --count 256
      --max-attempts 4096
      --seed "$level_seed"
      --output "$output_path"
    )
    if [[ "$generator" == "gmm" ]]; then
      args+=(--artifact "$PROJECT_MODEL_ROOT/artifacts/gmm/seed_v1.json")
    elif [[ "$generator" == "cvae" ]]; then
      args+=(--artifact "$PROJECT_MODEL_ROOT/artifacts/cvae/final_seed_v1/best.pt")
    fi
    python -u tools/generate_with_model.py "${args[@]}"
  done
done

candidate_args=(
  --dataset "$dataset"
  --candidates "$candidate_dir/lhs_high.jsonl"
  --candidates "$candidate_dir/gmm_high.jsonl"
  --candidates "$candidate_dir/cvae_high.jsonl"
  --candidates "$candidate_dir/lhs_critical.jsonl"
  --candidates "$candidate_dir/gmm_critical.jsonl"
  --candidates "$candidate_dir/cvae_critical.jsonl"
  --scoring-repeats 5
  --bootstrap-models 30
  --n-estimators 300
  --select-per-channel 3
  --min-per-target-channel 1
  --random-state 20260817
)

python -u -m analysis.score_feedback_candidates_dual \
  "${candidate_args[@]}" \
  --feature-space raw_15d \
  --output-dir "$baseline_dir"

python -u -m analysis.score_feedback_candidates_dual \
  "${candidate_args[@]}" \
  --feature-space physical_enhanced \
  --output-dir "$enhanced_dir"

python -u -m analysis.compare_candidate_scoring_feature_spaces \
  --baseline-dir "$baseline_dir" \
  --enhanced-dir "$enhanced_dir" \
  --output-dir "$comparison_dir"

echo "[PHYSICAL_SCORE] dataset=$dataset"
echo "[RESULT_DIR] $result_dir"
