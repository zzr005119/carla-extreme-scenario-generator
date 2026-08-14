# Seed Scenario Dataset V1

该目录是生成式 AI 参数级场景模型的第一版种子数据，不是 CARLA 实测结果。

## 数据规模

- 总样本：256
- 风险目标分布：`{"critical": 64, "high": 64, "low": 64, "medium": 64}`
- 数据划分：`{"test": 36, "train": 180, "validation": 40}`
- 各风险档划分：`{"low": {"test": 9, "train": 45, "validation": 10}, "medium": {"test": 9, "train": 45, "validation": 10}, "high": {"test": 9, "train": 45, "validation": 10}, "critical": {"test": 9, "train": 45, "validation": 10}}`
- 生成方法：平衡风险分层 + Latin Hypercube 参数覆盖
- 随机种子：`20260812`

## 文件

- `scenarios.jsonl`：全部场景记录。
- `train.jsonl`：训练集。
- `validation.jsonl`：验证集。
- `test.jsonl`：测试集，仅用于最终模型评估。
- `example_record.json`：单条场景记录示例。
- `example_compiled_config.json`：编译后的 CARLA 完整配置示例。
- `manifest.json`：数据来源、分布和校验结果。

## 复现与校验

```cmd
python tools\generate_seed_dataset.py --force
python core\scenario_validator.py data\scenarios\seed_v1\scenarios.jsonl
python scenes\scene_04_parameterized.py --config data\scenarios\seed_v1\example_compiled_config.json --validate-only
```

## 标签边界

`conditions.target_risk_level` 是参数设计目标，不是 CARLA 实测风险等级。
样本完成仿真后，应将结果写入 `observed_risk`，训练和论文分析时必须区分目标标签与实测标签。
