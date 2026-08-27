#!/usr/bin/env bash
set -u

PROJECT_ROOT="${PROJECT_ROOT:-/home/zhaozirong/projects/carla-extreme-scenario-generator}"
PYTHON="${PYTHON:-/home/zhaozirong/software/envs/Carla666-0916/bin/python}"
OUTPUT_BASE="${PROJECT_OUTPUT_ROOT:-/home/zhaozirong/software/output/carla-0.9.16}"
OLD_ROOT="${OUTPUT_BASE}/carla_rl_multiscene_v1/sac_seed_20260824_10000"
RUN_ROOT="${OUTPUT_BASE}/carla_rl_multiscene_v1/all_failed_recheck_$(date -u +%Y%m%d_%H%M%S)"

cd "$PROJECT_ROOT"
mkdir -p "$RUN_ROOT"

mapfile -t records < <("$PYTHON" - <<'PY'
import json
from pathlib import Path

root = Path('/home/zhaozirong/software/output/carla-0.9.16/carla_rl_multiscene_v1/sac_seed_20260824_10000/episodes')
seen = set()
for path in sorted(root.rglob('execution_result.json')):
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        continue
    result = payload.get('result') if isinstance(payload.get('result'), dict) else payload
    if result.get('strict_acceptance_passed') is True:
        continue
    record_path = path.with_name('scenario_record.json')
    if not record_path.is_file():
        continue
    key = str(record_path)
    if key in seen:
        continue
    seen.add(key)
    print(key)
PY
)

failed=0
index=0
for record in "${records[@]}"; do
  [[ -n "$record" ]] || continue
  index=$((index + 1))
  sample_id="$($PYTHON - "$record" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['sample_id'])
PY
)"
  name="failed_${index}_$(printf '%s' "$sample_id" | tr -cs 'A-Za-z0-9_-' '_')"
  echo "[RECHECK] ${index}/${#records[@]} sample=${sample_id}"
  "$PYTHON" -u tools/recheck_carla_record.py \
    --record "$record" \
    --output-root "$RUN_ROOT" \
    --name "$name" \
    --traffic-manager-port "${CARLA_TRAFFIC_MANAGER_PORT:-8100}" \
    --timeout 300 || failed=1
done

echo "[RECHECK] record_count=${#records[@]}"
echo "[RECHECK] output_root=$RUN_ROOT"
exit "$failed"
