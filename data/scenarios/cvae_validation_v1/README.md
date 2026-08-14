# CVAE CARLA 抽样验证集 V1

该目录用于验证生成模型参数能否在 CARLA 中成功运行，并回填实测风险。
`target_risk_level` 是生成条件，`observed_risk` 才是 CARLA 实测结果。

## 执行顺序

1. 启动 CARLAUE4。
2. 双击或在 CMD 中运行 `run_all.cmd`。
3. 全部场景运行后执行：

```cmd
cd /d D:\Xx\竞赛\大创实施ing
D:\Anaconda\envs\Carla666\python.exe tools\collect_carla_validation.py --manifest "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v1\manifest.json"
```

`run_all.cmd` 使用当前系统 `python`，该解释器必须已安装 CARLA Python API；
结果回填使用 `Carla666`，避免与 CARLA 运行环境混用。

轻量传感器配置仅保留 640×360 RGB 与碰撞传感器，降低本机负载；
风险评分仍来自车辆、前车、行人遥测和天气参数。
