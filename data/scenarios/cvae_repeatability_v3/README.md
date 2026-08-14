# CVAE CARLA 确定性路线回归 V3

该实验在单场景 waypoint 控制器冒烟验收通过后，验证三个固定场景在三个交通种子下的受控重复性。旧 `cvae_repeatability_v2` 保留为失败诊断证据，不被覆盖。

## 实验设计

- 固定低、中、高风险代表场景各 1 条。
- 每个场景运行 3 个 Traffic Manager 种子，共 9 次。
- 三批采用平衡交叉安排，每批包含低、中、高场景各 1 条。
- 仅用于工程回归，不支持统计显著性结论。
- 验收要求包括场景完成、RGB 不少于 100 帧、服务健康、双车同时在途率 1.0，以及双方最大路线偏差不超过 3.0 m。
- 逐帧记录双方控制量、主车安全制动原因、控制器路径进度和路线拓扑诊断。

## 执行

启动 CARLAUE4 后运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v3\run_all.cmd"
```

`run_all.cmd` 会在九次仿真完成后自动执行严格验收。也可分批运行：

- `run_part_01.cmd`
- `run_part_02.cmd`
- `run_part_03.cmd`

分批运行全部完成后执行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v3\collect_results.cmd"
```
