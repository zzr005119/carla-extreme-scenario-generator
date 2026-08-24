# ScenarioRunner 关联完整验收 V1

_验收日期：2026-08-24；样本：`seed_v1_high_0165`；用途：阶段五实机证据和软著前置材料；不等同于跨地图或批量能力声明_

## 证据分层

本次验收明确分成两层，避免把 OpenSCENARIO 文件本身误写成已经承载项目全部运行语义：

1. **ScenarioRunner 原生直执行层**：同一 XOSC 已在 CARLA 0.9.16 + ScenarioRunner 0.9.16 中完成实体加载、Storyboard 运行和清理，证据见 [`scenario_runner_direct_execution_v1.md`](scenario_runner_direct_execution_v1.md)。纯 XOSC 没有项目 criteria，不产生风险 JSON/JUnit。
2. **项目完整验收层**：使用同一 `seed_v1_high_0165` 的旁路 CARLA JSON，由 `scenes/scene_04_parameterized.py` 执行完整天气、路线、传感器、遥测和风险链路。该层产生 `metadata.json`、`telemetry.csv` 和统一 `acceptance_result.json`。

因此，本文件证明的是“ScenarioRunner 适配样本与项目完整 CARLA 运行链路可以被同一组输入关联复核”，不证明 XOSC 已经跨仿真器表达 RGB/Depth/Semantic/Collision、`waypoint_follower_v1` 或 `heuristic_v2`。

## 配置与入口

配置准备器会从 XOSC 和 CARLA JSON 生成完整验收配置，并强制打开四类传感器、路线锁和固定 Traffic Manager 端口：

```bash
python tools/prepare_scenario_runner_acceptance.py \
  --xosc artifacts/seed_v1_high_0165.xosc \
  --carla-config artifacts/seed_v1_high_0165.carla.json \
  --output-dir artifacts/scenario_runner_v1_full_acceptance \
  --traffic-manager-port 8100
```

服务器实机入口：

```bash
python -u scenes/scene_04_parameterized.py \
  --config artifacts/scenario_runner_v1_full_acceptance/acceptance_config.json \
  --traffic-manager-port 8100
```

严格检查入口：

```bash
python tools/check_scenario_runner_acceptance.py \
  --manifest artifacts/scenario_runner_v1_full_acceptance/acceptance_manifest.json
```

## 2026-08-24 实机结果

| 检查项 | 结果 |
| --- | --- |
| Git 提交 | `2495b0a4bde78c287db15d029ff022786504c0cd` |
| CARLA 客户端/服务端 | `0.9.16 / 0.9.16`，版本匹配 |
| 环境与资源 | 服务器 `Carla666-0916`；CARLA 使用 GPU1；GPU0 vLLM 未修改；GPU1 外部 TensorRT 服务未修改 |
| 地图与 TM | `Town10HD_Opt`；TM `8100`；seed `20260977` |
| 场景执行 | `completed`；同步模式 `0.05 s`；20 秒、400 个仿真步 |
| RGB | `200` 帧，expected/received/saved 均为 `200`，失败 `0` |
| Depth | `200` 帧，expected/received/saved 均为 `200`，失败 `0` |
| Semantic | `200` 帧，expected/received/saved 均为 `200`，失败 `0` |
| Collision | 传感器已启用，碰撞事件计数 `0` |
| 路线控制 | `waypoint_follower`，双车在途率 `1.0` |
| 最大路线偏差 | ego `0.992 m`；lead `0.978 m`；门槛 `3.0 m` |
| 风险 | `heuristic_v2`，`42.268 / medium` |
| 服务与清理 | CARLA 健康检查通过；传感器/场景 Actor 和世界设置清理完成 |
| 统一结果 | `acceptance_result.json` 状态 `passed`，全部 `12` 项检查通过 |
| 结果清单 SHA-256 | `4637890C007AC38AEDC391494AE6240956F38E306C445DE500FA82B271CE7E9F` |

## 证据位置

服务器原始轻量证据：

```text
/home/zhaozirong/projects/carla-extreme-scenario-generator/artifacts/scenario_runner_v1_full_acceptance/
```

其中保留 `acceptance_config.json`、`acceptance_manifest.json`、`acceptance_result.json`，以及运行目录中的 `metadata.json`、`config_snapshot.json` 和 `telemetry.csv`。原始 RGB/Depth/Semantic 帧约 361 MB，仅留在服务器，不进入 Git 或本机材料包。

本机轻量回收目录：

```text
F:\Carla\project-transfer\scenario_runner_v1_full_acceptance_20260824_142853\
```

## 结论边界

- 可以写入当前工程材料：该样本在 CARLA 0.9.16 上通过完整四类传感器、waypoint 路线、风险计算、服务健康和清理质量门。
- 不能据此写成：所有 XOSC 场景都具备完整传感器/风险语义；ScenarioRunner 已完成批量、多地图或跨仿真器兼容；一次样本支持统计泛化结论。
- 本次运行不改变 117 条场景库快照和既有实验结论；它是阶段五的独立展示/接口关联证据。
