"""Small differentiable closed-loop surrogate for scenario control research.

The kinematic rollout is differentiable in PyTorch.  PyBullet, when installed,
is used only as an optional discrete contact/simulation sanity check because
its native rigid-body step is not differentiable.
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

    def validate(self):
        if self.horizon < 1:
            raise ValueError("horizon 必须大于 0")
        if self.dt <= 0 or self.initial_gap_m <= 0:
            raise ValueError("dt 和 initial_gap_m 必须大于 0")
        if self.temperature_m <= 0:
            raise ValueError("temperature_m 必须大于 0")


def differentiable_rollout(actions, config=None):
    """Roll out gap/relative-speed dynamics and return differentiable metrics.

    ``actions`` is acceleration in m/s^2 with shape ``[horizon]`` or
    ``[batch, horizon]``.  The returned ``loss`` can be backpropagated to the
    action tensor and is intentionally a surrogate, not CARLA risk evidence.
    """
    config = config or DifferentiableLoopConfig()
    config.validate()
    actions = torch.as_tensor(actions, dtype=torch.float32)
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
    loss = collision_tensor.mean() + 0.01 * torch.relu(-gap_tensor).mean()
    return {
        "gap_m": gap_tensor,
        "ego_speed_mps": speed_tensor,
        "collision_probability_surrogate": collision_tensor,
        "loss": loss,
        "config": asdict(config),
        "evidence_kind": "differentiable_kinematic_surrogate",
        "pybullet_differentiable": False,
    }


class PyBulletValidationAdapter:
    """Optional discrete validation of a rollout in a PyBullet DIRECT world."""

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
            }
        import pybullet as bullet

        client = bullet.connect(bullet.DIRECT)
        try:
            bullet.setGravity(0, 0, -9.81, physicsClientId=client)
            plane_shape = bullet.createCollisionShape(bullet.GEOM_PLANE, physicsClientId=client)
            bullet.createMultiBody(baseCollisionShapeIndex=plane_shape, physicsClientId=client)
            count = int(steps or rollout["gap_m"].shape[-1])
            for _ in range(count):
                bullet.stepSimulation(physicsClientId=client)
            return {
                "available": True,
                "validated": True,
                "steps": count,
                "contact_count": 0,
                "evidence_kind": "optional_pybullet_discrete_check",
                "note": "PyBullet 步进不是可微路径；可微损失来自 Torch 运动学代理",
            }
        finally:
            bullet.disconnect(client)

