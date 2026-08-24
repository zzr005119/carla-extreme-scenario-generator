# ScenarioRunner 直执行边界 V1

## 入口

`tools/run_scenario_runner.py` 负责解析 XOSC、定位 ScenarioRunner、生成命令和写入 manifest。默认只做 dry-run，只有显式传 `--execute` 才会启动外部 ScenarioRunner；Traffic Manager 默认使用项目端口 `8100`，不会强制等待外部 ego：

```bash
python tools/run_scenario_runner.py \
  --runner-root /home/zhaozirong/software/scenario_runner-0.9.16 \
  --xosc <scenario.xosc> \
  --traffic-manager-port 8100 \
  --traffic-manager-seed <seed> \
  --sync \
  --output <scenario_runner_manifest.json> \
  --execute
```

服务器直接执行时还需要使用固定环境并暴露 CARLA `agents` 包：

```bash
export PYTHONPATH=/home/zhaozirong/software/scenario_runner-0.9.16:/home/zhaozirong/software/carla-0.9.16/PythonAPI/carla
export SCENARIO_RUNNER_ROOT=/home/zhaozirong/software/scenario_runner-0.9.16
/home/zhaozirong/software/envs/Carla666-0916/bin/python -u \
  /home/zhaozirong/software/scenario_runner-0.9.16/scenario_runner.py \
  --openscenario /home/zhaozirong/projects/carla-extreme-scenario-generator/artifacts/seed_v1_high_0165.xosc \
  --host 127.0.0.1 --port 2000 --timeout 30 \
  --trafficManagerPort 8100 --trafficManagerSeed 20260977 --sync \
  --output --json --junit \
  --outputDir /home/zhaozirong/projects/carla-extreme-scenario-generator/artifacts/scenario_runner_v1_20260824_direct_tm8100
```

## P2 实机证据

2026-08-24 已在实验室服务器完成 `seed_v1_high_0165` 的单场景直执行：

| 项目 | 证据 |
|---|---|
| CARLA | 客户端/服务端 `0.9.16`，RPC `127.0.0.1:2000` |
| 环境 | `/home/zhaozirong/software/envs/Carla666-0916`，Python `3.12.13` |
| GPU | CARLA 使用 GPU1；GPU0 的 vLLM 未停止 |
| 地图 | `Town10HD_Opt`，当前世界 `155` 个 spawn points |
| 主车位姿 | spawn index `40` 查询为 `(106.028816, 67.419983, 0.600000, yaw=-89.609253)` |
| Traffic Manager | `8100`，seed `20260977`；避开已占用的 `8000/8001` |
| XOSC | OpenSCENARIO `1.0`；SHA-256 `15B95CE8ABFE2556D0EF4F73D13C2BCACC58FB8A62DC305B5F1080BFC4AF9415` |
| 运行日志 | `/home/zhaozirong/projects/carla-extreme-scenario-generator/artifacts/scenario_runner_v1_20260824_direct_tm8100/runner_stdout.log` |
| Runtime manifest | `/home/zhaozirong/projects/carla-extreme-scenario-generator/artifacts/scenario_runner_v1_20260824_direct_tm8100/scenario_runner_manifest.json` |
| 生命周期 | `Preparing scenario` -> `ScenarioManager: Running scenario` -> `No more scenarios .... Exiting` |

这证明当前最小 XOSC 子集能够由 ScenarioRunner 在 CARLA 0.9.16 中加载、生成主车/前车/行人并运行 Storyboard；runtime manifest 记录返回码 `0`。ScenarioRunner 在最后一次清理时对已移除的 ego actor 打印 `failed to destroy actor` 警告，但不影响进程返回码和场景完成标记，后续若需要无警告收尾再单独处理官方清理策略。纯 OpenSCENARIO 场景没有 ScenarioRunner criteria，因此日志会出现 `Nothing to analyze`，也不会产生 JSON/JUnit 结果文件；这不等价于风险、传感器或路线质量验收。

## 已完成条件

1. XOSC 通过 OpenSCENARIO 1.0 结构校验，`integer`、车辆蓝图和主车 ego 标记符合 ScenarioRunner 解析约定。
2. CARLA 0.9.16 服务在线，地图和 Traffic Manager 端口可用。
3. 行人动作使用标准 `LongitudinalAction/SpeedAction`，不依赖未部署的 `CARLA:pedestrian_crossing` 插件。
4. 单场景真实运行日志、版本、地图、TM 端口、主车坐标和 XOSC 哈希已登记。

## 明确边界

- 这是 ScenarioRunner 单场景直执行冒烟，不是 Scene 04 的多传感器 `metadata.json` 风险验收。
- XOSC 的天气、传感器、`heuristic_v2`、TTC、碰撞统计、路线控制器和写盘队列仍由旁路 CARLA JSON/Scene 04 负责。
- 主车 `ego_spawn_index` 到 `WorldPosition` 的坐标需要结合目标 CARLA 地图查询；转换器通过 `--ego-world-position X Y Z H P R` 接收已查询位姿，不声称跨地图自动解析。
- `--reloadWorld` 在服务器上可能超过默认 10 秒客户端超时；本次复用已健康的 `Town10HD_Opt` 世界完成执行，地图重载需要单独延长超时验证。
