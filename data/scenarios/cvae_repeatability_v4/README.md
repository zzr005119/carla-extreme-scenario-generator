# CVAE CARLA 确定性路线回归 V4

该实验使用冻结的 `waypoint_follower_v1`，验证 12 个固定 CVAE 场景在三个交通种子下的受控重复性。

## 实验设计

- 固定场景数：12；总运行数：36。
- 共 9 个运行区组，每个区组内随机执行。
- 调度设计：九个拉丁式随机区组，每组包含四个风险档各 1 次，种子重复位置在区组间轮换
- 仅用于工程回归，不支持统计显著性结论。
- 验收要求包括场景完成、RGB 不少于 100 帧、服务健康、双车同时在途率 1.0，以及双方最大路线偏差不超过 3.0 m。
- 逐帧记录双方控制量、主车安全制动原因、控制器路径进度和路线拓扑诊断。

## 执行

启动 CARLAUE4 后运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v4\run_all.cmd"
```

`run_all.cmd` 会在 36 次仿真完成后自动执行严格验收。也可分批运行：

- `run_part_01.cmd`
- `run_part_02.cmd`
- `run_part_03.cmd`
- `run_part_04.cmd`
- `run_part_05.cmd`
- `run_part_06.cmd`
- `run_part_07.cmd`
- `run_part_08.cmd`
- `run_part_09.cmd`

分批运行全部完成后执行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v4\collect_results.cmd"
```
