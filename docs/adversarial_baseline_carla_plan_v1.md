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

五个场景均发生碰撞。当前奖励中的 `collision_event_reward=0.5` 和 `event_reward` 上限在四个候选上全部饱和，因此四个候选虽然风险分均低于共享基线，最终 reward 仍全部为正。该现象不影响执行链路、版本、传感器、路线和风险回填验收，但说明单 pair reward 不能直接解释为策略优劣；扩大批次前应先补充相对基线奖励诊断，并保留原始风险、事件和碰撞数据以便离线重算。

轻量证据已回收至 `F:\Carla\project-transfer\server-results\20260821_134011_20260821_134314`，其中包括运行明细、奖励分解、五份 metadata 快照和静态计划。原始 RGB 帧继续保存在服务器运行目录，不回收入 Git。

## 运行边界

静态计划仍只有 `60/60` 配置校验证据；实机证据目前只覆盖首个 pair 的 `5/5`。不能把首个 pair 的结果写成完整 60 次实机通过，也不能据此宣称某种非学习策略普遍优于其他策略或 RL 策略有效。

正式执行继续遵守服务器优先规则，服务器和本机都必须使用 CARLA `0.9.16` 与项目环境 `Carla666-0916`。执行器支持按 `pair_id` 或 pair 数量运行、跳过已经严格通过的结果、基线失败中止、候选失败后的服务健康判断和增量落盘恢复。

## 入口

- 配置：`configs/adversarial_baseline_carla_plan_v1.json`
- Schema：`schemas/adversarial_baseline_carla_plan_v1.schema.json`
- 准备工具：`tools/prepare_adversarial_baseline_carla_plan.py`
- 执行与聚合：`tools/run_adversarial_baseline_carla_plan.py`
- 服务器入口：`tools/server_adversarial_baseline_carla_smoke_v1.cmd`
- 运行配置基线：`configs/adversarial_loop_v1.json`

## 下一步

先补充相对共享基线的 reward 诊断口径，明确碰撞已发生时的奖励语义和连续碰撞事件去重方式；随后复用同一服务器计划跳过已完成的 5 次，执行剩余 11 个 pair、55 次 CARLA 对照，并按 12 个分层汇总策略结果。
