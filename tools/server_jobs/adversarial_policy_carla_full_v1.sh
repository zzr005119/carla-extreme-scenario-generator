#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_plan_v1"
plan_dir="$(find "$plan_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [[ -z "$plan_dir" ]]; then
  echo "No adversarial policy CARLA plan found under $plan_root" >&2
  exit 1
fi

python - "$plan_dir" <<'PY'
import json
import os
import sys

plan_dir = sys.argv[1]
with open(os.path.join(plan_dir, "summary.json"), encoding="utf-8") as file:
    plan = json.load(file)
with open(
    os.path.join(plan_dir, "execution", "summary.json"),
    encoding="utf-8",
) as file:
    smoke = json.load(file)

expected_hash = "df0c022070ac6535929fa1a1c29e2a34f2b0ba7f0242e55a624971caeba805d5"
if plan.get("format") != "adversarial_policy_carla_plan_summary_v1":
    raise SystemExit("Latest directory is not a policy CARLA plan V1")
if plan.get("total_run_count") != 36:
    raise SystemExit("Policy plan must contain exactly 36 runs")
if plan.get("scene_config_validation_count") != 36:
    raise SystemExit("Policy plan static validation is incomplete")
if plan.get("selection_audit", {}).get("excluded_overlap_count") != 0:
    raise SystemExit("Policy plan overlaps the proxy evaluation set")
if plan.get("policy_model", {}).get("verified_sha256") != expected_hash:
    raise SystemExit("Policy model hash does not match the frozen SAC model")
if smoke.get("selected_pair_count") != 1 or not smoke.get("runtime_gate_passed"):
    raise SystemExit("The required one-pair CARLA smoke gate has not passed")
print(f"[PLAN_DIR] {plan_dir}")
PY

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-count 12 \
  --output-dir "$plan_dir/execution" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

analysis_dir="$plan_dir/analysis_v1"
if [[ -e "$analysis_dir" ]]; then
  echo "Analysis directory already exists: $analysis_dir" >&2
  exit 1
fi
python -u tools/analyze_adversarial_baseline_carla_results.py \
  --results "$plan_dir/execution/run_results.json" \
  --output-dir "$analysis_dir"

echo "[RESULT_DIR] $plan_dir"
