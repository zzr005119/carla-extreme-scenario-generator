# 风险反馈 V5 与物理增强代理

## 数据集

- 基础数据：风险反馈 V4 的 `99` 个独立场景。
- 新增数据：物理增强配对验证的 `18` 个独立场景。
- 合并结果：`117` 个独立场景，LHS、GMM、CVAE 各 `39` 个，碰撞场景 `39` 个。
- Traffic Manager 种子已聚合为场景级重复测量，不作为独立样本计数。

## V4/V5 原始 15 维对比

- MAE：`11.594 → 12.012`。
- Spearman：`0.707 → 0.686`。
- Top-9 Jaccard：`0.284 → 0.254`。
- 碰撞场景 MAE：`18.912 → 17.527`。

新增主动筛选样本改善了碰撞子集误差，但使原始 15 维代理的总体误差、排序和 Top-K 稳定性变差，因此 V5 不应继续只使用原始 15 维输入。

## V5 物理增强重复 OOF

- 输入：原始 `15` 维参数 + `12` 个生成前物理交互派生特征。
- 验证：`50` 次按 `generator × target_risk_level` 分层的三折 OOF。
- MAE：原始 `12.012`，增强 `10.986`。
- Spearman：原始 `0.686`，增强 `0.781`。
- Top-9 Jaccard：原始 `0.254`，增强 `0.304`。
- 碰撞场景 MAE：原始 `17.527`，增强 `16.169`。
- 碰撞分类 AP：原始 `0.535`，增强 `0.686`。
- 碰撞分类 ROC-AUC：原始 `0.740`，增强 `0.825`。

物理增强在 99 场景 V4 和 117 场景 V5 上均同时改善总体误差、排序、碰撞误差和碰撞分类，现冻结为后续候选评分的优先实验分支；原始 15 维仍保留为可复现实验基线。

## 冻结模型

- 模型：随机森林风险回归器。
- 特征空间：`physical_enhanced`，共 `27` 维。
- 单次分层三折 OOF：MAE `11.472`、RMSE `13.911`、Spearman `0.737`、高风险及以上召回率 `0.986`。
- 目标档实测均值和 OOF 预测均值均保持 `low < medium < high < critical`。
- 服务器模型：`/home/zhaozirong/software/models/carla-extreme-scenario-generator/artifacts/risk_proxy_v5_physical/20260817_140802/selected_model.joblib`

模型权重不进入 Git；本目录只保存结论和可追溯路径。

## 证据位置

- 服务器结果：`/home/zhaozirong/software/output/carla-0.9.16/risk_feedback_v5/20260817_140802`
- 本地回收：`F:\Carla\project-transfer\server-results\20260817_140802_20260817_143432`
- 生成提交：`b27f2ca`
