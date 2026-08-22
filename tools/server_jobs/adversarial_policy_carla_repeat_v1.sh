#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_repeat_plan_v1"
plan_dir="$(find "$plan_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [[ -z "$plan_dir" ]]; then
  echo "No repeated policy CARLA plan found under $plan_root" >&2
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
    raise SystemExit("Latest directory is not a repeated policy CARLA plan V1")
if summary.get("selected_source_pair_count") != 3:
    raise SystemExit("Repeated policy plan must contain exactly 3 source pairs")
if summary.get("repeat_seed_count") != 3:
    raise SystemExit("Repeated policy plan must contain exactly 3 Traffic Manager seeds")
if summary.get("total_run_count") != 27:
    raise SystemExit("Repeated policy plan must contain exactly 27 runs")
if summary.get("scene_config_validation_count") != 27:
    raise SystemExit("Repeated policy plan static validation is incomplete")
if summary.get("carla_runtime_executed"):
    raise SystemExit("Repeated policy plan is already marked as runtime executed")
print(f"[PLAN_DIR] {plan_dir}")
PY

execution_dir="$plan_dir/execution"
analysis_dir="$plan_dir/analysis_v1"
if [[ -e "$analysis_dir" ]]; then
  echo "Analysis directory already exists: $analysis_dir" >&2
  exit 1
fi

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-count 9 \
  --output-dir "$execution_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

python -u tools/analyze_adversarial_baseline_carla_results.py \
  --results "$execution_dir/run_results.json" \
  --output-dir "$analysis_dir"

echo "[RESULT_DIR] $plan_dir"
