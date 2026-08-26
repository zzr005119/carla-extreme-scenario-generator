#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAMBA_BIN="${MAMBA_BIN:-/home/zhaozirong/software/micromamba-bin/micromamba}"
ENV_PREFIX="${MJX_ENV_PREFIX:-/home/zhaozirong/software/envs/MJXPoC-Linux}"

export JAX_PLATFORMS=cpu
export MJX_JAX_PLATFORM=cpu
export CUDA_VISIBLE_DEVICES=""
export XLA_PYTHON_CLIENT_PREALLOCATE=false

cd "$PROJECT_ROOT"
exec "$MAMBA_BIN" run -p "$ENV_PREFIX" python tools/scan_mjx_multibody_contact_boundary.py "$@"
