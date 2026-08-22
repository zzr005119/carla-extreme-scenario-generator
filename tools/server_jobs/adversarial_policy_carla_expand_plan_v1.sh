#!/usr/bin/env bash
set -euo pipefail

root="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_expand_v1"
excluded_path="$root/excluded_library_entries.jsonl"
proxy_path="$PROJECT_OUTPUT_ROOT/adversarial_proxy_benchmark_v1/20260821_175341/evaluation_samples.jsonl"
policy_plan_path="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_plan_v1/20260821_202710/run_plan.json"
mkdir -p "$root"

python - "$excluded_path" "$proxy_path" "$policy_plan_path" <<'PY'
import json
import os
import sys

excluded_path, proxy_path, policy_plan_path = sys.argv[1:]
library_ids = []
with open(proxy_path, encoding="utf-8") as file:
    for line in file:
        if line.strip():
            row = json.loads(line)
            library_ids.append(str(row["sampling"]["library_id"]))
with open(policy_plan_path, encoding="utf-8") as file:
    plan = json.load(file)
for row in plan["runs"]:
    if row.get("phase") == "baseline":
        library_ids.append(str(row["library_id"]))

if len(library_ids) != 36 or len(set(library_ids)) != 36:
    raise SystemExit(
        f"Expected 36 unique prior library entries, got rows={len(library_ids)} "
        f"unique={len(set(library_ids))}"
    )
with open(excluded_path, "w", encoding="utf-8", newline="\n") as file:
    for library_id in library_ids:
        file.write(json.dumps({"sampling": {"library_id": library_id}}))
        file.write("\n")
print(f"[EXCLUDED] rows={len(library_ids)} path={excluded_path}")
PY

timestamp="$(date +%Y%m%d_%H%M%S)"
plan_dir="$root/$timestamp"
runtime_dir="$PROJECT_OUTPUT_ROOT/adversarial_policy_carla_expand_runtime_v1/$timestamp"
python -m unittest \
  tests.test_adversarial_policy_carla_plan \
  tests.test_adversarial_baseline_carla_plan \
  tests.test_adversarial_proxy_executor
python -u tools/prepare_adversarial_policy_carla_plan.py \
  --config configs/adversarial_policy_carla_expand_v1.json \
  --output-dir "$plan_dir" \
  --runtime-output-root "$runtime_dir" \
  --traffic-manager-port "$CARLA_TRAFFIC_MANAGER_PORT"
echo "[RESULT_DIR] $plan_dir"
