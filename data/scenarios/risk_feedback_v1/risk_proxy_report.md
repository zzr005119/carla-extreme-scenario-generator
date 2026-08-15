# 风险代理基线 V1

- 独立场景：`36` 个。
- 重复测量：每个场景的 3 个 Traffic Manager 种子先聚合为场景均值。
- 输入：15 维归一化场景参数；`target_risk_level` 和 `generator` 不作为模型输入。
- 目标：场景级 `observed_risk_score_mean`。
- 交叉验证：按 `generator × target_risk_level` 分层的 3 折交叉验证。
- 当前选择模型：`random_forest`。
- MAE：`5.515`；RMSE：`10.138`；Spearman：`0.9024453024453025`。

## 解释边界

该基线用于对候选场景进行风险排序，不替代 CARLA 实测，也不证明生成器已经学会真实交通风险分布。由于独立场景只有 36 个，本结果只作工程基线和误差诊断，不作统计显著性结论。

## 输出文件

- `dataset.csv`：36 个独立场景的聚合特征和风险标签。
- `oof_predictions.csv`：交叉验证折外预测。
- `model_comparison.csv`：均值基线、Ridge 和随机森林对照。
- `target_summary.csv`：按生成器和目标档的实测/预测汇总。
- `feature_importance.csv`：选中模型的特征重要性。
- `proxy_summary.json`：机器可读汇总。
