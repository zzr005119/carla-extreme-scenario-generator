#!/usr/bin/env bash
set -euo pipefail

plan_root="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_expand_v1"
plan_dir="$(find "$plan_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
if [[ -z "$plan_dir" ]]; then
  echo "No expansion plan found under $plan_root" >&2
  exit 1
fi
python - "$plan_dir" <<'PY'
import json
import os
import sys

plan_dir = sys.argv[1]
with open(os.path.join(plan_dir, "summary.json"), encoding="utf-8") as file:
    summary = json.load(file)
if summary.get("format") != "adversarial_policy_carla_plan_summary_v1":
    raise SystemExit("Latest expansion directory is not a policy plan")
if summary.get("total_run_count") != 18 or summary.get("scene_config_validation_count") != 18:
    raise SystemExit("Expansion plan must contain 18 statically validated runs")
if summary.get("selection_audit", {}).get("excluded_overlap_count") != 0:
    raise SystemExit("Expansion plan overlaps excluded library entries")
print(f"[PLAN_DIR] {plan_dir}")
PY
python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-id apcv1_pair_01 \
  --output-dir "$plan_dir/execution" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"
echo "[RESULT_DIR] $plan_dir"
