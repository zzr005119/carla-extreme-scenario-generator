# 对抗性非学习基线 CARLA 对照计划 V1

_完成日期：2026年8月21日；范围：阶段四真实 CARLA 对照计划与首个 pair 实机冒烟_

## 设计

计划从场景库抽取一个完整的 `12` 分层周期，即 LHS/GMM/CVAE × low/medium/high/critical 各一个独立场景。每个场景只准备一次共享基线，并分别准备 fixed、random、LHS、rule-guided LHS 四个候选，因此总运行数为：

`12 × (1 baseline + 4 candidates) = 60 runs`

基线与四个候选使用相同的 Traffic Manager 种子、路线控制配置和传感器验收要求。候选保留首轮动作、全部失败尝试、最终选中动作和约束重试次数，避免只比较成功样本而丢失生成成本。

## 静态结果

| 项目 | 结果 |
|---|---:|
| 独立基线场景 | 12 |
| 生成器 × 目标风险分层 | 12/12 |
| 共享基线运行 | 12 |
| 四策略候选运行 | 48 |
| 总计划运行 | 60 |
| Scene 04 `--validate-only` | 60/60 |
| 重试预算耗尽 | 0 |

本轮 12 条候选子集中，fixed、LHS 和 rule-guided LHS 首轮均为 `12/12` 有效；random 首轮为 `10/12`，独立重试流额外使用 2 次动作后补齐为 `12/12`。该差异只描述约束可执行性，不代表 CARLA 风险效果。

最终计划目录：`F:\Carla\output-0.9.16\adversarial_baseline_carla_plan_v1\20260821_132000`。目录包含 `run_plan.json`、`run_plan.csv`、`sample_manifest.jsonl`、60 个场景记录、60 个 CARLA 配置和 60 份静态校验日志。来源提交为 `ab78246745103bcb06178009ddea2d16336e2845`，生成时工作树干净。

## 首个 pair 实机冒烟

服务器任务 `adversarial-baseline-carla-smoke-v1_20260821_134010` 基于提交 `3d42af59e56a07463b6cdb4b9e4dc23ccb3ad73f` 重新生成 Linux 路径计划，并执行 `abcv1_pair_01` 的 1 个共享基线和 4 个策略候选。5 次运行全部通过严格验收：CARLA 客户端/服务端均为 `0.9.16`，风险方法均为 `heuristic_v2`，RGB 均为 `100` 帧，传感器与服务状态均为 `completed/healthy`，路线双车在途率均为 `1.0`，最大路线偏差不超过 `0.999 m`。

| 运行 | 风险分 | 相对基线增量 | Reward | 碰撞事件 |
|---|---:|---:|---:|---:|
| 共享基线 | 94.081 | - | - | 42 |
| fixed | 87.612 | -6.469 | 0.635310 | 309 |
| random | 85.842 | -8.239 | 0.617610 | 10 |
| LHS | 84.703 | -9.378 | 0.606220 | 9 |
| rule-guided LHS | 88.943 | -5.138 | 0.648620 | 318 |

五个场景均发生碰撞。旧奖励中的 `collision_event_reward=0.5` 和 `event_reward` 上限在四个候选上全部饱和，因此四个候选虽然风险分均低于共享基线，旧 reward 仍全部为正。该问题会给训练提供方向错误的信用分配，使策略倾向于维持基线已有碰撞，并使不同基线危险程度下的 reward 不可直接比较；它不影响已记录的风险分、版本、传感器、路线和严格验收结论。

reward V2 已改为 `relative_capped_delta`：碰撞按相对基线的 0/1 状态差计算，安全事件只统计按类型与原因去重的 `ego_safety_brake`，预设触发事件和连续碰撞回调不进入附加奖励。使用同一批真实 metadata 离线重算后，四个候选 reward 从 `0.635310/0.617610/0.606220/0.648620` 修正为 `-0.064690/-0.082390/-0.093780/-0.051380`，4/4 与负风险增量方向一致。

轻量证据已回收至 `F:\Carla\project-transfer\server-results\20260821_134011_20260821_134314`，其中包括运行明细、奖励分解、五份 metadata 快照和静态计划。原始 RGB 帧继续保存在服务器运行目录，不回收入 Git。

## 运行边界

静态计划仍只有 `60/60` 配置校验证据；实机证据目前只覆盖首个 pair 的 `5/5`。不能把首个 pair 的结果写成完整 60 次实机通过，也不能据此宣称某种非学习策略普遍优于其他策略或 RL 策略有效。

正式执行继续遵守服务器优先规则，服务器和本机都必须使用 CARLA `0.9.16` 与项目环境 `Carla666-0916`。执行器支持按 `pair_id` 或 pair 数量运行、跳过已经严格通过的结果、基线失败中止、候选失败后的服务健康判断和增量落盘恢复。

## 完整实机对照

服务器任务 `adversarial-baseline-carla-full-v1_20260821_152923` 基于提交 `a65254dc667c17a8050d17caae72a931ae733700` 执行完整 `12` 个 pair。首个 5 次门槛通过后继续剩余 55 次，最终 `60/60` 严格验收通过；客户端/服务端均为 `0.9.16`，风险方法均为 `heuristic_v2`，RGB 均为 `100` 帧，传感器、路线和服务健康全部通过。

| 策略 | 平均风险增量 | 中位风险增量 | 风险升高 | 平均 reward | 新增碰撞 | 消除碰撞 | 四策略最高风险 |
|---|---:|---:|---:|---:|---:|---:|---:|
| fixed | -2.817 | +0.525 | 9/12 | -0.0823 | 0 | 1 | 1/12 |
| random | -6.177 | -0.656 | 4/12 | -0.0909 | 1 | 1 | 1/12 |
| LHS | -3.152 | -0.821 | 5/12 | -0.0857 | 0 | 1 | 2/12 |
| rule-guided LHS | -1.617 | +2.045 | 10/12 | -0.0412 | 1 | 1 | 8/12 |

共享基线平均风险为 `47.232`，`3/12` 个基线发生碰撞。rule-guided LHS 在本计划中风险升高和四策略最高风险次数最多，适合作为后续 RL 的主要非学习对照；但每个生成器×目标风险分层只有一个 pair，均值也明显受少数大幅下降样本影响，因此不宣称其具有普遍优势。轻量结果与成对分析位于 `F:\Carla\project-transfer\server-results\20260821_152924_20260821_155826\execution`。

## 入口

- 配置：`configs/adversarial_baseline_carla_plan_v1.json`
- Schema：`schemas/adversarial_baseline_carla_plan_v1.schema.json`
- 准备工具：`tools/prepare_adversarial_baseline_carla_plan.py`
- 执行与聚合：`tools/run_adversarial_baseline_carla_plan.py`
- Reward 重算：`tools/recalculate_adversarial_baseline_rewards.py`
- 成对分析：`tools/analyze_adversarial_baseline_carla_results.py`
- 服务器入口：`tools/server_adversarial_baseline_carla_smoke_v1.cmd`
- 完整服务器入口：`tools/server_adversarial_baseline_carla_full_v1.cmd`
- 运行配置基线：`configs/adversarial_loop_v1.json`

## 下一步

reward V2、四类非学习基线结果、Stable-Baselines3 训练工程链路和 27 维冻结风险代理执行器均已冻结。下一步先进行多随机种子代理训练与等预算对照，再设计与本轮 12 分层、共享基线、严格验收和 reward V2 同口径的低预算 CARLA 独立策略评估。
