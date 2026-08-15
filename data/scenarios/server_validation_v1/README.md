# 服务器完整环境与批次验证 V1

## 验证范围

- 日期：2026-08-15。
- 主机：`factory22-srv`。
- Python：`/home/zhaozirong/software/envs/Carla666-0916`，版本 3.12.13。
- CARLA：`/home/zhaozirong/software/carla-0.9.16`，客户端与服务端均为 0.9.16。
- GPU：CARLA 和项目模型使用 GPU 1；GPU 0 保留给现有 vLLM 服务。

## 依赖与模型验证

- 完整安装 `requirements-models.txt`，`pip check` 无依赖冲突。
- LHS、GMM、CVAE 在高风险条件下各生成 `32/32` 条有效候选，Schema 有效率、唯一率和最终接收率均为 `100%`。
- 风险代理重新训练选择随机森林，MAE `5.515`、RMSE `10.138`，与本地基线一致。
- 模型产物不进入 Git，服务器实际路径为 `/home/zhaozirong/software/models/carla-extreme-scenario-generator`。

## CARLA 批次验证

服务器上的 8000 和 8001 端口已被现有 API 与 vLLM 占用，因此本批次使用独立 Traffic Manager 端口 8100：

```bash
CUDA_VISIBLE_DEVICES=1 /home/zhaozirong/software/envs/Carla666-0916/bin/python -u batch_runner.py \
  --config configs/batch_rainy_night_variants.json \
  --output-root /home/zhaozirong/software/output/carla-0.9.16/server_batches \
  --traffic-manager-port 8100
```

- 5 个变体 × 3 个交通种子，共 `15/15` 次完成。
- 传感器完整率 `100%`，CARLA 服务健康率 `100%`。
- 每次 RGB、Depth、SemSeg 各 200 帧，共 `9000` 帧。
- 15 次运行均无碰撞。
- 结构化汇总来源：`/home/zhaozirong/software/output/carla-0.9.16/server_batches/batches/rainy_night_variants/20260815_191419`。
- 原始传感器输出约 6.8 GB，仅保留在服务器，不进入 Git。

## 证据文件

- `batch_summary.csv`、`aggregate_summary.csv`、`batch_metadata.json`、`run_schedule.json`：服务器 CARLA 批次明细与聚合结果。
- `generator_evaluation.*`：三生成器服务器推理与统一离线评估结果。
- `*_high_summary.json`：三种生成器的高风险候选生成汇总。
- `proxy_summary.json`、`model_comparison.csv`、`feature_importance.csv`、`target_summary.csv`、`risk_proxy_report.md`：风险代理复训结果。
- `server_environment.txt`：服务器软件、GPU 和关键模型产物校验信息。

本轮只证明服务器环境、模型推理和项目批次链路可用，不增加独立场景样本量，也不替代后续外部验证实验。
