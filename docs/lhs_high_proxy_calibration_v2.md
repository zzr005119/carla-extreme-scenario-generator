# LHS/high 风险代理校准 V2

_完成日期：2026 年 8 月 23 日；分析模式：CPU-only 离线分析；实测输入：CARLA 0.9.16/GPU1_

## 证据口径

本轮在 V1 的 3 条独立样本基础上，增加 6 条未使用候选，合计 `9` 个独立场景。新增批次来自当前 LHS/high 候选池实际存在的联合支持域分层，不重复已有 pair，也不把 Traffic Manager 重复测量计入独立样本。9 条运行均通过 CARLA 0.9.16、`Carla666-0916`、`heuristic_v2`、RGB、路线和服务严格验收；本轮 CARLA 在线训练未启动。

## 新增六条实测

| sample_id | 分层 | 代理稳健分 | 实测风险 | 实测档位 | 预测碰撞概率 | 碰撞 |
|---|---|---:|---:|---|---:|---:|
| `lhs_high_20260817_0192` | mid_low_collision | 58.165 | 50.692 | high | 0.322 | 否 |
| `lhs_high_20260817_0112` | near_high_low_collision | 49.529 | 73.834 | high | 0.257 | 是 |
| `lhs_high_20260817_0120` | mid_high_collision | 59.122 | 52.734 | high | 0.516 | 否 |
| `lhs_high_20260817_0099` | high_threshold_uncertain_collision | 52.433 | 47.702 | medium | 0.365 | 否 |
| `lhs_high_20260817_0103` | mid_uncertain_collision | 57.514 | 49.363 | medium | 0.478 | 否 |
| `lhs_high_20260817_0048` | upper_high_collision | 64.249 | 79.602 | critical | 0.563 | 是 |

新增运行结果为 `6/6` 严格通过，其中碰撞 `2/6`；合并 V1 后独立样本为 `9` 条、碰撞 `4/9`。

## 合并校准结果

- 风险 MAE：`11.752`；RMSE：`13.840`；实测分相对代理分偏差：`+5.024`。
- 风险排序 Spearman `rho=0.433`，Kendall `tau=0.389`。
- high 以上阈值筛选：召回 `5/6`，准确率 `0.667`；存在 `1` 个漏检和 `2` 个误报。
- 预测碰撞概率 `0.5` 阈值：召回 `2/4`，准确率 `0.667`，Brier `0.213`；仍漏掉碰撞边界样本。
- 重复 Traffic Manager 方向检查仍为 `rule_guided_lhs > sac_policy`，但该结果只用于方向证据，不增加独立样本量。

## 决策边界

新增样本降低了 V1 的平均偏差（`+10.766` -> `+5.024`），但合并排序相关性和碰撞边界识别仍不足以把代理当作实测风险或概率模型。代理继续只用于候选筛选、分层观察和实验优先级排序，不作为在线训练 reward，不触发代理复训或 CARLA 在线训练。

下一步不重复已有 pair。若继续实验，应在明确的新问题和独立支持域覆盖目标下设计新的独立场景；否则先整理现有证据和阶段四质量门，不扩大运行规模。

## 复现入口

- 选择工具：`tools/select_lhs_high_calibration_batch.py`
- 计划配置：`configs/lhs_high_independent_carla_plan_v2.json`
- 校准工具：`tools/calibrate_lhs_high_boundary.py --calibration-format lhs_high_proxy_calibration_v2`
- 新批次静态证据：`F:\Carla\output-0.9.16\lhs_high_independent_carla_plan_v2\20260823_085134`
- 新批次运行证据：`F:\Carla\project-transfer\lhs_high_proxy_calibration_v2\execution_smoke_v2`、`F:\Carla\project-transfer\lhs_high_proxy_calibration_v2\execution_remaining_v2`
- 合并校准输出：`F:\Carla\project-transfer\lhs_high_proxy_calibration_v2_20260823_090057`
