"""Independent two-dynamic-body MJX-JAX contact probe."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import importlib.util
import os
from typing import Any


@dataclass(frozen=True)
class MultiBodyProbeConfig:
    horizon: int = 128
    timestep: float = 0.02
    initial_gap_m: float = 4.0
    body_half_length_m: float = 1.0
    safe_gap_m: float = 2.0
    force_limit: float = 5.0
    damping: float = 0.1
    soft_temperature_m: float = 0.25
    smoothness_weight: float = 0.01
    solver_iterations: int = 4
    solver_ls_iterations: int = 4

    def validate(self) -> None:
        if self.horizon < 2:
            raise ValueError("horizon 必须至少为 2")
        if self.timestep <= 0 or self.initial_gap_m <= 0:
            raise ValueError("timestep 和 initial_gap_m 必须大于 0")
        if self.body_half_length_m <= 0 or self.safe_gap_m <= 0:
            raise ValueError("body_half_length_m 和 safe_gap_m 必须大于 0")
        if self.force_limit <= 0 or self.damping < 0 or self.soft_temperature_m <= 0:
            raise ValueError("force_limit/damping/soft_temperature_m 参数非法")
        if self.smoothness_weight < 0:
            raise ValueError("smoothness_weight 不能小于 0")
        if self.solver_iterations < 1 or self.solver_ls_iterations < 1:
            raise ValueError("solver_iterations 和 solver_ls_iterations 必须至少为 1")

    @property
    def lead_center_x_m(self) -> float:
        return self.initial_gap_m + 2.0 * self.body_half_length_m


def available() -> bool:
    return importlib.util.find_spec("jax") is not None and importlib.util.find_spec("mujoco") is not None


def _imports():
    if not available():
        raise RuntimeError("缺少可选依赖，请安装 requirements-mjx-poc.txt")
    import jax

    platform = os.environ.get("MJX_JAX_PLATFORM", "cpu").strip() or "cpu"
    jax.config.update("jax_platforms", platform)
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    import mujoco
    from mujoco import mjx

    return jax, jnp, mujoco, mjx


def build_mjcf(config: MultiBodyProbeConfig) -> str:
    config.validate()
    return f"""<mujoco>
  <option timestep="{config.timestep}" gravity="0 0 0" integrator="implicitfast" iterations="{config.solver_iterations}" ls_iterations="{config.solver_ls_iterations}"/>
  <worldbody>
    <body name="ego" pos="0 0 1">
      <joint name="ego_slide" type="slide" axis="1 0 0" damping="{config.damping}"/>
      <geom name="ego_geom" type="box" size="{config.body_half_length_m} 0.5 0.5" mass="1"/>
    </body>
    <body name="lead" pos="{config.lead_center_x_m} 0 1">
      <joint name="lead_slide" type="slide" axis="1 0 0" damping="{config.damping}"/>
      <geom name="lead_geom" type="box" size="{config.body_half_length_m} 0.5 0.5" mass="1"/>
    </body>
  </worldbody>
  <actuator>
    <motor joint="ego_slide" gear="1"/>
    <motor joint="lead_slide" gear="1"/>
  </actuator>
