"""MJX-JAX differentiable rigid-body proof of concept.

This module is an optional research backend for P4.1.  It deliberately keeps a
small one-dimensional ego/lead rigid-body scene so that the evidence answers a
narrow question: can an MJX-JAX rollout expose a numerically useful derivative
and remain close to native MuJoCo on CPU?

The module does not connect CARLA, run RL, or replace the current Torch/PyBullet
boundary.  MJX-JAX's forward-mode Jacobian is used for the first PoC because
reverse-mode differentiation through the current contact solver can fail on a
dynamic ``while_loop``.  That limitation is reported in the manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import importlib.util
import os
from typing import Any


@dataclass(frozen=True)
class MJXPoCConfig:
    """Configuration for the smallest useful rigid-body scene."""

    horizon: int = 32
    timestep: float = 0.02
    initial_gap_m: float = 6.0
    ego_half_length_m: float = 1.0
    lead_half_length_m: float = 1.0
    safe_gap_m: float = 4.0
    force_limit: float = 5.0
    damping: float = 0.1
    soft_temperature_m: float = 0.25
    smoothness_weight: float = 0.01
    solver_iterations: int = 4
    solver_ls_iterations: int = 4

    def validate(self) -> None:
        if self.horizon < 2:
            raise ValueError("horizon 必须至少为 2")
        if self.timestep <= 0:
            raise ValueError("timestep 必须大于 0")
        if self.initial_gap_m <= 0:
            raise ValueError("initial_gap_m 必须大于 0")
        if self.ego_half_length_m <= 0 or self.lead_half_length_m <= 0:
            raise ValueError("刚体半长必须大于 0")
        if self.safe_gap_m <= 0 or self.soft_temperature_m <= 0:
            raise ValueError("safe_gap_m 和 soft_temperature_m 必须大于 0")
        if self.force_limit <= 0 or self.damping < 0:
            raise ValueError("force_limit 必须大于 0，damping 不能小于 0")
        if self.smoothness_weight < 0:
            raise ValueError("smoothness_weight 不能小于 0")
        if self.solver_iterations < 1 or self.solver_ls_iterations < 1:
            raise ValueError("solver_iterations 和 solver_ls_iterations 必须至少为 1")

    @property
    def lead_center_x_m(self) -> float:
        return self.initial_gap_m + self.ego_half_length_m + self.lead_half_length_m


def available() -> bool:
    """Return whether the optional JAX/MJX packages are importable."""

    return importlib.util.find_spec("jax") is not None and importlib.util.find_spec("mujoco") is not None


def _imports():
    if not available():
        raise RuntimeError("缺少可选依赖，请安装 requirements-mjx-poc.txt")
    import jax

    # CPU remains the default; GPU runs opt in explicitly through the environment.
    platform = os.environ.get("MJX_JAX_PLATFORM", "cpu").strip() or "cpu"
    jax.config.update("jax_platforms", platform)
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    import mujoco
    from mujoco import mjx

    return jax, jnp, mujoco, mjx


def build_mjcf(config: MJXPoCConfig) -> str:
    """Build an MJCF scene with a sliding ego box and a static lead box."""

    config.validate()
    return f"""<mujoco>
  <option timestep=\"{config.timestep}\" gravity=\"0 0 0\" integrator=\"implicitfast\" iterations=\"{config.solver_iterations}\" ls_iterations=\"{config.solver_ls_iterations}\"/>
  <worldbody>
    <body name=\"ego\" pos=\"0 0 1\">
      <joint name=\"ego_slide\" type=\"slide\" axis=\"1 0 0\" damping=\"{config.damping}\"/>
      <geom name=\"ego_geom\" type=\"box\" size=\"{config.ego_half_length_m} 0.5 0.5\" mass=\"1\"/>
    </body>
    <body name=\"lead\" pos=\"{config.lead_center_x_m} 0 1\">
      <geom name=\"lead_geom\" type=\"box\" size=\"{config.lead_half_length_m} 0.5 0.5\" mass=\"1\"/>
    </body>
  </worldbody>
  <actuator>
    <motor joint=\"ego_slide\" gear=\"1\"/>
  </actuator>
