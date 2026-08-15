# 风险反馈数据集 V2

- 基础数据：`36` 个独立场景。
- 外部验证新增：`27` 个独立场景。
- 合并结果：`63` 个独立场景，重复 `sample_id` 为 `0`。
- 碰撞场景：`18` 个。
- Traffic Manager 种子仍作为同一场景的重复测量，不计为独立样本。
- `target_risk_level` 和 `generator` 仅用于分层与诊断，不作为风险代理输入。

## 文件

- `external_validation_addition.csv`：27 个外部验证新增场景。
- `dataset.csv`：合并后的场景级训练数据。
- `dataset.jsonl`：与 CSV 等价的逐行 JSON。
- `merge_summary.json`：来源哈希、计数和合并校验。
