"""Run the independent two-dynamic-body MJX contact probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mjx_multibody_probe import MJXMultiBodyProbe, MultiBodyProbeConfig, available  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MJX-JAX 双动态刚体接触压力测试")
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizon", type=int, default=128)
    parser.add_argument("--force", type=float, default=5.0, help="ego 恒定力；lead 默认 0")
    parser.add_argument("--timestep", type=float, default=0.02)
    parser.add_argument("--initial-gap", type=float, default=4.0)
    parser.add_argument("--solver-iterations", type=int, default=4)
    parser.add_argument("--epsilon", type=float, default=1e-4)
    parser.add_argument("--compare-workarounds", action="store_true")
    parser.add_argument("--probe-custom-vjp", action="store_true")
    args = parser.parse_args()
    if not available():
        print("[MJX-multibody] blocked: 缺少 jax/mujoco")
        return 2
    config = MultiBodyProbeConfig(
        horizon=args.horizon,
        timestep=args.timestep,
        initial_gap_m=args.initial_gap,
        solver_iterations=args.solver_iterations,
    )
    backend = MJXMultiBodyProbe(config)
    actions = backend.jnp.zeros((config.horizon, 2), dtype=backend.jnp.float64)
    actions = actions.at[:, 0].set(args.force)
    manifest = backend.manifest(
        actions,
        epsilon=args.epsilon,
        compare_workarounds=args.compare_workarounds,
        probe_custom_vjp=args.probe_custom_vjp,
    )
    manifest["action_profile"] = "ego_constant_lead_zero"
    manifest["ego_force"] = args.force
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[MJX-multibody] quality_gate={manifest['quality_gate']} "
        f"device={manifest['device']} min_gap_m={manifest['rollout']['min_gap_m']:.6f} "
        f"fd_rel_error={manifest['gradient_check']['relative_error']:.6g}"
    )
    if manifest["workaround_probe"]:
        for row in manifest["workaround_probe"]:
            print(
                f"[MJX-multibody] workaround={row['strategy']} "
                f"iterations={row['solver_iterations']} reverse={row['reverse_mode_available']} "
                f"native_ok={row['within_native_tolerance']}"
            )
    if manifest["custom_vjp_probe"]:
        probe = manifest["custom_vjp_probe"]
        print(
            f"[MJX-multibody] custom_vjp max_diff={probe['max_abs_difference_to_jacfwd']:.6g} "
            f"fd_rel_error={probe['relative_error_to_finite_difference']:.6g}"
        )
    print(f"[MJX-multibody] manifest={output}")
    return 0 if manifest["quality_gate"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
