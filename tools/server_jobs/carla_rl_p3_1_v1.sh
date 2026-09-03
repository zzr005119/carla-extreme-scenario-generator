#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/zhaozirong/projects/carla-extreme-scenario-generator}"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"
OUTPUT_BASE="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
ROOT="${CARLA_RL_P3_1_ROOT:-$OUTPUT_BASE/carla_rl_p3_1_v1}"
PLAN_PATH="${PLAN_PATH:-$ROOT/carla_rl_multiscene_plan_v1.json}"
CONFIG="$PROJECT_ROOT/configs/adversarial_loop_multistep_p3_1.json"
ENTRIES="$PROJECT_ROOT/data/scenarios/scenario_library_v1/entries.jsonl"
MANIFEST="$PROJECT_ROOT/data/scenarios/scenario_library_v1/manifest.json"
SEED="${RL_SEED:-20260903}"
MODE="${1:?需要 canary、pilot、resume-pilot 或 evaluate-dev}"

cd "$PROJECT_ROOT"

prepare_plan() {
  mkdir -p "$(dirname "$PLAN_PATH")"
  "$PYTHON" -u tools/prepare_carla_rl_multiscene_plan.py \
    --entries "$ENTRIES" --manifest "$MANIFEST" \
    --output "$PLAN_PATH" --seed "$SEED"
}

if [[ ! -s "$PLAN_PATH" ]]; then
  prepare_plan
fi

quality_gate() {
  local output_root="$1"
  local steps="$2"
  "$PYTHON" -u tools/check_carla_rl_training.py \
    --output-root "$output_root" --expected-algorithm SAC \
    --expected-steps "$steps" --require-continuity
}

dev_summary_usable() {
  local summary="$1"
  local model="$2"
  [[ -f "$summary" ]] || return 1
  "$PYTHON" - "$summary" "$model" "$CONFIG" "$PLAN_PATH" "$((SEED + 100000))" <<'PY'
import hashlib
import json
import pathlib
import sys


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


summary_path, model, config, plan_path, expected_seed = sys.argv[1:]
payload = json.load(open(summary_path, encoding="utf-8"))
plan = json.load(open(plan_path, encoding="utf-8"))
acceptance = payload.get("acceptance") or {}
checks = acceptance.get("checks") or {}
required_gates = {
    "baseline_strict_acceptance",
    "candidate_condition_validity",
    "candidate_runtime_strict_acceptance",
    "candidate_evidence_completeness",
}
passed = (
    payload.get("format") == "carla_online_rl_evaluation_v2"
    and payload.get("split") == "dev"
    and acceptance.get("status") == "passed"
    and set(checks) == required_gates
    and all((checks.get(name) or {}).get("passed") is True for name in required_gates)
    and pathlib.Path(payload.get("model_path", "")).resolve() == pathlib.Path(model).resolve()
    and payload.get("model_sha256") == sha256(model)
    and payload.get("config_sha256") == sha256(config)
    and payload.get("scenario_plan_sha256") == plan.get("plan_sha256")
    and int(payload.get("seed", -1)) == int(expected_seed)
)
raise SystemExit(0 if passed else 1)
PY
}

case "$MODE" in
  canary)
    output="$ROOT/canary_sac_seed_${SEED}_256"
    test ! -e "$output/checkpoint_manifest.json"
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$output" --algorithm SAC \
      --steps 256 --chunk-steps 256 --seed "$SEED" \
      --allow-online-carla
    quality_gate "$output" 256
    ;;
  pilot)
    output="$ROOT/pilot_sac_seed_${SEED}_2000"
    test ! -e "$output/checkpoint_manifest.json"
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$output" --algorithm SAC \
      --steps 2000 --chunk-steps 1000 --seed "$SEED" \
      --allow-online-carla
    quality_gate "$output" 2000
    ;;
  resume-pilot)
    output="$ROOT/pilot_sac_seed_${SEED}_2000"
    checkpoint="$(find "$output/models" -maxdepth 1 -type f -name 'sac_seed_*_steps_*.zip' -print 2>/dev/null | sort | tail -n 1)"
    if [[ -z "$checkpoint" ]]; then
      echo "[P3.1] 未找到可恢复 checkpoint: $output/models" >&2
      exit 76
    fi
    "$PYTHON" -u tools/train_carla_rl.py \
      --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
      --output-root "$output" --algorithm SAC \
      --steps 2000 --chunk-steps 1000 --seed "$SEED" \
      --resume "$checkpoint" --allow-online-carla
    quality_gate "$output" 2000
    ;;
  evaluate-dev)
    pilot="$ROOT/pilot_sac_seed_${SEED}_2000"
    summaries=()
    for steps in 001000 002000; do
      model="$pilot/models/sac_seed_${SEED}_steps_${steps}.zip"
      eval_root="$ROOT/dev_sac_seed_${SEED}_steps_${steps}"
      summary="$eval_root/test_evaluation_summary.json"
      test -f "$model"
      if dev_summary_usable "$summary" "$model"; then
        echo "[P3.1] 复用已验收 dev 摘要: $summary"
      else
        "$PYTHON" -u tools/evaluate_carla_rl_multiscene.py \
          --config "$CONFIG" --scenario-plan "$PLAN_PATH" \
          --model "$model" --algorithm SAC --split dev \
          --output-root "$eval_root" --seed "$((SEED + 100000))" \
          --allow-online-carla
      fi
      summaries+=(--evaluation-summary "$summary")
    done
    selection="$ROOT/dev_checkpoint_selection.json"
    "$PYTHON" -u tools/select_carla_rl_checkpoint.py \
      "${summaries[@]}" --output "$selection"
    "$PYTHON" - "$selection" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
gate = payload.get("promotion_gate") or {}
print(f"[P3.1] promotion_gate={gate.get('status')}")
print(f"[P3.1] selected_model={payload.get('selected_model_path')}")
raise SystemExit(0 if gate.get("status") == "passed" else 78)
PY
    ;;
  *)
    echo "用法: $0 {canary|pilot|resume-pilot|evaluate-dev}" >&2
    exit 2
    ;;
esac
