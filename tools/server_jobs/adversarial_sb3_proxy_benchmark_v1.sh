#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date +%Y%m%d_%H%M%S)"
result_dir="$PROJECT_OUTPUT_ROOT/adversarial_proxy_benchmark_v1/$timestamp"

python -m unittest \
  tests.test_adversarial_proxy_benchmark \
  tests.test_adversarial_proxy_executor \
  tests.test_adversarial_sb3_training

python -u tools/benchmark_adversarial_sb3_proxy.py \
  --output-dir "$result_dir"

echo "[RESULT_DIR] $result_dir"
