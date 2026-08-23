# ScenarioRunner 直执行边界 V1

## 入口

`tools/run_scenario_runner.py` 负责解析 XOSC、定位 ScenarioRunner、生成命令和写入 manifest。默认只做 dry-run，只有显式传 `--execute` 才会启动外部 ScenarioRunner：

```bash
python tools/run_scenario_runner.py \
  --runner-root /home/zhaozirong/software/scenario_runner-0.9.16 \
  --xosc <scenario.xosc> \
  --output <scenario_runner_manifest.json> \
  --execute
```

## 当前状态

当前服务器环境中没有 `scenario_runner.py` 或 `srunner` 包，`scenario_runner-0.9.16` 外部代码未成功部署，因此完整直执行尚未运行。项目自定义 JSON -> XOSC 的静态适配和 Scene 04 CARLA JSON 运行不能替代 ScenarioRunner 直执行。

## 完成条件

后续安装并固定 ScenarioRunner 版本后，至少需要：

1. XOSC XML 解析和 ScenarioRunner 版本预检通过。
2. CARLA 0.9.16 服务在线，地图、ego 绑定和 OpenSCENARIO 事件均可执行。
3. 自定义 `CARLA:pedestrian_crossing` 扩展有运行时插件或被标准动作替换。
4. 单场景产生 `metadata.json`、遥测、路线和服务健康证据。

在上述条件完成前，材料中只能描述为“直执行预检入口”，不能写成完整 ScenarioRunner 兼容。
