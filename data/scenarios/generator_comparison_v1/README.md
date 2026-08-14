# LHS / GMM / CVAE CARLA 同口径对照 V1

该实验在冻结的 `waypoint_follower_v1` 下比较三种参数级场景生成器。

## 实验设计

- 生成器：LHS、条件 GMM、条件表格 CVAE。
- 每个生成器在低、中、高、临界四档各选择 3 个场景，共 36 个独立场景样本。
- 每个场景使用三个 Traffic Manager 种子重复运行，共 108 次。
- 独立实验单位是场景样本；交通种子属于重复测量，不能当作额外独立样本。
- 采用相同的 `spread` 抽样、基础配置、控制器、传感器和严格验收口径。
- 9 个平衡组各包含三种生成器 × 四个风险档，拆为 27 个四场景小批次；组内随机化用于削弱运行顺序和设备状态干扰。
- 本轮是工程描述性对照，不支持统计显著性声明。

## 执行

启动 CARLAUE4 后，优先逐个运行下列 9 个组脚本：

- `run_group_01.cmd`
- `run_group_02.cmd`
- `run_group_03.cmd`
- `run_group_04.cmd`
- `run_group_05.cmd`
- `run_group_06.cmd`
- `run_group_07.cmd`
- `run_group_08.cmd`
- `run_group_09.cmd`

每个组脚本包含 3 个四场景小批次；若设备不稳定，可直接运行对应的 `run_part_*.cmd`。
一次运行全部 108 次可使用 `D:\Xx\竞赛\大创实施ing\data\scenarios\generator_comparison_v1\run_all.cmd`，RTX 4060 设备不推荐连续执行。

全部完成后运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\generator_comparison_v1\collect_results.cmd"
```

重新检查 108 份配置可运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\generator_comparison_v1\validate_all.cmd"
```

汇总时同时输出跨种子重复性和三生成器对照报告；始终分开报告 `target_risk_level` 与 CARLA 实测 `observed_risk`。

共生成 `27` 个小批次脚本。
