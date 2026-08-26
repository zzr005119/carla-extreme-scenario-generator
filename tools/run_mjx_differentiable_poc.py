"""Run the optional MJX-JAX P4.1 differentiable rigid-body PoC."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mjx_differentiable_poc import MJXDifferentiableBackend, MJXPoCConfig, available  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="MJX-JAX 可微刚体 P4.1 最小 PoC")
    parser.add_argument(
        "--output",
        default="artifacts/p4_1_mjx_differentiable_poc_v1/manifest.json",
        help="JSON manifest 输出路径",
    )
    parser.add_argument("--horizon", type=int, default=32)
    parser.add_argument("--force", type=float, default=2.0, help="恒定主车执行器力")
    parser.add_argument("--epsilon", type=float, default=1e-4, help="有限差分步长")
    parser.add_argument("--solver-iterations", type=int, default=4)
    parser.add_argument(
        "--compare-workarounds",
        action="store_true",
        help="对照固定 1 次求解迭代与配置求解迭代的反向模式",
    )
    parser.add_argument(
        "--probe-custom-vjp",
        action="store_true",
        help="验证正常多次迭代下的 forward-over-reverse 自定义 VJP",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not available():
        print("[MJX-PoC] blocked: 缺少 jax/mujoco，可安装 requirements-mjx-poc.txt")
        return 2
    config = MJXPoCConfig(horizon=args.horizon, solver_iterations=args.solver_iterations)
    backend = MJXDifferentiableBackend(config)
    actions = backend.jnp.full((config.horizon,), args.force, dtype=backend.jnp.float64)
    manifest = backend.manifest(
        actions,
        epsilon=args.epsilon,
        compare_workarounds=args.compare_workarounds,
        probe_custom_vjp=args.probe_custom_vjp,
    )
    manifest["action_profile"] = "constant_force"
    manifest["action_force"] = args.force
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[MJX-PoC] quality_gate={manifest['quality_gate']} "
        f"device={manifest['device']} "
        f"min_gap_m={manifest['rollout']['min_gap_m']:.6f} "
        f"fd_rel_error={manifest['gradient_check']['relative_error']:.6g}"
    )
    print(f"[MJX-PoC] reverse_mode_available={manifest['gradient_check']['reverse_mode_available']}")
    if manifest["workaround_probe"]:
        for row in manifest["workaround_probe"]:
            print(
                f"[MJX-PoC] workaround={row['strategy']} "
                f"iterations={row['solver_iterations']} "
                f"reverse={row['reverse_mode_available']} "
                f"native_ok={row['within_native_tolerance']}"
            )
    if manifest["custom_vjp_probe"]:
        probe = manifest["custom_vjp_probe"]
        print(
            f"[MJX-PoC] custom_vjp=available "
            f"max_diff={probe['max_abs_difference_to_jacfwd']:.6g} "
            f"fd_rel_error={probe['relative_error_to_finite_difference']:.6g}"
        )
    print(f"[MJX-PoC] manifest={output}")
    return 0 if manifest["quality_gate"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
