# P3.1 独立盲测集 V1

该目录保存已封存的 P3.1 独立 blind split 计划和关键产物哈希清单，不保存 CARLA 原始传感器帧。

## 设计

- 计划文件：`carla_rl_multiscene_plan_p3_1_blind_v1.json`
- 规模：`24` 条盲测场景
- 分层：`lhs/gmm/cvae × low/medium/high/critical`
- 每个分层组合：`2` 条
- 独立生成种子：`20260906`
- 基础冻结计划种子：`20260903`
- 计划哈希：`28e23ff5c60464ce38e874e04ea09cb22124d52f5d9eb3f54e3239b77c0143c6`
- 封存清单：`archive_manifest_v1.json`

盲测场景在 15 维参数空间中重新采样，拥有新的 `canonical_sample_id` 和 `scenario_hash`。生成脚本会拒绝与现有 117 条场景发生 ID/hash 重叠，并要求最小归一化参数距离达到阈值。

## 执行

从项目根目录运行：

```cmd
.\tools\server_carla_rl_p3_1_04_evaluate_blind.cmd
```

该命令只评估 dev 晋级门选中的 1,000 步 SAC checkpoint，不追加训练。现有盲测已经完成并封存，不应再次运行该入口进行模型筛选。

盲测四项工程门均为 `24/24`，平均风险增量为 `+0.360917`，中位数为 `+0.3045`，`17/24` 场景上升。该结果是 `best_so_far` 选择下的小样本描述性证据，不是总体泛化证明；目标风险档仍是设计条件，`observed_risk` 才是实测结果。
