# 参数级物理约束 V1

## 定位

`physical_constraints_v1` 是生成前参数级的可执行性检查模块。它使用场景记录中的时长、距离、触发时间和速度计算可解释的时间/空间关系，拦截明显不可能完成的组合，并把危险边界记录为 warning。

该模块不读取 CARLA 遥测，不判断真实碰撞，不输出事故概率，也不替代 CARLA 实机验收。名义主车速度固定为 `29 km/h`（约 `8.0556 m/s`），因此所有派生量都必须标注为运行前近似。

## 硬约束

- 仿真时长、距离、速度和制动强度必须为有限数值且为正。
- 前车急刹和行人触发时间必须位于 `[0, duration_seconds]`。
- 行人横穿估计完成时间 `trigger_seconds + 2 * roadside_offset_m / speed_mps` 不得超过场景结束时间。
- 缺失字段、非有限值和非正运动学参数必须给出字段路径、错误代码和中文原因。

## 边界提示

- `lead_distance_at_brake_m <= 0`：名义主车速度下急刹时可能已经到达前车初始位置附近，记录为危险边界，不判非法。
- `pedestrian_distance_at_trigger_m <= 0`：名义主车可能已通过行人横穿点，必须通过 CARLA 实测确认交互是否成立。
- 前车急刹与行人触发时间间隔过大时，提示多危险叠加可能较弱。

## 入口与输出

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\check_physical_constraints.py `
  data\scenarios\seed_v1\scenarios.jsonl `
  --output F:\Carla\project-transfer\physical_constraints_v1\seed_report.json `
  --strict
```

核心函数为 `core.physical_constraints.evaluate_physical_constraints` 和 `build_physical_constraint_report`。报告格式为 `physical_constraint_report_v1`，包含记录计数、硬约束通过/失败计数、warning 计数、每条记录的指标和失败原因。

## 当前验收

2026-08-23：种子数据集 `256/256` 条硬约束通过，`0` 条非法；报告已生成到 `F:\Carla\project-transfer\physical_constraints_v1\seed_report.json`。该结果属于静态参数验证，不产生新的 CARLA 风险结果，也不需要 GPU 或服务器训练。
