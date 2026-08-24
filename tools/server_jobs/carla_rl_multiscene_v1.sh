#!/usr/bin/env bash
set -euo pipefail

# Run on the CARLA 0.9.16 server. CARLA must already be started by the owner;
# this job never kills an unknown process and never touches GPU0/vLLM.
PROJECT_ROOT="${PROJECT_ROOT:-/home/zhaozirong/projects/carla-extreme-scenario-generator}"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"
OUTPUT_BASE="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
OUTPUT_ROOT="${CARLA_RL_OUTPUT_ROOT:-$OUTPUT_BASE/carla_rl_multiscene_v1}"
PLAN_PATH="${PLAN_PATH:-$OUTPUT_ROOT/carla_rl_multiscene_plan_v1.json}"
CONFIG="$PROJECT_ROOT/configs/adversarial_loop_multistep_v1.json"
ENTRIES="$PROJECT_ROOT/data/scenarios/scenario_library_v1/entries.jsonl"
MANIFEST="$PROJECT_ROOT/data/scenarios/scenario_library_v1/manifest.json"
SEED="${RL_SEED:-20260824}"
MODE="${1:-canary}"
EVAL_SPLIT="${EVAL_SPLIT:-test}"
CANARY_SUFFIX="${RL_CANARY_SUFFIX:-}"

cd "$PROJECT_ROOT"

prepare_plan() {
  mkdir -p "$(dirname "$PLAN_PATH")"
  "$PYTHON" -u tools/prepare_carla_rl_multiscene_plan.py \
    --entries "$ENTRIES" --manifest "$MANIFEST" \
    --output "$PLAN_PATH" --seed "$SEED"
}

if [[ "$MODE" != "prepare" && ! -s "$PLAN_PATH" ]]; then
  prepare_plan
fi

case "$MODE" in
  prepare)
    prepare_plan
    ;;
  canary)
    canary_root="$OUTPUT_ROOT/canary_sac_seed_${SEED}"
    if [[ -n "$CANARY_SUFFIX" ]]; then
      canary_root="${canary_root}_${CANARY_SUFFIX}"
    fi
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$canary_root" \
      --algorithm SAC --steps 256 --chunk-steps 256 --seed "$SEED" \
      --allow-online-carla
    ;;
  train)
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$OUTPUT_ROOT/sac_seed_${SEED}_10000" \
      --algorithm SAC --steps 10000 --chunk-steps 1000 --seed "$SEED" \
      --allow-online-carla
    ;;
  resume)
    CHECKPOINT="${2:?resume 需要 .zip checkpoint 路径}"
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$OUTPUT_ROOT/sac_seed_${SEED}_10000" \
      --algorithm SAC --steps 10000 --chunk-steps 1000 --seed "$SEED" \
      --resume "$CHECKPOINT" --allow-online-carla
    ;;
  evaluate)
    MODEL="${2:?evaluate 需要 model .zip 路径}"
    "$PYTHON" -u tools/evaluate_carla_rl_multiscene.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --model "$MODEL" --algorithm SAC \
      --split "$EVAL_SPLIT" \
      --output-root "$OUTPUT_ROOT/${EVAL_SPLIT}_sac_seed_${SEED}" \
      --seed "$((SEED + 100000))" --allow-online-carla
    ;;
  *)
    echo "用法: $0 {prepare|canary|train|resume <checkpoint.zip>|evaluate <model.zip>}" >&2
    exit 2
    ;;
esac
