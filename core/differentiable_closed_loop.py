"""P4 differentiable surrogate and discrete PyBullet boundary.

The Torch rollout is a deliberately small, differentiable kinematic proxy.  It
provides soft penalties that can be used by a future generator/controller
training loop.  PyBullet is kept on a separate, detached replay path: native
rigid-body stepping is not differentiable and must not be described as such.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util

import torch


@dataclass(frozen=True)
class DifferentiableLoopConfig:
    horizon: int = 32
    dt: float = 0.05
    initial_gap_m: float = 28.0
    lead_speed_mps: float = 8.0
    ego_speed_mps: float = 10.0
    safe_gap_m: float = 4.0
    acceleration_limit_mps2: float = 6.0
    temperature_m: float = 1.0
    collision_loss_weight: float = 1.0
    safe_gap_loss_weight: float = 0.25
    control_smoothness_loss_weight: float = 0.01
    acceleration_limit_loss_weight: float = 0.01

    def validate(self):
        if self.horizon < 1:
            raise ValueError("horizon 必须大于 0")
        if self.dt <= 0 or self.initial_gap_m <= 0:
            raise ValueError("dt 和 initial_gap_m 必须大于 0")
        if self.temperature_m <= 0:
            raise ValueError("temperature_m 必须大于 0")
        for name in (
            "collision_loss_weight",
            "safe_gap_loss_weight",
            "control_smoothness_loss_weight",
            "acceleration_limit_loss_weight",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不能小于 0")


def differentiable_rollout(actions, config=None):
    """Roll out gap/relative-speed dynamics and return differentiable metrics.

    ``actions`` is acceleration in m/s^2 with shape ``[horizon]`` or
    ``[batch, horizon]``.  The returned ``loss`` can be backpropagated to the
    action tensor and is intentionally a surrogate, not CARLA risk evidence.
    """
    config = config or DifferentiableLoopConfig()
    config.validate()
    if isinstance(actions, torch.Tensor):
        if not torch.is_floating_point(actions):
            actions = actions.float()
    else:
        actions = torch.tensor(actions, dtype=torch.float32)
    if actions.ndim == 1:
        actions = actions.unsqueeze(0)
    if actions.ndim != 2 or actions.shape[1] != config.horizon:
        raise ValueError(f"actions 形状必须为 [batch, {config.horizon}]")

    clipped = torch.clamp(actions, -config.acceleration_limit_mps2, config.acceleration_limit_mps2)
    gap = torch.full(
        (actions.shape[0],), config.initial_gap_m,
        dtype=actions.dtype,
        device=actions.device,
    )
    ego_speed = torch.full_like(gap, config.ego_speed_mps)
    lead_speed = torch.full_like(gap, config.lead_speed_mps)
    gaps = []
    ego_speeds = []
    collision_probs = []
    for index in range(config.horizon):
        acceleration = clipped[:, index]
        ego_speed = torch.relu(ego_speed + acceleration * config.dt)
        relative_speed = lead_speed - ego_speed
        gap = gap + relative_speed * config.dt
        gaps.append(gap)
        ego_speeds.append(ego_speed)
        collision_probs.append(torch.sigmoid((config.safe_gap_m - gap) / config.temperature_m))

    gap_tensor = torch.stack(gaps, dim=1)
    speed_tensor = torch.stack(ego_speeds, dim=1)
    collision_tensor = torch.stack(collision_probs, dim=1)
    collision_soft_penalty = collision_tensor.mean()
    safe_gap_penalty = (
        torch.relu(config.safe_gap_m - gap_tensor).mean()
        / max(config.safe_gap_m, 1e-6)
    )
    if config.horizon > 1:
        control_smoothness_penalty = torch.diff(actions, dim=1).pow(2).mean()
    else:
        control_smoothness_penalty = actions.new_zeros(())
    acceleration_limit_penalty = (
        torch.relu(torch.abs(actions) - config.acceleration_limit_mps2).pow(2).mean()
    )
    physics_loss = (
        config.collision_loss_weight * collision_soft_penalty
        + config.safe_gap_loss_weight * safe_gap_penalty
        + config.acceleration_limit_loss_weight * acceleration_limit_penalty
    )
    control_loss = config.control_smoothness_loss_weight * control_smoothness_penalty
    loss = physics_loss + control_loss
    return {
        "gap_m": gap_tensor,
        "ego_speed_mps": speed_tensor,
        "collision_probability_surrogate": collision_tensor,
        "loss_components": {
            "collision_soft_penalty": collision_soft_penalty,
            "safe_gap_penalty": safe_gap_penalty,
            "control_smoothness_penalty": control_smoothness_penalty,
            "acceleration_limit_penalty": acceleration_limit_penalty,
        },
        "physics_loss": physics_loss,
        "control_loss": control_loss,
        "loss": loss,
        "config": asdict(config),
        "evidence_kind": "differentiable_kinematic_surrogate",
        "pybullet_differentiable": False,
    }


def compose_p4_training_loss(rollout, adversarial_loss=0.0, *, physics_weight=1.0, control_weight=1.0):
    """Compose the documented future training contract.

    The function is intentionally a pure Torch composition point.  It does
    not train a generator, connect CARLA, or imply that the PyBullet adapter is
    part of the gradient graph:

    ``L_total = L_adv + lambda_1 * L_physics + lambda_2 * L_control``.
    """
    if physics_weight < 0 or control_weight < 0:
        raise ValueError("physics_weight 和 control_weight 不能小于 0")
    if not isinstance(adversarial_loss, torch.Tensor):
        adversarial_loss = torch.tensor(
            adversarial_loss,
            dtype=rollout["loss"].dtype,
            device=rollout["loss"].device,
        )
    else:
        adversarial_loss = adversarial_loss.to(
            dtype=rollout["loss"].dtype,
            device=rollout["loss"].device,
        )
    if adversarial_loss.ndim:
        adversarial_loss = adversarial_loss.mean()
    total_loss = (
        adversarial_loss
        + physics_weight * rollout["physics_loss"]
        + control_weight * rollout["control_loss"]
    )
    return {
        "total_loss": total_loss,
        "adversarial_loss": adversarial_loss,
        "physics_loss": rollout["physics_loss"],
        "control_loss": rollout["control_loss"],
        "physics_weight": float(physics_weight),
        "control_weight": float(control_weight),
        "evidence_kind": "composed_surrogate_training_contract",
        "training_integrated": False,
    }


class PyBulletValidationAdapter:
    """Replay one detached gap trace in a PyBullet DIRECT world.

    The two boxes are a geometry probe, not a vehicle model.  The adapter
    reports whether the replay produces contacts for negative bumper gaps and
    explicitly returns no gradient evidence.
    """

    @staticmethod
    def available():
        return importlib.util.find_spec("pybullet") is not None

    def validate(self, rollout, *, steps=None):
        if not self.available():
            return {
                "available": False,
                "validated": False,
                "reason": "缺少可选 pybullet 依赖",
                "evidence_kind": "optional_pybullet_discrete_check",
                "differentiable": False,
            }
        import pybullet as bullet

        gap_tensor = rollout.get("gap_m")
        if not isinstance(gap_tensor, torch.Tensor):
            return {
                "available": True,
                "validated": False,
                "reason": "rollout 缺少 Torch gap_m 张量",
                "evidence_kind": "optional_pybullet_discrete_check",
                "differentiable": False,
            }
        if gap_tensor.ndim == 1:
            gap_tensor = gap_tensor.unsqueeze(0)
        if gap_tensor.ndim != 2 or gap_tensor.shape[1] < 1:
            return {
                "available": True,
                "validated": False,
                "reason": "gap_m 形状必须为 [batch, horizon]",
                "evidence_kind": "optional_pybullet_discrete_check",
                "differentiable": False,
            }

        gaps = gap_tensor.detach().to(device="cpu", dtype=torch.float64)
        count = min(int(steps or gaps.shape[-1]), int(gaps.shape[-1]))
        if count < 1:
            return {
                "available": True,
                "validated": False,
                "reason": "steps 必须大于 0",
                "evidence_kind": "optional_pybullet_discrete_check",
                "differentiable": False,
            }

        client = bullet.connect(bullet.DIRECT)
        try:
            bullet.setGravity(0, 0, 0, physicsClientId=client)
            plane_shape = bullet.createCollisionShape(bullet.GEOM_PLANE, physicsClientId=client)
            bullet.createMultiBody(baseCollisionShapeIndex=plane_shape, physicsClientId=client)
            box_shape = bullet.createCollisionShape(
                bullet.GEOM_BOX,
                halfExtents=[2.0, 1.0, 0.75],
                physicsClientId=client,
            )
            ego_id = bullet.createMultiBody(
                baseMass=1,
                baseCollisionShapeIndex=box_shape,
                basePosition=[0, 0, 1.0],
                physicsClientId=client,
            )
            lead_id = bullet.createMultiBody(
                baseMass=1,
                baseCollisionShapeIndex=box_shape,
                basePosition=[4.0 + float(gaps[0, 0]), 0, 1.0],
                physicsClientId=client,
            )
            contact_steps = []
            contact_points = 0
            for index in range(count):
                gap = float(gaps[0, index])
                bullet.resetBasePositionAndOrientation(ego_id, [0, 0, 1.0], [0, 0, 0, 1], physicsClientId=client)
                bullet.resetBasePositionAndOrientation(lead_id, [4.0 + gap, 0, 1.0], [0, 0, 0, 1], physicsClientId=client)
                bullet.stepSimulation(physicsClientId=client)
                points = bullet.getContactPoints(ego_id, lead_id, physicsClientId=client)
                if points:
                    contact_steps.append(index)
                    contact_points += len(points)
            return {
                "available": True,
                "validated": True,
                "differentiable": False,
                "steps": count,
                "batch_size": int(gaps.shape[0]),
                "replayed_batch_index": 0,
                "min_gap_m": float(gaps[0, :count].min().item()),
                "negative_gap_steps": int((gaps[0, :count] < 0).sum().item()),
                "contact_steps": contact_steps,
                "contact_count": contact_points,
                "geometry_replay": True,
                "evidence_kind": "optional_pybullet_discrete_check",
                "note": "PyBullet 原生步进和动态盒体接触查询已与 Torch 轨迹解耦；不产生梯度，也不代表 CARLA 车辆物理",
            }
        except Exception as error:
            return {
                "available": True,
                "validated": False,
                "differentiable": False,
                "reason": f"PyBullet 离散回放失败: {error}",
                "evidence_kind": "optional_pybullet_discrete_check",
            }
        finally:
            bullet.disconnect(client)


def build_p4_boundary_manifest(actions, config=None, *, hard_constraint_report=None, adapter=None):
    """Build a JSON-safe P4 evidence manifest without hiding quality gates.

    ``hard_constraint_report`` is intentionally supplied by the existing
    parameter-level checker.  If it is present and invalid, the manifest is
    blocked even when the Torch surrogate has a finite loss.
    """
    config = config or DifferentiableLoopConfig()
    rollout = differentiable_rollout(actions, config)
    probe_actions = torch.zeros(
        (rollout["gap_m"].shape[0], config.horizon),
        dtype=rollout["gap_m"].dtype,
        device=rollout["gap_m"].device,
        requires_grad=True,
    )
    probe_rollout = differentiable_rollout(probe_actions, config)
    gradient = torch.autograd.grad(probe_rollout["loss"], probe_actions)[0]
    adapter = adapter or PyBulletValidationAdapter()
    discrete = adapter.validate(rollout)

    hard_evaluated = hard_constraint_report is not None
    hard_passed = None
    if hard_evaluated:
        if "invalid_count" in hard_constraint_report:
            hard_passed = hard_constraint_report.get("invalid_count", 0) == 0
        else:
            hard_passed = bool(hard_constraint_report.get("valid", False))
    quality_gate = (
        "pass"
        if hard_passed is True
        else "blocked_hard_constraint"
        if hard_passed is False
        else "hard_constraint_not_evaluated"
    )
    components = {
        name: float(value.detach().cpu().item())
        for name, value in rollout["loss_components"].items()
    }
    return {
        "format": "p4_differentiable_boundary_manifest_v1",
        "status": "completed",
        "quality_gate": quality_gate,
        "torch_surrogate": {
            "evidence_kind": rollout["evidence_kind"],
            "loss": float(rollout["loss"].detach().cpu().item()),
            "loss_components": components,
            "gradient_check": {
                "finite": bool(torch.isfinite(gradient).all().item()),
                "l2_norm": float(torch.linalg.vector_norm(gradient).detach().cpu().item()),
            },
            "batch_size": int(rollout["gap_m"].shape[0]),
            "horizon": config.horizon,
            "min_gap_m": float(rollout["gap_m"].detach().min().cpu().item()),
        },
        "pybullet_discrete_check": discrete,
        "hard_constraint_gate": {
            "evaluated": hard_evaluated,
            "passed": hard_passed,
            "evidence_kind": "parameter_level_hard_constraint",
            "note": "硬约束报告来自 core.physical_constraints；未提供报告时不替代硬约束校验",
        },
        "claims": {
            "torch_differentiable_surrogate": True,
            "pybullet_native_differentiable": False,
            "carla_closed_loop": False,
            "training_integrated": False,
            "vehicle_rigid_body_fidelity": False,
        },
        "boundary_note": "P4 当前交付是可微运动学代理损失 + PyBullet 离散几何校验 + 独立参数硬约束质量门，不是 PyBullet 可微刚体训练闭环",
    }
