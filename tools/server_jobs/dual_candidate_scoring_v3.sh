#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/dual_candidate_scoring_v3/$timestamp"
candidate_dir="$result_dir/candidate_pools"
scoring_dir="$result_dir/scoring"
dataset="$PWD/data/scenarios/risk_feedback_v2/dataset.csv"
latest_v3_dataset="$(find "$PROJECT_OUTPUT_ROOT/risk_feedback_v3" -type f -path '*/dataset/dataset.csv' | sort | tail -n 1)"

if [[ -z "$latest_v3_dataset" || ! -f "$latest_v3_dataset" ]]; then
  echo "[V3_SCORE] 未找到风险反馈 V3 数据集" >&2
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
  level_seed=$((20260816 + level_index))
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

python -u analysis/score_feedback_candidates_dual.py \
  --dataset "$latest_v3_dataset" \
  --candidates "$candidate_dir/lhs_high.jsonl" \
  --candidates "$candidate_dir/gmm_high.jsonl" \
  --candidates "$candidate_dir/cvae_high.jsonl" \
  --candidates "$candidate_dir/lhs_critical.jsonl" \
  --candidates "$candidate_dir/gmm_critical.jsonl" \
  --candidates "$candidate_dir/cvae_critical.jsonl" \
  --output-dir "$scoring_dir" \
  --scoring-repeats 5 \
  --bootstrap-models 30 \
  --n-estimators 300 \
  --select-per-channel 3 \
  --min-per-target-channel 1 \
  --random-state 20260816

echo "[V3_SCORE] dataset=$latest_v3_dataset"
echo "[RESULT_DIR] $result_dir"
