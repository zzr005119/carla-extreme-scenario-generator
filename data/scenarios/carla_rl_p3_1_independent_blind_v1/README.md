# P3.1 独立盲测集 V1

该目录保存 P3.1 的独立 blind split 计划，不保存 CARLA 原始传感器帧。

## 设计

- 计划文件：`carla_rl_multiscene_plan_p3_1_blind_v1.json`
- 规模：`24` 条盲测场景
- 分层：`lhs/gmm/cvae × low/medium/high/critical`
- 每个分层组合：`2` 条
- 独立生成种子：`20260906`
- 基础冻结计划种子：`20260903`
- 计划哈希：`28e23ff5c60464ce38e874e04ea09cb22124d52f5d9eb3f54e3239b77c0143c6`

盲测场景在 15 维参数空间中重新采样，拥有新的 `canonical_sample_id` 和 `scenario_hash`。生成脚本会拒绝与现有 117 条场景发生 ID/hash 重叠，并要求最小归一化参数距离达到阈值。

## 执行

从项目根目录运行：

```cmd
.\tools\server_carla_rl_p3_1_04_evaluate_blind.cmd
```

该命令只评估 dev 晋级门选中的 1,000 步 SAC checkpoint，不追加训练。服务器任务完成后仅回收结构化摘要和日志，不回收原始传感器帧。

盲测结果在 CARLA 实机运行完成前不得写成泛化证明；目标风险档仍是设计条件，`observed_risk` 才是实测结果。
