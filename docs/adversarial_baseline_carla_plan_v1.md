# 对抗性非学习基线 CARLA 对照计划 V1

_完成日期：2026年8月21日；范围：阶段四真实 CARLA 对照的静态执行计划_

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

## 运行边界

本轮没有连接 CARLA 服务，也没有产生新的 `metadata.json`、风险分数、碰撞事件或策略奖励。`60/60` 仅表示配置能通过 Scene 04 静态校验，不能写成 CARLA 实机通过。

正式执行继续遵守服务器优先规则，服务器和本机都必须使用 CARLA `0.9.16` 与项目环境 `Carla666-0916`。第一个运行门只执行一个 pair，即 1 个共享基线加 4 个策略候选；严格验收通过后才评估是否执行完整 60 次。

## 入口

- 配置：`configs/adversarial_baseline_carla_plan_v1.json`
- Schema：`schemas/adversarial_baseline_carla_plan_v1.schema.json`
- 准备工具：`tools/prepare_adversarial_baseline_carla_plan.py`
- 运行配置基线：`configs/adversarial_loop_v1.json`

## 下一步

建立计划执行与结果聚合入口，在服务器优先执行第一个 pair 的 5 次 CARLA 冒烟，并回收每个候选相对共享基线的实测风险增量、奖励分解和严格验收结果。
