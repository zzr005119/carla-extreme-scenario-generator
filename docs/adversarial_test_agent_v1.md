# 对抗性测试代理 V1 契约

阶段四第一版采用“场景间迭代”而不是单次 CARLA 仿真内实时接管车辆：代理给出下一条场景参数增量，外部运行器执行一次场景并回传结构化结果，代理再计算奖励和下一观测。这样可以复用现有 Scene 04、严格路线验收和 `heuristic_v2` 结果，同时不把 RL 框架或 CARLA API 引入核心契约。

## 输入与动作

- 当前场景仍以 `schemas/generated_scenario.schema.json` 为事实源。
- 动作是 15 维归一化增量，范围 `[-1, 1]`，按 `step_size=0.08` 映射到当前 15 维归一化参数。
- 参数变异后重新执行 Schema 与语义校验；天气标签必须继续满足原场景请求。超出动作范围的值会被裁剪并在 transition 中标记。

## 观测空间

观测是 34 维 `[0, 1]` 向量：15 维参数、12 维目标风险/天气条件 one-hot、7 维反馈（实测风险分、碰撞数、事件数、运行有效、严格验收通过、连续重复计数、步数比例）。`target_risk_level` 只作为条件输入，风险奖励使用 CARLA 实测 `observed_risk_score`。

## 奖励分解

`risk_delta` 使用相邻成功运行的实测风险分差；碰撞事件和其他事件提供有上限的附加奖励；无效候选、重复场景和运行失败分别施加惩罚。碰撞奖励用于发现 SUT 薄弱环节，不等同于事故概率或安全结论。

## 终止与截断

- Schema/语义校验失败：`terminated= true`，原因 `invalid_candidate`。
- CARLA 运行失败、严格验收失败、服务不健康，或完成结果缺少风险方法/等级/运行目录：`terminated=true`，原因 `run_failure` 或外部失败原因。
- 连续重复参数指纹达到 3 次：`truncated=true`，原因 `repeated_scene`。
- 达到最大 16 步：`truncated=true`，原因 `max_steps`。

## 当前边界

本版本没有训练 SAC/PPO，也没有声明策略已经学会发现薄弱环节。服务器项目环境已安装 Gymnasium `1.3.0`，可选环境外壳、mock/API 检查、一次真实 CARLA 环境冒烟、场景库分层采样、四类非学习离线候选对照、有限约束重试和 60 项 CARLA 静态计划均已完成；Stable-Baselines3 仍未安装。边界和证据见 `docs/adversarial_gymnasium_evaluation_v1.md`、`docs/adversarial_sampling_baselines_v1.md` 与 `docs/adversarial_baseline_carla_plan_v1.md`；下一步建立执行入口并在服务器运行单 pair 的 5 次冒烟。
