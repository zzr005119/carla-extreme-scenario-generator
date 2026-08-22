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

python - "$plan_dir" <<'PY'
import copy
import json
import os
import sys

plan_dir = sys.argv[1]
plan_path = os.path.join(plan_dir, "run_plan.json")
manifest_path = os.path.join(plan_dir, "source_manifest.json")
with open(plan_path, encoding="utf-8") as file:
    plan = json.load(file)
with open(manifest_path, encoding="utf-8") as file:
    manifest = json.load(file)
with open(plan["summary"]["source_plan"], encoding="utf-8") as file:
    source_plan = json.load(file)

source_rows = {row["run_id"]: row for row in source_plan["runs"]}
source_run_ids = {row["run_id"]: row["source_run_id"] for row in manifest["runs"]}
fields = (
    "selected_action",
    "candidate_fingerprint",
    "policy_model_sha256",
    "policy_seed",
    "attempts",
    "attempt_count",
    "invalid_attempt_count",
    "first_attempt_valid",
)
changed = False
for row in plan["runs"]:
    if row.get("phase") != "candidate":
        continue
    source_row = source_rows[source_run_ids[row["run_id"]]]
    for field in fields:
        if field in source_row and row.get(field) != source_row[field]:
            row[field] = copy.deepcopy(source_row[field])
            changed = True
plan["summary"]["strategy_order"] = ["sac_policy", "rule_guided_lhs"]
if changed or plan["summary"].get("strategy_order") != ["sac_policy", "rule_guided_lhs"]:
    with open(plan_path, "w", encoding="utf-8") as file:
        json.dump(plan, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print("[PLAN] restored candidate actions from source policy plan")
else:
    print("[PLAN] candidate actions already present")
PY

python -u tools/run_adversarial_baseline_carla_plan.py \
  --plan "$plan_dir/run_plan.json" \
  --pair-count 9 \
  --output-dir "$execution_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"

python -u tools/analyze_adversarial_baseline_carla_results.py \
  --results "$execution_dir/run_results.json" \
  --output-dir "$analysis_dir"

echo "[RESULT_DIR] $plan_dir"