</mujoco>"""


def surface_gap_m(config: MultiBodyProbeConfig, qpos):
    """Return the lead/ego surface gap from relative joint positions."""

    return config.initial_gap_m + qpos[..., 1] - qpos[..., 0]


class MJXMultiBodyProbe:
    def __init__(self, config: MultiBodyProbeConfig | None = None):
        self.config = config or MultiBodyProbeConfig()
        self.config.validate()
        self.jax, self.jnp, self.mujoco, self.mjx = _imports()
        self.native_model = self.mujoco.MjModel.from_xml_string(build_mjcf(self.config))
        self.mjx_model = self.mjx.put_model(self.native_model)
        self.base_data = self.mjx.make_data(self.mjx_model)

    def _validate_actions(self, actions):
        actions = self.jnp.asarray(actions, dtype=self.jnp.float64)
        expected = (self.config.horizon, 2)
        if actions.ndim != 2 or tuple(actions.shape) != expected:
            raise ValueError(f"actions 形状必须为 {expected}")
        return self.jnp.clip(actions, -self.config.force_limit, self.config.force_limit)

    def rollout(self, actions) -> dict[str, Any]:
        actions = self._validate_actions(actions)
        jnp = self.jnp
        model = self.mjx_model

        def step(data, control):
            data = self.mjx.step(model, data.replace(ctrl=control))
            return data, (data.qpos[:2], data.qvel[:2])

        _, (qpos, qvel) = self.jax.lax.scan(step, self.base_data, actions)
        gap = surface_gap_m(self.config, qpos)
        safe_penalty = jnp.mean(
            self.jax.nn.softplus(
                (self.config.safe_gap_m - gap) / self.config.soft_temperature_m
            )
        )
        smoothness_penalty = jnp.mean(jnp.diff(actions, axis=0) ** 2)
        loss = safe_penalty + self.config.smoothness_weight * smoothness_penalty
        return {
            "qpos_m": qpos,
            "qvel_mps": qvel,
            "gap_m": gap,
            "safe_gap_penalty": safe_penalty,
            "smoothness_penalty": smoothness_penalty,
            "loss": loss,
        }

    def loss(self, actions):
        return self.rollout(actions)["loss"]

    def loss_with_custom_vjp(self):
        jax = self.jax
        raw_loss = self.loss

        @jax.custom_vjp
        def custom_loss(actions):
            return raw_loss(actions)

        def custom_loss_fwd(actions):
            return raw_loss(actions), actions

        def custom_loss_bwd(actions, cotangent):
            jacobian = jax.jacfwd(raw_loss)(actions)
            return (cotangent * jacobian,)

        custom_loss.defvjp(custom_loss_fwd, custom_loss_bwd)
        return custom_loss

    def native_rollout(self, actions):
        actions = self._validate_actions(actions)
        data = self.mujoco.MjData(self.native_model)
        qpos, qvel = [], []
        for control in actions.tolist():
            data.ctrl[:] = control
            self.mujoco.mj_step(self.native_model, data)
            qpos.append([float(value) for value in data.qpos[:2]])
            qvel.append([float(value) for value in data.qvel[:2]])
        qpos = self.jnp.asarray(qpos, dtype=self.jnp.float64)
        qvel = self.jnp.asarray(qvel, dtype=self.jnp.float64)
        return {
            "qpos_m": qpos,
            "qvel_mps": qvel,
            "gap_m": surface_gap_m(self.config, qpos),
        }

    def gradient_check(self, actions, *, coordinate: tuple[int, int] | None = None, epsilon: float = 1e-4):
        actions = self._validate_actions(actions)
        if epsilon <= 0:
            raise ValueError("epsilon 必须大于 0")
        coordinate = (self.config.horizon // 2, 0) if coordinate is None else tuple(coordinate)
        if not (0 <= coordinate[0] < self.config.horizon and 0 <= coordinate[1] < 2):
            raise ValueError("coordinate 超出动作形状")
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
        except Exception as error:
            reverse_mode_error = f"{type(error).__name__}: {error}"
        return {
            "method": "jax.jacfwd",
            "finite": bool(self.jnp.isfinite(jacfwd).all().item()),
            "l2_norm": float(self.jnp.linalg.norm(jacfwd).item()),
            "coordinate": list(coordinate),
            "analytic": float(analytic.item()),
            "finite_difference": float(finite_difference.item()),
            "relative_error": float(relative_error.item()),
            "reverse_mode_available": reverse_mode_error is None,
            "reverse_mode_error": reverse_mode_error,
        }

    def custom_vjp_probe(self, actions, *, epsilon: float = 1e-4):
        actions = self._validate_actions(actions)
        coordinate = (self.config.horizon // 2, 0)
        actions = actions.at[coordinate].set(
            self.jnp.clip(
                actions[coordinate],
                -0.8 * self.config.force_limit,
                0.8 * self.config.force_limit,
            )
        )
        custom_gradient = self.jax.grad(self.loss_with_custom_vjp())(actions)
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
            "coordinate": list(coordinate),
            "custom_gradient": float(custom_gradient[coordinate].item()),
            "forward_jacfwd": float(forward_gradient[coordinate].item()),
            "finite_difference": float(finite_difference.item()),
            "max_abs_difference_to_jacfwd": float(max_difference.item()),
            "relative_error_to_finite_difference": float(relative_error.item()),
        }

    def workaround_probe(self, actions, *, epsilon: float = 1e-4):
        rows = []
        for iterations, strategy in ((1, "fixed_solver_iterations_1"), (self.config.solver_iterations, "configured_solver_iterations")):
            probe_config = MultiBodyProbeConfig(**{**asdict(self.config), "solver_iterations": iterations})
            probe = MJXMultiBodyProbe(probe_config)
            probe_actions = probe.jnp.asarray(actions, dtype=probe.jnp.float64)
            gradient = probe.gradient_check(probe_actions, epsilon=epsilon)
            result = probe.rollout(probe_actions)
            native = probe.native_rollout(probe_actions)
            max_qpos_error = float(probe.jnp.max(probe.jnp.abs(result["qpos_m"] - native["qpos_m"])).item())
            rows.append({
                "strategy": strategy,
                "solver_iterations": iterations,
                "reverse_mode_available": gradient["reverse_mode_available"],
                "forward_mode_finite": gradient["finite"],
                "finite_difference_relative_error": gradient["relative_error"],
                "max_qpos_abs_error_m": max_qpos_error,
                "within_native_tolerance": max_qpos_error < 1e-5,
                "reverse_mode_error": gradient["reverse_mode_error"],
            })
        return rows

    def manifest(self, actions, *, epsilon: float = 1e-4, compare_workarounds: bool = False, probe_custom_vjp: bool = False):
        actions = self._validate_actions(actions)
        result = self.rollout(actions)
        native = self.native_rollout(actions)
        gradient = self.gradient_check(actions, epsilon=epsilon)
        workaround_rows = self.workaround_probe(actions, epsilon=epsilon) if compare_workarounds else None
        custom_vjp = self.custom_vjp_probe(actions, epsilon=epsilon) if probe_custom_vjp else None
        max_qpos_error = float(self.jnp.max(self.jnp.abs(result["qpos_m"] - native["qpos_m"])).item())
        max_gap_error = float(self.jnp.max(self.jnp.abs(result["gap_m"] - native["gap_m"])).item())
        device = str(self.jax.devices()[0])
        return {
            "format": "mjx_multibody_contact_probe_manifest_v1",
            "status": "completed",
            "backend": "MJX-JAX",
            "device": device,
            "versions": {
                "jax": importlib.metadata.version("jax"),
                "mujoco": importlib.metadata.version("mujoco"),
                "mujoco_mjx": importlib.metadata.version("mujoco-mjx"),
            },
            "config": asdict(self.config),
            "rollout": {
                "loss": float(result["loss"].item()),
                "min_gap_m": float(result["gap_m"].min().item()),
                "final_gap_m": float(result["gap_m"][-1].item()),
                "final_qpos_m": [float(value) for value in result["qpos_m"][-1].tolist()],
                "final_qvel_mps": [float(value) for value in result["qvel_mps"][-1].tolist()],
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
                "two_dynamic_bodies": True,
                "contact_probe": bool(float(result["gap_m"].min().item()) <= 0.0),
                "mjx_forward_mode_gradient": gradient["finite"],
                "mjx_reverse_mode_gradient": gradient["reverse_mode_available"],
                "custom_vjp_forward_over_reverse": bool(custom_vjp is not None and custom_vjp["finite"]),
                "training_integrated": False,
            },
            "quality_gate": (
                "pass_contact_forward_mode"
                if gradient["finite"] and gradient["relative_error"] < 1e-2 and max_qpos_error < 1e-5
                else "blocked"
            ),
            "boundary_note": (
                f"MJX-JAX {device} 双动态刚体接触压力测试已完成；结果仅证明小规模接触前向与梯度校验，"
                "不代表已完成车辆动力学、生成模型训练或 CARLA 闭环。"
            ),
        }
