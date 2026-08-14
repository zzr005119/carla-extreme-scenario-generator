# 路线控制器单场景冒烟回归

该回归使用中风险 CVAE 代表样本验证主车与前车的确定性 waypoint 跟踪控制。

验收要求：仿真完成、RGB 写盘完成、CARLA 服务健康、路线严格验收 `1/1`；RGB 不少于 `100` 帧，双车同时在途率为 `1.0`，主车与前车最大路线偏差均不超过 `3.0 m`。

启动 CARLAUE4 后运行：

```cmd
"D:\Xx\竞赛\大创实施ing\data\scenarios\route_controller_smoke_v1\run_smoke.cmd"
```
