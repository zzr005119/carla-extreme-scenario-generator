# CARLA 0.9.15 历史运行证据

- 迁移时间：2026-08-15。
- 原始目录：`F:\Carla\test\output`。
- 本地归档：`artifacts/carla_0915_runtime_evidence/`。
- 归档内容：JSON、CSV、LOG 和 Markdown，共 `834` 个文件、`16,619,306` 字节。
- 完整性检查：全部文件按相对路径复制，并逐文件校验大小和 SHA-256，缺失 `0`、不一致 `0`。
- 未归档内容：历史 RGB、Depth、Semantic Segmentation 等 PNG/NPY 原始传感器帧。这些文件共约 `14.24 GiB`，不参与当前 15 维参数风险反馈建模，已在迁移后删除。

历史数据集中的 `metadata_path`、`run_dir` 和运行脚本继续保留原始绝对路径，用于记录实验发生时的真实环境；它们不代表当前活动运行路径。后续新增实验统一使用 CARLA 0.9.16、项目仓库中的场景运行器和 `F:\Carla\output-0.9.16`。
