# 生成模型小规模 Diffusion 对照 V1

_更新日期：2026-08-23；证据层级：E2（本机离线）；不包含新 CARLA 实测_

## 目的与边界

本轮为阶段五 `S5-CORE-02` 的小规模可比实验，在现有 15 维连续场景参数契约上增加轻量条件表格 Diffusion。它只作为 LHS、条件 GMM 和 C-TabCVAE 的研究对照，不替换已经冻结的 LHS/GMM/CVAE 工程基线。

`conditions.target_risk_level` 仍是参数设计条件，`observed_risk` 保持 `not_simulated`。风险排序使用已冻结的 CARLA 实测风险代理进行候选预排序，不能解释为本轮生成样本已经完成 CARLA 验证。

## 实现

- 模型：`models/conditional_tabular_diffusion.py`
- 训练：`training/train_diffusion.py`
- 统一生成：`tools/generate_with_model.py --model diffusion`
- 对照编排：`tools/run_diffusion_comparison.py` / `tools/run_diffusion_comparison.cmd`
- 统一评估：`analysis/evaluate_generators.py`
- 检查点格式：`conditional_tabular_diffusion_v1`
- 输入：15 维归一化连续参数 + 4 维风险 one-hot + 8 维天气 multi-hot
- 约束：采样后按目标档显式投影到 `tools/generate_seed_dataset.py` 的设计区间，再经过统一 Schema/语义校验

该投影是参数级可行域处理，不是实测风险控制，也不保证 CARLA Actor、路线或传感器运行成功。

## 可复现命令

在项目根目录执行：

```powershell
tools\run_diffusion_comparison.cmd --device cuda --output-dir F:\Carla\project-transfer\diffusion_comparison_v1
```

命令默认每个生成器、每个目标档生成 `32` 条，共 `4 × 4 × 32 = 512` 条参数记录；使用已有的 GMM/CVAE 权重，若未指定 Diffusion 权重则先训练一份小模型。输出目录被 Git 忽略，包含 `samples/`、`evaluation/generator_evaluation.json`、`evaluation/generator_evaluation.md` 和可选的 `generator_risk_ordering.json`。

只运行已有 Diffusion 权重的对照：

```powershell
tools\run_diffusion_comparison.cmd --device cuda `
  --diffusion-artifact F:\Carla\project-transfer\diffusion_comparison_v1\diffusion\best.pt `
  --output-dir F:\Carla\project-transfer\diffusion_comparison_v1\comparison
```

## 本轮离线结果

对照配置为四个生成器、四个目标档、每档 `32` 条；生成记录均完成统一入口和 Schema 校验：

| 生成器 | 有效率 | 唯一率 | 四档设计区间一致率 | 风险代理均值（low / medium / high / critical） |
|---|---:|---:|---:|---|
| LHS | 1.000 | 1.000 | 1.000 | 25.929 / 32.618 / 49.941 / 56.945 |
| GMM | 1.000 | 1.000 | 0.312–0.625 | 25.897 / 32.486 / 48.711 / 56.731 |
| C-TabCVAE | 1.000 | 1.000 | 0.000–0.594 | 26.998 / 33.422 / 38.189 / 47.988 |
| Diffusion + 档位投影 | 1.000 | 1.000 | 1.000 | 28.407 / 35.997 / 43.173 / 54.868 |

按目标档分别聚合后，四种生成器的风险代理均值均保持 `low < medium < high < critical`，但这是冻结代理上的排序一致性，不是新增 CARLA 风险证据。Diffusion 的参数相关矩阵误差约 `0.213–0.236`，同档平均样本距离约 `0.491–0.797`；这些指标只描述当前人工种子分布上的参数样本。

## 结论

1. `S5-CORE-02` 已满足“小规模离线对照、统一合法性/多样性/风险排序口径”的工程验收条件。
2. Diffusion 在本轮经过显式设计区间投影后达到四档 `100%` 设计区间记录一致率；这不能单独归因于神经网络，投影是必要的约束后处理。
3. 现有结果不支持替换 C-TabCVAE 主线，也不支持任何生成器已经学会真实交通风险分布的结论。
4. 后续若要比较真实危险性，必须从未重复场景中抽样，使用 CARLA `0.9.16` 严格验收并回填 `observed_risk`；本轮不自动提交或启动该任务。
