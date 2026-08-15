# 场景数据目录

该目录只保存体积较小、可追溯的结构化场景参数和数据清单。

## 目录约定

- `scenarios/seed_v1/`：第一版参数级种子数据集。
- 后续 CARLA 0.9.16 大规模传感器输出保存在 `F:\Carla\output-0.9.16`，不提交 Git。
- CARLA 0.9.15 历史 JSON、CSV 和日志证据保存在本地忽略目录 `artifacts/carla_0915_runtime_evidence/`；历史清单中的旧绝对路径仅用于来源追溯，不应直接重新执行。
- 模型训练产生的 checkpoint、缓存和大体积中间文件不得直接放入仓库。

## 标签约定

- `conditions.target_risk_level`：参数设计时希望达到的风险等级。
- `observed_risk`：CARLA 实际运行后由风险指标计算得到的实测标签。
- 未经过 CARLA 运行的样本必须保持 `observed_risk.status = not_simulated`，不得表述为已验证高危场景。

## 常用命令

```cmd
python tools\generate_seed_dataset.py --force
python core\scenario_validator.py data\scenarios\seed_v1\scenarios.jsonl
python scenes\scene_04_parameterized.py --config data\scenarios\seed_v1\example_compiled_config.json --validate-only
```
