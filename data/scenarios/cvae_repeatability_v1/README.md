# CVAE CARLA 多种子重复性验证 V1

该实验将第二轮的 12 个固定场景分别运行 3 个 Traffic Manager 种子。
第二轮已有 12 次结果，因此本目录只新增缺失的 24 次运行。

## 实验设计

- 12 个场景 × 3 个交通种子 = 36 次完整结果。
- 已有结果：12 次；本轮新增：24 次。
- 每批 4 次，包含低、中、高、临界目标各 1 条。
- 同一场景的参数保持不变，只改变 Traffic Manager 种子。

## 执行

启动 CARLAUE4 后，建议依次运行：

- `run_part_01.cmd`
- `run_part_02.cmd`
- `run_part_03.cmd`
- `run_part_04.cmd`
- `run_part_05.cmd`
- `run_part_06.cmd`

全部运行完成后执行：

```cmd
cd /d D:\Xx\竞赛\大创实施ing
D:\Anaconda\envs\Carla666\python.exe tools\collect_carla_repeatability.py --manifest "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\manifest.json"
```

若某批失败，只需重新运行对应的 `run_part_XX.cmd`。
