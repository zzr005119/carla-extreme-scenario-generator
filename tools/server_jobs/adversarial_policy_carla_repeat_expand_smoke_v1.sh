#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_repeat_expand_plan_v1"
plan_dir="$(find "$plan_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [[ -z "$plan_dir" ]]; then
  echo "No expansion repeat plan found under $plan_root" >&2
  exit 1
fi
python - "$plan_dir" <<'PY'
import json
import os
import sys

plan_dir = sys.argv[1]
with open(os.path.join(plan_dir, "summary.json"), encoding="utf-8") as file:
    summary = json.load(file)
if summary.get("format") != "adversarial_policy_carla_repeat_plan_summary_v1":
    raise SystemExit("Latest directory is not an expansion repeat plan")
if summary.get("selected_source_pair_count") != 2:
    raise SystemExit("Expansion repeat plan must contain exactly 2 source pairs")
if summary.get("repeat_seed_count") != 3 or summary.get("total_run_count") != 18:
    raise SystemExit("Expansion repeat plan must contain 3 seeds and 18 runs")
if summary.get("scene_config_validation_count") != 18:
    raise SystemExit("Expansion repeat plan static validation is incomplete")
print(f"[PLAN_DIR] {plan_dir}")
PY
python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-id apcv2_repeat_pair_01_s20260827 \
  --output-dir "$plan_dir/execution_smoke" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"
echo "[RESULT_DIR] $plan_dir"
