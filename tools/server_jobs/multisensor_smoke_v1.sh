#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/multisensor_smoke_v1/$timestamp"
config_dir="$result_dir/config"
runtime_root="$result_dir/runtime"

mkdir -p "$config_dir" "$runtime_root"
python -u tools/prepare_multisensor_smoke.py \
  --output-dir "$config_dir" \
  --runtime-output-root "$runtime_root"

python -u scenes/scene_04_parameterized.py \
  --config "$config_dir/config.json"

metadata_path="$(find "$runtime_root" -type f -name metadata.json | sort | tail -n 1)"
if [[ -z "$metadata_path" || ! -f "$metadata_path" ]]; then
  echo "[MULTISENSOR] 未找到 metadata.json" >&2
  exit 2
fi

python - "$metadata_path" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as file:
    metadata = json.load(file)
frames = metadata.get("frames", {})
required = ("rgb", "depth", "semantic")
missing = [name for name in required if int(frames.get(name, 0)) < 100]
print(f"[MULTISENSOR] metadata={path}")
print(f"[MULTISENSOR] frames={frames}")
if missing:
    raise SystemExit(f"[MULTISENSOR] 帧数不足: {missing}")
print("[MULTISENSOR] RGB + Depth + Semantic 写盘检查通过")
PY

echo "[RESULT_DIR] $result_dir"
