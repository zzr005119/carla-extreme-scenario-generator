# LHS/high 风险代理校准 V1

_完成日期：2026 年 8 月 22 日；分析模式：CPU-only 离线分析_

## 证据口径

本轮把 3 条新候选作为独立校准样本：

- `lhs_high_20260817_0203`：near high threshold
- `lhs_high_20260817_0022`：near critical boundary
- `lhs_high_20260817_0041`：uncertain collision boundary

此前 LHS/high 的 3 个 Traffic Manager 种子重复结果只用于方向检查，不计入独立样本量。所有输入运行均已经通过 CARLA 0.9.16、`heuristic_v2`、传感器、路线和服务严格门。

## 独立样本结果

| sample_id | 代理稳健分 | 实测风险 | 代理档位 | 实测档位 | 预测碰撞概率 | 实测碰撞 |
|---|---:|---:|---|---|---:|---:|
| `lhs_high_20260817_0203` | 49.952 | 46.417 | medium | medium | 0.213 | 否 |
| `lhs_high_20260817_0022` | 66.563 | 79.118 | high | critical | 0.789 | 是 |
| `lhs_high_20260817_0041` | 56.579 | 79.856 | high | critical | 0.405 | 是 |

风险 MAE 为 `13.122`，RMSE 为 `15.405`，实测风险相对代理分平均偏差为 `+10.766`。代理排序与实测排序的 Spearman `rho=0.500`、Kendall `tau=0.333`。以 `50` 分作为 high 以上筛选阈值时，3 条样本均被正确筛出；但碰撞概率 `0.5` 阈值只召回 `1/2` 个碰撞样本，漏掉 uncertain-collision 候选。

## 重复方向检查

同一 LHS/high 源场景的重复测量中，代理增量和实测风险增量排序都为：

`rule_guided_lhs > sac_policy`

但实测增量约为代理增量的 `4.03` 倍和 `6.11` 倍。该结果支持保留代理的筛选方向，不支持把代理分或代理增量直接当作 CARLA 实测风险。

## 决策边界

当前代理可以继续作为候选筛选和边界观察信号，但不能作为实测风险替代值，也不能直接用于在线训练 reward。独立样本数仅为 `3`，不进行显著性检验、置信区间或代理复训决策。

可执行的下一步是从未使用候选中补充一批独立场景，继续使用相同的严格 CARLA 验收门；在此之前不重复同一 pair、不启动 CARLA 在线训练。

## 复现入口

- 工具：`tools/calibrate_lhs_high_boundary.py`
- 独立校准表：`independent_calibration.csv`
- 重复方向表：`repeat_direction_check.csv`
- 本次结果：`F:\Carla\project-transfer\lhs_high_proxy_calibration_v1_20260823_000100`
- 新候选实测证据：`F:\Carla\project-transfer\server-results\execution_smoke_v1_20260822_222603`、`F:\Carla\project-transfer\server-results\execution_remaining_v1_20260822_223026`
