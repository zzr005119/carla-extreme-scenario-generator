"""Screen contact-stability settings for the independent MJX two-body probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mjx_multibody_probe import MJXMultiBodyProbe, MultiBodyProbeConfig, available  # noqa: E402


SCREENING_DESIGN = [
    {"force": 0.05, "timestep": 0.005, "initial_gap": 4.0, "iterations": 1},
    {"force": 0.05, "timestep": 0.020, "initial_gap": 6.0, "iterations": 4},
    {"force": 0.20, "timestep": 0.005, "initial_gap": 6.0, "iterations": 4},
    {"force": 0.20, "timestep": 0.020, "initial_gap": 4.0, "iterations": 1},
    {"force": 0.05, "timestep": 0.005, "initial_gap": 6.0, "iterations": 1},
    {"force": 0.05, "timestep": 0.020, "initial_gap": 4.0, "iterations": 4},
    {"force": 0.20, "timestep": 0.005, "initial_gap": 4.0, "iterations": 4},
    {"force": 0.20, "timestep": 0.020, "initial_gap": 6.0, "iterations": 1},
]


def main() -> int:
    parser = argparse.ArgumentParser(description="MJX 双刚体接触稳定性筛选")
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizon", type=int, default=128)
    parser.add_argument("--penetration-tolerance", type=float, default=0.05)
    parser.add_argument("--epsilon", type=float, default=1e-4)
    args = parser.parse_args()
    if not available():
        print("[MJX-stability] blocked: 缺少 jax/mujoco")
        return 2
    if args.penetration_tolerance < 0:
        raise ValueError("penetration-tolerance 不能小于 0")

    rows = []
    for index, setting in enumerate(SCREENING_DESIGN, start=1):
        config = MultiBodyProbeConfig(
            horizon=args.horizon,
            timestep=setting["timestep"],
            initial_gap_m=setting["initial_gap"],
            solver_iterations=setting["iterations"],
        )
        backend = MJXMultiBodyProbe(config)
        actions = backend.jnp.zeros((config.horizon, 2), dtype=backend.jnp.float64)
        actions = actions.at[:, 0].set(setting["force"])
        result = backend.rollout(actions)
        native = backend.native_rollout(actions)
        gradient = backend.gradient_check(actions, epsilon=args.epsilon)
        min_gap = float(result["gap_m"].min().item())
        max_qpos_error = float(backend.jnp.max(backend.jnp.abs(result["qpos_m"] - native["qpos_m"])).item())
        max_gap_error = float(backend.jnp.max(backend.jnp.abs(result["gap_m"] - native["gap_m"])).item())
        max_penetration = max(0.0, -min_gap)
        stable = bool(
            gradient["finite"]
            and gradient["relative_error"] < 1e-2
            and max_qpos_error < 1e-5
            and max_gap_error < 1e-5
            and max_penetration <= args.penetration_tolerance
        )
        rows.append(
            {
                "case_id": f"mbs_{index:02d}",
                "settings": setting,
                "min_gap_m": min_gap,
                "max_penetration_m": max_penetration,
                "loss": float(result["loss"].item()),
                "gradient": gradient,
                "native_mujoco_comparison": {
                    "max_qpos_abs_error_m": max_qpos_error,
                    "max_gap_abs_error_m": max_gap_error,
                    "within_tolerance": bool(max_qpos_error < 1e-5 and max_gap_error < 1e-5),
                },
                "stability_gate": "pass" if stable else "fail",
            }
        )
        print(
            f"[MJX-stability] {index}/8 {rows[-1]['case_id']} "
            f"force={setting['force']} dt={setting['timestep']} gap0={setting['initial_gap']} "
            f"iter={setting['iterations']} min_gap={min_gap:.6f} "
            f"fd_rel={gradient['relative_error']:.3g} gate={rows[-1]['stability_gate']}"
        )

    manifest = {
        "format": "mjx_multibody_stability_screen_manifest_v1",
        "status": "completed",
        "backend": "MJX-JAX",
        "device": str(backend.jax.devices()[0]),
        "platform": backend.jax.default_backend(),
        "config": {
            "horizon": args.horizon,
            "penetration_tolerance_m": args.penetration_tolerance,
            "epsilon": args.epsilon,
        },
        "design": {
            "type": "balanced_fractional_screening",
            "factor_names": ["force", "timestep", "initial_gap", "iterations"],
            "runs": len(SCREENING_DESIGN),
            "levels": {
                "force": sorted({item["force"] for item in SCREENING_DESIGN}),
                "timestep": sorted({item["timestep"] for item in SCREENING_DESIGN}),
                "initial_gap": sorted({item["initial_gap"] for item in SCREENING_DESIGN}),
                "iterations": sorted({item["iterations"] for item in SCREENING_DESIGN}),
            },
        },
        "runs": rows,
        "summary": {
            "stable_runs": sum(row["stability_gate"] == "pass" for row in rows),
            "failed_runs": sum(row["stability_gate"] == "fail" for row in rows),
            "minimum_observed_gap_m": min(row["min_gap_m"] for row in rows),
            "maximum_observed_penetration_m": max(row["max_penetration_m"] for row in rows),
        },
        "claims": {
            "contact_stability_screened": True,
            "physical_realism_gate_passed": False,
            "custom_vjp_training_ready": False,
            "training_integrated": False,
        },
        "boundary_note": "这是双刚体接触参数筛选，不是车辆动力学真实性证明，也不构成 CVAE/Diffusion 训练接入。",
    }
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[MJX-stability] device={manifest['device']} stable="
        f"{manifest['summary']['stable_runs']}/{manifest['design']['runs']} manifest={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
