#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/adversarial_loop_smoke_v1/$timestamp"

mkdir -p "$result_dir"
python -u tools/run_adversarial_episode.py \
  --mode carla \
  --record data/scenarios/cvae_validation_v2/selected_records.jsonl \
  --sample-id cvae_medium_20260813_0103 \
  --output-root "$result_dir" \
  --runtime-output-root "$result_dir/runtime" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

echo "[RESULT_DIR] $result_dir"