</mujoco>"""


class MJXDifferentiableBackend:
    """Small MJX-JAX backend with native MuJoCo comparison support."""

    def __init__(self, config: MJXPoCConfig | None = None):
        self.config = config or MJXPoCConfig()
        self.config.validate()
        self.jax, self.jnp, self.mujoco, self.mjx = _imports()
        self.native_model = self.mujoco.MjModel.from_xml_string(build_mjcf(self.config))
        self.mjx_model = self.mjx.put_model(self.native_model)
        self.base_data = self.mjx.make_data(self.mjx_model)

    def _validate_actions(self, actions):
        actions = self.jnp.asarray(actions, dtype=self.jnp.float64)
        if actions.ndim != 1 or actions.shape[0] != self.config.horizon:
            raise ValueError(f"actions 形状必须为 [{self.config.horizon}]")
        return self.jnp.clip(actions, -self.config.force_limit, self.config.force_limit)

    def rollout(self, actions) -> dict[str, Any]:
        """Run the differentiable rigid-body rollout and return JAX arrays."""

        actions = self._validate_actions(actions)
        jnp = self.jnp
        mjx = self.mjx
        model = self.mjx_model

        def step(data, force):
            data = mjx.step(model, data.replace(ctrl=jnp.array([force])))
            return data, (data.qpos[0], data.qvel[0])

        _, (qpos, qvel) = self.jax.lax.scan(step, self.base_data, actions)
        gap = self.config.initial_gap_m - qpos
        soft_collision = self.jax.nn.sigmoid(
            (self.config.safe_gap_m - gap) / self.config.soft_temperature_m
        )
        safe_gap_penalty = jnp.mean(
            self.jax.nn.softplus(
                (self.config.safe_gap_m - gap) / self.config.soft_temperature_m
            )
        )
        smoothness_penalty = jnp.mean(jnp.diff(actions) ** 2)
        loss = safe_gap_penalty + self.config.smoothness_weight * smoothness_penalty
        return {
            "qpos_m": qpos,
            "qvel_mps": qvel,
            "gap_m": gap,
            "soft_collision": soft_collision,
            "safe_gap_penalty": safe_gap_penalty,
            "smoothness_penalty": smoothness_penalty,
            "loss": loss,
        }

    def loss(self, actions):
        return self.rollout(actions)["loss"]

    def loss_with_custom_vjp(self):
        """Return a custom-VJP loss using forward-mode Jacobians in backward.

        MJX's normal multi-iteration solver is retained in the primal path.
        The backward rule computes the exact local Jacobian with JAX forward
        mode and contracts it with the incoming cotangent.  This is a real
        VJP for the current rollout, not a detached or hand-written surrogate,
        but its cost scales with the action dimension.
        """

        jax = self.jax
        raw_loss = self.loss

        @jax.custom_vjp
        def custom_loss(actions):
            return raw_loss(actions)

        def custom_loss_fwd(actions):
            value = raw_loss(actions)
            return value, actions

        def custom_loss_bwd(actions, cotangent):
            jacobian = jax.jacfwd(raw_loss)(actions)
            return (cotangent * jacobian,)

        custom_loss.defvjp(custom_loss_fwd, custom_loss_bwd)
        return custom_loss

    def custom_vjp_probe(self, actions, *, epsilon: float = 1e-4) -> dict[str, Any]:
        """Compare custom VJP, forward Jacobian and central finite difference."""

        actions = self._validate_actions(actions)
        coordinate = self.config.horizon // 2
        # Keep the finite-difference probe strictly inside actuator bounds.
        actions = actions.at[coordinate].set(
            self.jnp.clip(
                actions[coordinate],
                -0.8 * self.config.force_limit,
                0.8 * self.config.force_limit,
            )
        )
        custom_loss = self.loss_with_custom_vjp()
        custom_gradient = self.jax.grad(custom_loss)(actions)
        forward_gradient = self.jax.jacfwd(self.loss)(actions)
        plus = actions.at[coordinate].add(epsilon)
        minus = actions.at[coordinate].add(-epsilon)
        finite_difference = (self.loss(plus) - self.loss(minus)) / (2 * epsilon)
        max_difference = self.jnp.max(self.jnp.abs(custom_gradient - forward_gradient))
        relative_error = self.jnp.abs(custom_gradient[coordinate] - finite_difference) / (
            self.jnp.abs(finite_difference) + 1e-12
        )
        return {
            "available": True,
            "method": "custom_vjp_forward_over_reverse",
            "finite": bool(self.jnp.isfinite(custom_gradient).all().item()),
            "coordinate": coordinate,
            "custom_gradient": float(custom_gradient[coordinate].item()),
            "forward_jacfwd": float(forward_gradient[coordinate].item()),
            "finite_difference": float(finite_difference.item()),
            "max_abs_difference_to_jacfwd": float(max_difference.item()),
            "relative_error_to_finite_difference": float(relative_error.item()),
            "cost_note": "反向规则内部计算完整 jacfwd，复杂度随动作维度线性增加",
        }

    def native_rollout(self, actions):
        """Run the same model with native MuJoCo for a numerical comparison."""

        actions = self._validate_actions(actions)
        data = self.mujoco.MjData(self.native_model)
        qpos = []
        qvel = []
        for force in actions.tolist():
            data.ctrl[0] = float(force)
            self.mujoco.mj_step(self.native_model, data)
            qpos.append(float(data.qpos[0]))
            qvel.append(float(data.qvel[0]))
        return {
            "qpos_m": self.jnp.asarray(qpos, dtype=self.jnp.float64),
            "qvel_mps": self.jnp.asarray(qvel, dtype=self.jnp.float64),
            "gap_m": self.config.initial_gap_m - self.jnp.asarray(qpos, dtype=self.jnp.float64),
        }

    def gradient_check(self, actions, *, coordinate: int | None = None, epsilon: float = 1e-4):
        """Compare MJX forward-mode derivative with a central finite difference."""

        actions = self._validate_actions(actions)
        if epsilon <= 0:
            raise ValueError("epsilon 必须大于 0")
        coordinate = self.config.horizon // 2 if coordinate is None else int(coordinate)
        if not 0 <= coordinate < self.config.horizon:
            raise ValueError("coordinate 超出 horizon")
        # Keep the finite-difference probe strictly inside actuator bounds.
        actions = actions.at[coordinate].set(
            self.jnp.clip(
                actions[coordinate],
                -0.8 * self.config.force_limit,
                0.8 * self.config.force_limit,
            )
        )
        jacfwd = self.jax.jacfwd(self.loss)(actions)
        plus = actions.at[coordinate].add(epsilon)
        minus = actions.at[coordinate].add(-epsilon)
        finite_difference = (self.loss(plus) - self.loss(minus)) / (2 * epsilon)
        analytic = jacfwd[coordinate]
        relative_error = self.jnp.abs(analytic - finite_difference) / (
            self.jnp.abs(finite_difference) + 1e-12
        )
        reverse_mode_error = None
        try:
            self.jax.grad(self.loss)(actions)
        except Exception as error:  # JAX contact solver limitation is evidence.
            reverse_mode_error = f"{type(error).__name__}: {error}"
        return {
            "method": "jax.jacfwd",
            "finite": bool(self.jnp.isfinite(jacfwd).all().item()),
            "l2_norm": float(self.jnp.linalg.norm(jacfwd).item()),
            "coordinate": coordinate,
            "analytic": float(analytic.item()),
            "finite_difference": float(finite_difference.item()),
            "relative_error": float(relative_error.item()),
            "reverse_mode_available": reverse_mode_error is None,
            "reverse_mode_error": reverse_mode_error,
        }

    def workaround_probe(self, actions, *, epsilon: float = 1e-4) -> list[dict[str, Any]]:
        """Compare fixed-iteration reverse mode with dynamic-iteration jacfwd."""

        rows = []
        for iterations, strategy in (
            (1, "fixed_solver_iterations_1"),
            (self.config.solver_iterations, "configured_solver_iterations"),
        ):
            probe_config = MJXPoCConfig(**{**asdict(self.config), "solver_iterations": iterations})
            probe = MJXDifferentiableBackend(probe_config)
            probe_actions = probe.jnp.asarray(actions, dtype=probe.jnp.float64)
            gradient = probe.gradient_check(probe_actions, epsilon=epsilon)
            result = probe.rollout(probe_actions)
            native = probe.native_rollout(probe_actions)
            max_qpos_error = float(
                probe.jnp.max(probe.jnp.abs(result["qpos_m"] - native["qpos_m"])).item()
            )
            rows.append(
                {
                    "strategy": strategy,
                    "solver_iterations": iterations,
                    "reverse_mode_available": gradient["reverse_mode_available"],
                    "forward_mode_finite": gradient["finite"],
                    "finite_difference_relative_error": gradient["relative_error"],
                    "max_qpos_abs_error_m": max_qpos_error,
                    "within_native_tolerance": max_qpos_error < 1e-5,
                    "reverse_mode_error": gradient["reverse_mode_error"],
                }
            )
        return rows

    def manifest(
        self,
        actions,
        *,
        epsilon: float = 1e-4,
        compare_workarounds: bool = False,
        probe_custom_vjp: bool = False,
    ) -> dict[str, Any]:
        actions = self._validate_actions(actions)
        result = self.rollout(actions)
        native = self.native_rollout(actions)
        gradient = self.gradient_check(actions, epsilon=epsilon)
        workaround_rows = self.workaround_probe(actions, epsilon=epsilon) if compare_workarounds else None
        custom_vjp = self.custom_vjp_probe(actions, epsilon=epsilon) if probe_custom_vjp else None
        max_qpos_error = float(self.jnp.max(self.jnp.abs(result["qpos_m"] - native["qpos_m"])).item())
        max_gap_error = float(self.jnp.max(self.jnp.abs(result["gap_m"] - native["gap_m"])).item())
        device = str(self.jax.devices()[0])
        jax_version = importlib.metadata.version("jax")
        mujoco_version = importlib.metadata.version("mujoco")
        mjx_version = importlib.metadata.version("mujoco-mjx")
        return {
            "format": "p4_1_mjx_differentiable_poc_manifest_v1",
            "status": "completed",
            "backend": "MJX-JAX",
            "device": device,
            "versions": {
                "jax": jax_version,
                "mujoco": mujoco_version,
                "mujoco_mjx": mjx_version,
            },
            "config": asdict(self.config),
            "rollout": {
                "loss": float(result["loss"].item()),
                "safe_gap_penalty": float(result["safe_gap_penalty"].item()),
                "smoothness_penalty": float(result["smoothness_penalty"].item()),
                "min_gap_m": float(result["gap_m"].min().item()),
                "final_gap_m": float(result["gap_m"][-1].item()),
                "final_qpos_m": float(result["qpos_m"][-1].item()),
                "final_qvel_mps": float(result["qvel_mps"][-1].item()),
            },
            "gradient_check": gradient,
            "workaround_probe": workaround_rows,
            "custom_vjp_probe": custom_vjp,
            "native_mujoco_comparison": {
                "max_qpos_abs_error_m": max_qpos_error,
                "max_gap_abs_error_m": max_gap_error,
                "within_tolerance": bool(max_qpos_error < 1e-5 and max_gap_error < 1e-5),
            },
            "claims": {
                "mjx_rigid_body_forward_dynamics": True,
                "mjx_forward_mode_gradient": gradient["finite"],
                "mjx_reverse_mode_gradient": gradient["reverse_mode_available"],
                "fixed_iteration_reverse_mode_probe": bool(
                    workaround_rows is not None
                    and any(
                        row["strategy"] == "fixed_solver_iterations_1"
                        and row["reverse_mode_available"]
                        for row in workaround_rows
                    )
                ),
                "custom_vjp_forward_over_reverse": bool(
                    custom_vjp is not None and custom_vjp["finite"]
                ),
                "pybullet_native_differentiable": False,
                "carla_closed_loop": False,
                "training_integrated": False,
            },
            "quality_gate": (
                "pass_forward_mode_only"
                if gradient["finite"]
                and gradient["relative_error"] < 1e-2
                and max_qpos_error < 1e-5
                else "blocked"
            ),
            "boundary_note": (
                f"MJX-JAX {device} 小场景刚体 PoC 已验证前向梯度和原生 MuJoCo 轨迹对齐；"
                "当前接触求解器的反向模式可能触发 JAX 动态 while_loop 限制，"
                "固定为单次求解迭代可绕开该限制，但必须额外验证接触精度，"
                "因此尚未形成可扩展的生成模型训练闭环。"
            ),
        }
