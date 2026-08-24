# 可微闭环与 PyBullet 边界 V1

## P4 技术契约

P4 不把 PyBullet 原生刚体仿真包装成“可微”。当前交付明确拆成三层：

1. **Torch 可微运动学代理**：`core.differentiable_closed_loop.differentiable_rollout` 接收 `[batch, horizon]` 加速度序列，递推主车速度、相对速度和间距，返回可反传的软损失。损失显式拆为碰撞概率软惩罚、安全间距惩罚、控制平滑惩罚和加速度越界惩罚；`compose_p4_training_loss` 暴露 `L_total = L_adv + lambda_1 * L_physics + lambda_2 * L_control` 的纯 Torch 组合点。
2. **PyBullet 离散几何回放**：`PyBulletValidationAdapter` 在 `DIRECT` 模式将一条已脱离计算图的 gap 轨迹回放到两个盒体中，报告负间距、接触步和接触点数量。它是几何/接触一致性校验，不是车辆模型，也不产生梯度。
3. **参数级硬约束质量门**：`core.physical_constraints` 继续负责记录进入后续流程前的有限值、时间窗口和运动学硬约束。硬门失败时，P4 manifest 必须为 `blocked_hard_constraint`，不能被软损失掩盖。

统一证据入口是 `build_p4_boundary_manifest`，命令入口是：

```powershell
tools\p4_differentiable_boundary.cmd --profile closing --horizon 32
```

输出 `artifacts/p4_differentiable_boundary_v1/manifest.json`，包含 Torch 损失/梯度检查、PyBullet 可用性和离散回放结果、硬约束质量门与能力声明。

## 能写入材料的结论

- 可以写“实现了可反向传播的运动学代理损失，并通过有限梯度回归”。
- 可以写“提供可选 PyBullet DIRECT 离散几何/接触校验”。
- 可以写“硬约束、软损失和离散校验分别报告，失败边界可审计”。

## 明确不能写的结论

- 不能写“PyBullet 可微刚体物理训练已完成”。
- 不能写“该损失已经接入 CVAE、Diffusion 或 RL 训练并改善 CARLA 风险”。当前 `claims.training_integrated=false`。
- 不能把两个盒体的接触回放当成 CARLA 车辆动力学、传感器、路线或风险证据。
- 不能把 Torch surrogate loss 当作 `observed_risk` 或真实碰撞概率。

## 运行与依赖边界

- Torch 是项目模型环境的必需依赖；本机测试应使用 `D:\ANACONDA\envs\Carla666-0916\python.exe`，不要用系统 Python 代替。
- PyBullet 是可选依赖，版本约束见 `requirements-pybullet-loop.txt`。缺失时 manifest 保留 `available=false` 和 `optional_pybullet_discrete_check`，不把缺失改写为通过。
- P4 入口不启动 CARLA、不启动在线 RL、不申请 GPU 训练资源；GPU 训练只有在后续明确实验计划和资源检查后才单独启动。

## 当前验证状态

- 本机 `Carla666-0916`：`tests.test_runtime_adapters` 为 `9/9` 通过；本机当前未安装可选 PyBullet，因此离散分支按设计跳过。
- 服务器 `Carla666-0916`：PyBullet `3.2.7` 的增强 gap 几何回放已通过；`horizon=128` 的 contact probe 报告 `negative_gap_steps=63`、`contact_count=41`、接触步 `65–75`，Torch 梯度有限且 `pybullet_native_differentiable=false`。详细记录见 `docs/p4_server_validation_v1.md`，原始 manifest 位于 `F:\Carla\project-transfer\server-results\p4_differentiable_boundary_v1`。
- 本模块不替代 CARLA 0.9.16 的真实运行验收，也不关闭完整消融实验和结题报告后置项。
