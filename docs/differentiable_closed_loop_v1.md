# 可微闭环与 PyBullet 校验 V1

## 当前实现

`core/differentiable_closed_loop.py` 将场景控制抽象为 Torch 运动学闭环：输入 `[batch, horizon]` 加速度序列，递推 ego 速度、相对速度和间距，输出可微的碰撞概率代理损失。对 `loss.backward()` 的梯度回归已通过。

PyBullet 不提供对原生刚体积分步的自动微分，因此本项目将两条证据严格拆开：

1. **可微路径**：Torch 运动学代理，证据类型 `differentiable_kinematic_surrogate`。
2. **离散校验路径**：可选 `PyBulletValidationAdapter` 在 `DIRECT` 模式执行重力/平面步进，证据类型 `optional_pybullet_discrete_check`。

## 服务器验证

- 服务器 `Carla666-0916` 已安装 `pybullet 3.2.7`，安装位置不进入 Git。
- 服务器运行 `tests.test_runtime_adapters`：`4/4` 通过，包含 Torch 梯度检查和 PyBullet DIRECT 校验。
- 本结果不等价于 PyBullet 可微物理训练，也不产生 CARLA 风险或真实道路结论。

## 下一步边界

如果需要真正的可微刚体动力学，应另选支持自动微分的物理库或对 PyBullet 进行可验证的代理建模；在此之前，材料中只能写“可微运动学代理 + PyBullet 离散校验”。
