# 对抗性测试分层采样与离线基线 V1

_完成日期：2026年8月21日；范围：阶段四训练前数据采样和非学习候选基线_

## 目标

本轮解决 Gymnasium 环境每次 `reset()` 固定使用同一场景的问题，并在安装 Stable-Baselines3 前建立可复现的非学习对照。所有候选只执行 Schema、语义约束、动作范围、唯一性和参数变化检查；没有运行 CARLA，不计算候选奖励，也不评价风险提升效果。

## 分层采样

`core/adversarial_sampling.py` 从 `scenario_library_v1` 的 `117` 条独立场景中采样，默认按“生成器 × 目标风险档”轮转。一个完整周期覆盖 LHS/GMM/CVAE 与 low/medium/high/critical 的 `12` 个组合；同一分层内优先选择尚未使用的场景，再平衡天气标签、危险标签和 Traffic Manager 种子。

采样器支持生成器、目标风险档、天气标签和危险标签过滤。传入相同随机种子时，场景 ID 与 Traffic Manager 种子序列可复现。采样结果转换回 `generated_scenario` 运行契约时，`observed_risk` 被重置为 `not_simulated`；场景库历史均值只写入 `reset info.sampling.historical_observed_risk`，不能替代本 episode 的基线执行。

## 基线策略

| 策略 | 动作来源 | 用途 |
|---|---|---|
| `fixed` | 已完成实机冒烟的稀疏固定动作 | 当前编排基线 |
| `random` | 15 维独立均匀随机动作 | 无学习随机基线 |
| `lhs` | 15 维 Latin Hypercube 动作 | 动作空间覆盖基线 |
| `rule_guided_lhs` | 风险方向规则固定符号，LHS 生成幅值 | 规则与空间覆盖组合基线 |

四种策略均实现 `select_action(step_index, observation)`，可复用现有闭环编排接口；它们不是已训练策略。

## 首轮离线结果

配置 `configs/adversarial_baselines_v1.json` 使用随机种子 `20260821`，抽取 `24` 个独立场景，即两个完整的 `12` 分层周期。生成器各 `8` 条，四个目标风险档各 `6` 条，两个危险标签均覆盖 `24/24`，三个 Traffic Manager 种子各使用 `8` 次。

| 策略 | 有效候选 | 有效率 | 有效候选唯一率 | 平均归一化参数变化 |
|---|---:|---:|---:|---:|
| fixed | 24/24 | 100.0% | 100.0% | 0.0150 |
| random | 21/24 | 87.5% | 100.0% | 0.0452 |
| lhs | 21/24 | 87.5% | 100.0% | 0.0457 |
| rule_guided_lhs | 22/24 | 91.7% | 100.0% | 0.0509 |

随机、LHS 和规则引导 LHS 的无效候选均由天气参数跨越原请求标签边界导致，例如 `night` 变为 `day`、`dense_fog` 退化为 `fog` 或 `strong_wind` 条件丢失。代理正确拒绝了这些候选，未发生运行器调用。该结果说明后续真实 CARLA 对照前需要显式记录重采样次数或约束修复，不能静默丢弃失败候选。

离线结果目录：`F:\Carla\output-0.9.16\adversarial_baselines_v1\20260821_130208`。

## 接口与文件

- `core/adversarial_sampling.py`：场景库条目恢复、过滤、分层轮转和种子平衡。
- `core/adversarial_gym_env.py`：兼容返回 `(record, sampling_info)` 的采样器，并把元数据写入 `reset info`。
- `core/adversarial_loop.py`：固定、随机、LHS、规则引导 LHS 策略。
- `tools/evaluate_adversarial_baselines.py`：生成 `sample_manifest.jsonl`、`baseline_proposals.jsonl` 和 `baseline_summary.json`。
- `configs/adversarial_baselines_v1.json` 与 `schemas/adversarial_baselines_v1.schema.json`：冻结离线对照配置和 Schema。

## 验证与边界

本机项目环境 `D:\ANACONDA\envs\Carla666-0916` 已通过全仓库 `49/49` 单元测试、相关模块 `py_compile`、离线命令行执行和 `git diff --check`。这些结果证明采样、候选生成和报告链路可复现，不证明四种策略的 CARLA 风险收益，也不构成 RL 训练证据。

## 下一道验收门

1. 为随机、LHS 和规则引导 LHS 增加有上限的约束感知重采样，保留原始无效率与尝试次数。
2. 从一个 `12` 分层周期准备共享基线和四策略候选的小规模 CARLA 对照计划。
3. 服务器优先执行冒烟和严格验收；确认真实奖励、失败率与运行成本后，再处理 Stable-Baselines3 安装和 SAC/PPO 训练入口。
