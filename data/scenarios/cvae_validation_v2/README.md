# CVAE CARLA 抽样验证集

该目录用于验证生成模型参数能否在 CARLA 中成功运行，并回填实测风险。
`target_risk_level` 是生成条件，`observed_risk` 才是 CARLA 实测结果。

## 执行顺序

1. 启动 CARLAUE4。
2. 推荐依次运行下列分批脚本，每批完成后观察 CARLA 是否稳定：
   - `run_part_01.cmd`
   - `run_part_02.cmd`
   - `run_part_03.cmd`
   也可以一次运行 `run_all.cmd`。
3. 全部场景运行后执行：

```cmd
cd /d D:\Xx\竞赛\大创实施ing
D:\Anaconda\envs\Carla666\python.exe tools\collect_carla_validation.py --manifest "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v2\manifest.json"
```

`run_all.cmd` 使用当前系统 `python`，该解释器必须已安装 CARLA Python API；
结果回填使用 `Carla666`，避免与 CARLA 运行环境混用。

每一批包含低、中、高、临界四档各 1 条，并共享同一个 Traffic Manager 种子；
批内顺序固定随机化，用于控制交通随机性和连续运行顺序的干扰。

轻量传感器配置仅保留 640×360 RGB 与碰撞传感器，降低本机负载；
风险评分仍来自车辆、前车、行人遥测和天气参数。
