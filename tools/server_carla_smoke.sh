#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import carla

client = carla.Client("127.0.0.1", 2000)
client.set_timeout(10.0)
print(client.get_world().get_map().name)
PY
