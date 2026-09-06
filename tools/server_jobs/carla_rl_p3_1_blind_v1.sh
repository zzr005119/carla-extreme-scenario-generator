#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/zhaozirong/projects/carla-extreme-scenario-generator}"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"
OUTPUT_BASE="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
ROOT="${CARLA_RL_P3_1_ROOT:-$OUTPUT_BASE/carla_rl_p3_1_v1}"
BLIND_PLAN="${BLIND_PLAN_PATH:-$PROJECT_ROOT/data/scenarios/carla_rl_p3_1_independent_blind_v1/carla_rl_multiscene_plan_p3_1_blind_v1.json}"
CONFIG="$PROJECT_ROOT/configs/adversarial_loop_multistep_p3_1.json"
SEED="${RL_SEED:-20260903}"
BLIND_SEED="${RL_BLIND_SEED:-20260906}"
EVAL_SEED="${RL_BLIND_EVAL_SEED:-22260903}"
SELECTION="$ROOT/dev_checkpoint_selection.json"
EVAL_ROOT="$ROOT/blind_sac_seed_${SEED}_steps_001000"
SUMMARY="$EVAL_ROOT/test_evaluation_summary.json"

cd "$PROJECT_ROOT"

if [[ ! -s "$BLIND_PLAN" ]]; then
  "$PYTHON" -u tools/prepare_carla_rl_p3_1_blind_plan.py \
    --output "$BLIND_PLAN" --seed "$BLIND_SEED" --base-plan-seed "$SEED"
fi
test -s "$SELECTION"
model="$($PYTHON - "$SELECTION" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
gate = payload.get("promotion_gate") or {}
if gate.get("status") != "passed":
    raise SystemExit("dev checkpoint promotion_gate 未通过")
model = str(payload.get("selected_model_path") or "")
if not model:
    raise SystemExit("dev checkpoint selection 缺少 selected_model_path")
print(model)
PY
)"
test -f "$model"

summary_usable() {
  "$PYTHON" - "$SUMMARY" "$model" "$CONFIG" "$BLIND_PLAN" "$EVAL_SEED" <<'PY'
import hashlib
import json
import pathlib
import sys

summary_path, model, config, plan_path, expected_seed = sys.argv[1:]
if not pathlib.Path(summary_path).is_file():
    raise SystemExit(1)
payload = json.loads(pathlib.Path(summary_path).read_text(encoding="utf-8"))
plan = json.loads(pathlib.Path(plan_path).read_text(encoding="utf-8"))
acceptance = payload.get("acceptance") or {}
checks = acceptance.get("checks") or {}
required = {
    "baseline_strict_acceptance",
    "candidate_condition_validity",
    "candidate_runtime_strict_acceptance",
    "candidate_evidence_completeness",
}
passed = (
    payload.get("format") == "carla_online_rl_evaluation_v2"
    and payload.get("split") == "blind"
    and acceptance.get("status") == "passed"
    and set(checks) == required
    and all((checks.get(name) or {}).get("passed") is True for name in required)
    and pathlib.Path(payload.get("model_path", "")).resolve() == pathlib.Path(model).resolve()
    and payload.get("model_sha256") == hashlib.sha256(pathlib.Path(model).read_bytes()).hexdigest()
    and payload.get("config_sha256") == hashlib.sha256(pathlib.Path(config).read_bytes()).hexdigest()
    and payload.get("scenario_plan_sha256") == plan.get("plan_sha256")
    and int(payload.get("seed", -1)) == int(expected_seed)
)
raise SystemExit(0 if passed else 1)
PY
}

if summary_usable; then
  echo "[P3.1] 复用已验收 blind 摘要: $SUMMARY"
else
  "$PYTHON" -u tools/evaluate_carla_rl_multiscene.py \
    --config "$CONFIG" --scenario-plan "$BLIND_PLAN" \
    --model "$model" --algorithm SAC --split blind \
    --output-root "$EVAL_ROOT" --seed "$EVAL_SEED" \
    --allow-online-carla
fi

echo "[P3.1] blind_plan=$BLIND_PLAN"
echo "[P3.1] selected_model=$model"
echo "[P3.1] summary=$SUMMARY"
