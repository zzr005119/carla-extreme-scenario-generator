#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAMBA_BIN="${MAMBA_BIN:-/home/zhaozirong/software/micromamba-bin/micromamba}"
ENV_PREFIX="${MJX_GPU_ENV_PREFIX:-/home/zhaozirong/software/envs/MJXPoC-Linux-GPU1}"

export CUDA_VISIBLE_DEVICES=1
export JAX_PLATFORMS=cuda
export MJX_JAX_PLATFORM=cuda
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export XLA_PYTHON_CLIENT_MEM_FRACTION="${MJX_GPU_MEM_FRACTION:-0.10}"

cd "$PROJECT_ROOT"
exec "$MAMBA_BIN" run -p "$ENV_PREFIX" python tools/scan_mjx_multibody_contact_boundary.py "$@"
