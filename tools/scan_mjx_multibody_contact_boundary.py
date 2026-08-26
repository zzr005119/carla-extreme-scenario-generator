"""Scan an independent counter-motion MJX contact boundary scenario.

The existing stability screen stays in a no-contact, low-force region.  This
screen drives both bodies toward one another so that the report distinguishes
numerical correctness from actual contact handling and penetration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mjx_multibody_probe import MJXMultiBodyProbe, MultiBodyProbeConfig, available  # noqa: E402


# A different action profile from the low-force ego-only stability screen.
# The relative closing force is increased while the geometry and horizon stay
# fixed, making the transition into contact observable and reproducible.
CONTACT_BOUNDARY_DESIGN = [
    {"ego_force": 0.25, "lead_force": -0.25},
    {"ego_force": 0.50, "lead_force": -0.50},
    {"ego_force": 1.00, "lead_force": -1.00},
    {"ego_force": 1.50, "lead_force": -1.50},
    {"ego_force": 2.00, "lead_force": -2.00},
    {"ego_force": 3.00, "lead_force": -3.00},
]


def classify_case(
    *,
    finite: bool,
    finite_difference_error: float,
    native_aligned: bool,
    contact_observed: bool,
    penetration_m: float,
    penetration_tolerance_m: float,
) -> tuple[str, bool, bool]:
    """Return (classification, numerical_gate, contact_gate)."""

    numerical_gate = bool(
        finite and finite_difference_error < 1e-2 and native_aligned
    )
    contact_gate = bool(contact_observed and penetration_m <= penetration_tolerance_m)
    if not numerical_gate:
        return "numerical_failure", numerical_gate, contact_gate
    if not contact_observed:
        return "no_contact_stable", numerical_gate, contact_gate
    if contact_gate:
        return "contact_stable", numerical_gate, contact_gate
    return "contact_penetration_unstable", numerical_gate, contact_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="MJX 相向运动接触边界扫描")
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizon", type=int, default=128)
    parser.add_argument("--timestep", type=float, default=0.02)
    parser.add_argument("--initial-gap", type=float, default=4.0)
    parser.add_argument("--solver-iterations", type=int, default=4)
    parser.add_argument("--penetration-tolerance", type=float, default=0.05)
    parser.add_argument("--epsilon", type=float, default=1e-4)
    parser.add_argument(
        "--probe-custom-vjp",
        action="store_true",
        help="对每组额外运行 custom VJP；默认只做 jacfwd/有限差分",
    )
    args = parser.parse_args()
    if args.penetration_tolerance < 0:
        raise ValueError("penetration-tolerance 不能小于 0")
    if not available():
        print("[MJX-boundary] blocked: 缺少 jax/mujoco")
        return 2

    rows = []
    for index, setting in enumerate(CONTACT_BOUNDARY_DESIGN, start=1):
        config = MultiBodyProbeConfig(
            horizon=args.horizon,
            timestep=args.timestep,
            initial_gap_m=args.initial_gap,
            solver_iterations=args.solver_iterations,
        )
        backend = MJXMultiBodyProbe(config)
        actions = backend.jnp.zeros((config.horizon, 2), dtype=backend.jnp.float64)
        actions = actions.at[:, 0].set(setting["ego_force"])
        actions = actions.at[:, 1].set(setting["lead_force"])
        result = backend.rollout(actions)
        native = backend.native_rollout(actions)
        gradient = backend.gradient_check(actions, epsilon=args.epsilon)
        min_gap = float(result["gap_m"].min().item())
        max_penetration = max(0.0, -min_gap)
        max_qpos_error = float(
            backend.jnp.max(backend.jnp.abs(result["qpos_m"] - native["qpos_m"])).item()
        )
        max_gap_error = float(
            backend.jnp.max(backend.jnp.abs(result["gap_m"] - native["gap_m"])).item()
        )
        native_aligned = bool(max_qpos_error < 1e-5 and max_gap_error < 1e-5)
        classification, numerical_gate, contact_gate = classify_case(
            finite=gradient["finite"],
            finite_difference_error=gradient["relative_error"],
            native_aligned=native_aligned,
            contact_observed=min_gap <= 0.0,
            penetration_m=max_penetration,
            penetration_tolerance_m=args.penetration_tolerance,
        )
        custom_vjp = None
        if args.probe_custom_vjp:
            custom_vjp = backend.custom_vjp_probe(actions, epsilon=args.epsilon)
        rows.append(
            {
                "case_id": f"counter_motion_{index:02d}",
                "settings": {
                    **setting,
                    "timestep": args.timestep,
                    "initial_gap": args.initial_gap,
                    "iterations": args.solver_iterations,
                },
                "min_gap_m": min_gap,
                "max_penetration_m": max_penetration,
                "contact_observed": bool(min_gap <= 0.0),
                "loss": float(result["loss"].item()),
                "gradient": gradient,
                "custom_vjp": custom_vjp,
                "native_mujoco_comparison": {
                    "max_qpos_abs_error_m": max_qpos_error,
                    "max_gap_abs_error_m": max_gap_error,
                    "within_tolerance": native_aligned,
                },
                "gates": {
                    "numerical": "pass" if numerical_gate else "fail",
                    "contact": "pass" if contact_gate else "fail",
                },
                "classification": classification,
            }
        )
        print(
            f"[MJX-boundary] {index}/{len(CONTACT_BOUNDARY_DESIGN)} "
            f"ego={setting['ego_force']} lead={setting['lead_force']} "
            f"min_gap={min_gap:.6f} penetration={max_penetration:.6f} "
            f"class={classification}"
        )

    summary = {
        "runs": len(rows),
        "numerical_gate_passes": sum(row["gates"]["numerical"] == "pass" for row in rows),
        "contact_gate_passes": sum(row["gates"]["contact"] == "pass" for row in rows),
        "contact_observed_runs": sum(row["contact_observed"] for row in rows),
        "classifications": {
            label: sum(row["classification"] == label for row in rows)
            for label in (
                "no_contact_stable",
                "contact_stable",
                "contact_penetration_unstable",
                "numerical_failure",
            )
        },
        "minimum_observed_gap_m": min(row["min_gap_m"] for row in rows),
        "maximum_observed_penetration_m": max(row["max_penetration_m"] for row in rows),
    }
    summary["contact_gate_pass_rate"] = (
        summary["contact_gate_passes"] / summary["contact_observed_runs"]
        if summary["contact_observed_runs"]
        else 0.0
    )
    all_contact_runs_pass = bool(
        summary["contact_observed_runs"] > 0
        and summary["contact_gate_passes"] == summary["contact_observed_runs"]
    )
    manifest = {
        "format": "mjx_multibody_contact_boundary_manifest_v1",
        "status": "completed",
        "backend": "MJX-JAX",
        "device": str(backend.jax.devices()[0]),
        "platform": backend.jax.default_backend(),
        "config": {
            "horizon": args.horizon,
            "timestep": args.timestep,
            "initial_gap_m": args.initial_gap,
            "solver_iterations": args.solver_iterations,
            "penetration_tolerance_m": args.penetration_tolerance,
            "epsilon": args.epsilon,
        },
        "action_profile": "counter_motion_ego_positive_lead_negative",
        "design": {
            "type": "independent_counter_motion_boundary",
            "factor_names": ["ego_force", "lead_force"],
            "runs": len(CONTACT_BOUNDARY_DESIGN),
            "levels": {
                "ego_force": sorted({item["ego_force"] for item in CONTACT_BOUNDARY_DESIGN}),
                "lead_force": sorted({item["lead_force"] for item in CONTACT_BOUNDARY_DESIGN}),
            },
        },
        "runs": rows,
        "summary": summary,
        "claims": {
            "independent_counter_motion_scenario": True,
            "numerical_gate_screened": True,
            "contact_boundary_identified": summary["contact_observed_runs"] > 0,
            "contact_realism_gate_passed": all_contact_runs_pass,
            "vehicle_dynamics_realism_proven": False,
            "custom_vjp_training_ready": False,
            "training_integrated": False,
        },
        "boundary_note": (
            "相向运动边界扫描用于区分数值一致性与接触真实性；"
            "穿透失稳是当前 MJX 小场景的失败证据，不得写成车辆动力学或生成模型训练已完成。"
        ),
    }
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[MJX-boundary] device={manifest['device']} "
        f"numerical={summary['numerical_gate_passes']}/{summary['runs']} "
        f"contact={summary['contact_gate_passes']}/{summary['runs']} manifest={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
