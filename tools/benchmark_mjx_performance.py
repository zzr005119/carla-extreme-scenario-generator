"""Benchmark batched MJX forward and custom-VJP throughput.

The benchmark is intentionally separate from the correctness PoC.  It warms
up JAX compilation, reports steady-state timings, and keeps the gradient
comparison on a small batch so the reference ``jacfwd`` path remains bounded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mjx_differentiable_poc import MJXDifferentiableBackend, MJXPoCConfig, available  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="MJX-JAX CPU/GPU 批量性能基准")
    parser.add_argument("--output", required=True, help="JSON manifest 输出路径")
    parser.add_argument("--horizon", type=int, default=128)
    parser.add_argument("--force-limit", type=float, default=5.0)
    parser.add_argument("--batch-sizes", default="1,4,16")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--gradient-check-batch", type=int, default=2)
    return parser.parse_args()


def _ready(value):
    return value.block_until_ready() if hasattr(value, "block_until_ready") else value


def _measure(fn, actions, repeats: int) -> dict:
    start = time.perf_counter()
    warmup = _ready(fn(actions))
    compile_seconds = time.perf_counter() - start
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        _ready(fn(actions))
        samples.append(time.perf_counter() - start)
    median_seconds = sorted(samples)[len(samples) // 2]
    return {
        "compile_seconds": compile_seconds,
        "steady_seconds": samples,
        "median_seconds": median_seconds,
        "samples_per_second": actions.shape[0] / median_seconds,
        "output_shape": list(warmup.shape),
    }


def _make_actions(backend, batch_size: int):
    jnp = backend.jnp
    horizon = backend.config.horizon
    t = jnp.arange(horizon, dtype=jnp.float64)[None, :]
    row = jnp.arange(batch_size, dtype=jnp.float64)[:, None]
    actions = 0.8 * backend.config.force_limit * jnp.sin(0.07 * t + 0.31 * row)
    return jnp.clip(actions, -backend.config.force_limit, backend.config.force_limit)


def main() -> int:
    args = parse_args()
    if not available():
        print("[MJX-benchmark] blocked: 缺少 jax/mujoco")
        return 2
    if args.repeats < 1 or args.gradient_check_batch < 1:
        raise ValueError("repeats 和 gradient-check-batch 必须大于 0")
    batch_sizes = [int(item.strip()) for item in args.batch_sizes.split(",") if item.strip()]
    if not batch_sizes or any(item < 1 for item in batch_sizes):
        raise ValueError("batch-sizes 必须是正整数列表")

    config = MJXPoCConfig(horizon=args.horizon, force_limit=args.force_limit)
    backend = MJXDifferentiableBackend(config)
    jax = backend.jax
    batched_forward = jax.jit(jax.vmap(backend.loss))
    custom_loss = backend.loss_with_custom_vjp()
    batched_custom_grad = jax.jit(jax.vmap(jax.grad(custom_loss)))
    reference_jacfwd = jax.jit(jax.vmap(jax.jacfwd(backend.loss)))

    runs = []
    for batch_size in batch_sizes:
        actions = _make_actions(backend, batch_size)
        forward = _measure(batched_forward, actions, args.repeats)
        custom_grad = _measure(batched_custom_grad, actions, args.repeats)
        runs.append(
            {
                "batch_size": batch_size,
                "horizon": config.horizon,
                "forward": forward,
                "custom_vjp_gradient": custom_grad,
            }
        )

    check_batch = min(args.gradient_check_batch, max(batch_sizes))
    check_actions = _make_actions(backend, check_batch)
    custom_values = _ready(batched_custom_grad(check_actions))
    reference_values = _ready(reference_jacfwd(check_actions))
    max_gradient_difference = float(jax.numpy.max(jax.numpy.abs(custom_values - reference_values)).item())
    manifest = {
        "format": "mjx_performance_benchmark_v1",
        "status": "completed",
        "backend": "MJX-JAX",
        "device": str(jax.devices()[0]),
        "platform": jax.default_backend(),
        "versions": {
            "jax": jax.__version__,
            "mujoco": __import__("mujoco").__version__ if hasattr(__import__("mujoco"), "__version__") else "unknown",
        },
        "config": {
            "horizon": config.horizon,
            "force_limit": config.force_limit,
            "batch_sizes": batch_sizes,
            "repeats": args.repeats,
            "gradient_check_batch": check_batch,
        },
        "runs": runs,
        "gradient_check": {
            "method": "custom_vjp_vs_batched_jacfwd",
            "max_abs_difference": max_gradient_difference,
            "finite": bool(jax.numpy.isfinite(custom_values).all().item()),
        },
        "claims": {
            "batched_forward_throughput": True,
            "batched_custom_vjp_throughput": True,
            "custom_vjp_matches_jacfwd": max_gradient_difference < 1e-10,
            "training_integrated": False,
        },
        "boundary_note": "这是小规模 batched vmap+jit 性能基准，不代表已完成生成模型训练接入或 CARLA 车辆动力学闭环。",
    }
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[MJX-benchmark] device={manifest['device']} platform={manifest['platform']} "
        f"grad_max_diff={max_gradient_difference:.6g} manifest={output}"
    )
    for row in runs:
        print(
            f"[MJX-benchmark] batch={row['batch_size']} "
            f"forward={row['forward']['samples_per_second']:.3f}/s "
            f"custom_vjp={row['custom_vjp_gradient']['samples_per_second']:.3f}/s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
