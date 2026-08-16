# 风险指标拆解校准 V1

- 数据集：风险反馈 V4，`99` 个独立场景，其中碰撞场景 `29` 个。
- 数据集 SHA-256：`abae68b1906fedc1f161f0e4ed56d98176a828b7ffcc264f7e114f38ac935974`。
- 输入：原有 `15` 维归一化场景参数；不使用 `target_risk_level` 和 `generator` 作为模型输入。
- 校准公式：`continuous_score = (total_score - 25 × collision_run_rate) / 0.75`。
- 验证：`50` 次重复分层三折 OOF，按 `generator × target_risk_level` 分层，固定 Top-`9`。
- 实现：`analysis/analyze_risk_score_decomposition.py`。
- 服务器入口：`tools/server_risk_metric_calibration_v1.cmd`。
- 碰撞分类入口：`tools/server_collision_proxy_v4.cmd`。

## 结果位置

- 风险反馈 V4：`F:\Carla\project-transfer\server-results\risk_feedback_v4_20260816_233210`。
- 拆解校准：`F:\Carla\project-transfer\server-results\20260816_235214_20260816_235946`。
- 碰撞分类：`F:\Carla\project-transfer\server-results\20260817_000201_20260817_000551`。

碰撞分类服务器目录使用 `20260817` 标识，是服务器任务目录的时钟命名；项目状态仍按 2026 年 8 月 16 日记录。

## 文件边界

仓库只保存结论和可复现代码；`repeat_predictions.csv` 等运行输出保留在 `F:\`，不提交模型权重和逐次大表。
