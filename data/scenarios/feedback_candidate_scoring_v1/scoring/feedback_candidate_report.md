# 反馈候选评分 V1

- 风险反馈训练样本：`36` 个独立场景。
- 已知碰撞场景：`3` 个。
- 候选池：`1536` 个场景。
- Bootstrap 随机森林：`50` 个。
- 最终短名单：`27` 个场景。

## 三通道

1. `stable_high_score`：优先选择稳健预测分高且重复 Top-K 入选频率高的候选。
2. `high_uncertainty`：优先选择模型间预测分歧大、同时具有一定风险水平的候选。
3. `collision_boundary`：优先选择靠近已知碰撞样本且接近碰撞/非碰撞邻域边界的候选。
4. 每个生成器×通道至少保留每个目标档 `1` 个，避免短名单全部塌缩到单一目标档。

## 选择结果

| 生成器 | 通道 | 样本 | 目标档 | 均值 | 标准差 | 稳健分 | Top-K频率 | 碰撞距离 |
|---|---|---|---|---:|---:|---:|---:|---:|
| cvae | collision_boundary | `cvae_critical_20260816_0044` | critical | 57.040 | 4.771 | 54.655 | 0.320 | 0.060 |
| cvae | collision_boundary | `cvae_high_20260815_0253` | high | 49.692 | 3.462 | 47.961 | 0.800 | 0.085 |
| cvae | collision_boundary | `cvae_critical_20260816_0217` | critical | 56.538 | 4.403 | 54.336 | 0.220 | 0.047 |
| cvae | high_uncertainty | `cvae_critical_20260816_0062` | critical | 59.730 | 5.173 | 57.143 | 0.600 | 0.095 |
| cvae | high_uncertainty | `cvae_high_20260815_0058` | high | 49.745 | 3.587 | 47.951 | 0.760 | 0.081 |
| cvae | high_uncertainty | `cvae_critical_20260816_0163` | critical | 58.405 | 5.037 | 55.887 | 0.500 | 0.076 |
| cvae | stable_high_score | `cvae_critical_20260816_0183` | critical | 59.629 | 4.838 | 57.210 | 0.700 | 0.067 |
| cvae | stable_high_score | `cvae_high_20260815_0159` | high | 51.631 | 4.598 | 49.332 | 0.820 | 0.088 |
| cvae | stable_high_score | `cvae_critical_20260816_0052` | critical | 59.596 | 4.728 | 57.232 | 0.680 | 0.095 |
| gmm | collision_boundary | `gmm_critical_20260816_0201` | critical | 59.391 | 5.067 | 56.858 | 0.400 | 0.065 |
| gmm | collision_boundary | `gmm_high_20260815_0025` | high | 53.887 | 4.722 | 51.526 | 0.600 | 0.076 |
| gmm | collision_boundary | `gmm_critical_20260816_0165` | critical | 57.582 | 4.675 | 55.245 | 0.200 | 0.054 |
| gmm | high_uncertainty | `gmm_critical_20260816_0112` | critical | 61.659 | 7.357 | 57.980 | 0.620 | 0.049 |
| gmm | high_uncertainty | `gmm_high_20260815_0227` | high | 53.968 | 5.757 | 51.090 | 0.560 | 0.127 |
| gmm | high_uncertainty | `gmm_critical_20260816_0068` | critical | 61.012 | 6.444 | 57.790 | 0.500 | 0.069 |
| gmm | stable_high_score | `gmm_critical_20260816_0243` | critical | 61.128 | 5.050 | 58.603 | 0.700 | 0.065 |
| gmm | stable_high_score | `gmm_high_20260815_0105` | high | 56.324 | 4.323 | 54.163 | 0.880 | 0.117 |
| gmm | stable_high_score | `gmm_critical_20260816_0119` | critical | 60.763 | 5.026 | 58.250 | 0.580 | 0.086 |
| lhs | collision_boundary | `lhs_critical_20260816_0144` | critical | 60.688 | 7.243 | 57.066 | 0.360 | 0.071 |
| lhs | collision_boundary | `lhs_high_20260815_0058` | high | 53.099 | 4.450 | 50.874 | 0.400 | 0.105 |
| lhs | collision_boundary | `lhs_critical_20260816_0150` | critical | 56.764 | 6.320 | 53.604 | 0.160 | 0.069 |
| lhs | high_uncertainty | `lhs_critical_20260816_0129` | critical | 61.365 | 6.468 | 58.131 | 0.600 | 0.031 |
| lhs | high_uncertainty | `lhs_high_20260815_0155` | high | 56.087 | 5.732 | 53.221 | 0.680 | 0.118 |
| lhs | high_uncertainty | `lhs_critical_20260816_0228` | critical | 62.284 | 6.342 | 59.113 | 0.560 | 0.096 |
| lhs | stable_high_score | `lhs_critical_20260816_0110` | critical | 61.913 | 5.754 | 59.036 | 0.680 | 0.104 |
| lhs | stable_high_score | `lhs_high_20260815_0093` | high | 55.634 | 2.702 | 54.283 | 0.700 | 0.134 |
| lhs | stable_high_score | `lhs_critical_20260816_0065` | critical | 61.891 | 4.578 | 59.602 | 0.600 | 0.111 |

## 解释边界

本结果只形成 CARLA 外部验证短名单。预测分、碰撞邻域分和目标风险档都不能替代实测风险；碰撞通道尤其不能解释为碰撞概率。

