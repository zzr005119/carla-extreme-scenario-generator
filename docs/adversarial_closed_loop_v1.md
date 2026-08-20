# 对抗性闭环编排 V1

本模块把阶段四已经冻结的代理契约接入现有 Scene 04 运行器，形成可重复执行的“基线场景 → 连续动作候选 → CARLA 严格执行 → `heuristic_v2` 风险回填”链路。它用于验证闭环接口，不代表 RL 策略已经训练完成。

## Episode 结构

1. 对输入场景执行一次严格基线运行。
2. 将基线实测风险作为代理初始反馈。
3. 固定动作策略输出 15 维归一化增量，生成一个候选场景。
4. 候选通过场景 Schema、语义校验和 Scene 04 配置校验后执行 CARLA。
5. 严格验收结果写回代理，生成 reward 和下一步观测；在未触发终止或截断条件时继续生成下一候选。
6. 达到配置的最大步数、重复/失败或其他安全终止条件后，保存终止状态和最终场景记录。

基线和候选都必须满足 CARLA `0.9.16` 客户端/服务端一致、RGB 不少于 100 帧、传感器写盘完成、服务健康、`waypoint_follower` 路线验收通过。碰撞运行可按首次碰撞前的路线窗口验收，避免碰撞后的物理偏移被误判为控制器失效。

## 运行模式

- `validate`：只生成基线与候选配置并调用 Scene 04 `--validate-only`，不连接 CARLA。
- `mock`：用确定性假结果回归 episode 状态机，只能作为接口测试。
- `carla`：按配置执行基线和连续候选的真实 CARLA 运行，并产生逐步严格验收证据。

服务器冒烟入口为 `tools/server_adversarial_loop_smoke_v1.cmd`；多步入口为 `tools/server_adversarial_loop_multistep_v1.cmd`。运行任务继续遵循服务器优先、CARLA 0.9.16、项目环境 `Carla666-0916` 和 GPU 1 项目锁规则。

## 已完成真实冒烟

2026-08-19 使用 `cvae_medium_20260813_0103` 和 Traffic Manager seed `20260823` 完成一次基线 + 一次候选运行。基线 `heuristic_v2=26.536/medium`，候选 `28.939/medium`，风险增量 `+2.403`；两次均无碰撞，RGB 各保存 `100` 帧，路线双车同时在途率为 `1.0`，最大路线偏差分别不超过 `0.997 m` 和 `1.000 m`，CARLA 客户端/服务端均为 `0.9.16`，严格验收 `2/2` 通过。

证据目录：`F:\Carla\project-transfer\server-results\adversarial_loop_smoke_v1_20260819_123339`。该样本和单步固定动作只用于验证闭环执行与风险回填，不支持“代理已经学会发现薄弱环节”的结论。

2026-08-20 使用 `cvae_medium_20260813_0103` 和 Traffic Manager seed `20260823` 完成多步真实冒烟。配置 `configs/adversarial_loop_multistep_v1.json` 的 `max_agent_steps=3`，服务器任务 `adversarial-loop-multistep-v1_20260820_132752` 执行一次基线和 3 个连续候选，严格验收 `4/4` 通过。风险序列为 `27.774/medium → 28.942/medium → 30.375/medium → 31.651/medium`，基线到最终候选增量 `+3.877`；3 个 transition 风险增量奖励项为 `0.01168`、`0.01433`、`0.01276`。四次运行均无碰撞，RGB 各保存 `100` 帧，路线、服务健康和客户端/服务端 `0.9.16` 版本一致性验收均通过。

证据目录：`F:\Carla\project-transfer\server-results\adversarial_loop_multistep_v1_20260820_132752`，episode 汇总位于 `episodes/cvae_medium_20260813_0103_20260820_132752/episode_summary.json`。本轮连续候选仍使用同一个固定 15 维动作，因此只证明反馈进入下一观测、样本 ID 递进和风险回填链路可用，不支持策略学习、RL 有效性或跨场景泛化结论。

## 下一步

- 增加 candidate 严格验收失败后的中止与恢复测试，确认失败原因、奖励和终止状态完整落盘。
- 增加重复场景触发截断测试，再评估是否引入 `gymnasium` 与 Stable-Baselines3。
