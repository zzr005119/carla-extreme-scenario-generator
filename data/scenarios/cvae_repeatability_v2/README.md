# CVAE CARLA 路线锁定回归 V2

该实验验证锁定主车与前车路线、禁止随机换道后，同一场景是否仍出现约 40 分的分支跳变。

## 实验设计

- 固定低、中、高风险代表场景各 1 条。
- 每个场景运行 3 个 Traffic Manager 种子，共 9 次。
- 三批采用平衡交叉安排，每批包含低、中、高场景各 1 条。
- 仅用于工程回归，不支持统计显著性结论。
- 验收要求包括场景完成、传感器完成、服务健康和路线锁定通过。

## 执行

启动 CARLAUE4 后运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v2\run_all.cmd"
```

也可分批运行：

- `run_part_01.cmd`
- `run_part_02.cmd`
- `run_part_03.cmd`

运行完成后执行：

```cmd
cd /d "D:\Xx\竞赛\大创实施ing"
D:\Anaconda\envs\Carla666\python.exe tools\collect_carla_repeatability.py --manifest "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v2\manifest.json"
```
