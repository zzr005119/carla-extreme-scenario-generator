# OpenSCENARIO/CARLA 最小适配边界 V1

## 目的

阶段四第一步只解决一个问题：把现有的 `generated_scenario` 自定义 JSON 记录转换成一份可追溯的 OpenSCENARIO XML 1.0 交换文件，同时编译出当前 Scene 04 可以继续使用的 CARLA JSON 配置。

本适配器不是完整的 OpenSCENARIO 导入器、导出器或跨仿真器兼容层。自定义 JSON 仍然是工程事实源；OpenSCENARIO 文件用于表达通用实体、相对初始位置、时间触发事件和场景时长；CARLA 专属字段通过参数声明、对象属性和旁路 `.carla.json` 保留。

## 版本决策

- 适配器版本：`custom_json_to_openscenario_carla_v1`。
- 输出标准：OpenSCENARIO XML `1.0` 保守子集。
- 运行基线：CARLA `0.9.16`，当前 Scene 04 JSON 配置。
- 事实源：`schemas/generated_scenario.schema.json` 定义的 `multi_hazard_parameter_v1` 单条记录。
- 生成入口：`tools/convert_scenario_to_openscenario.py`。
- 映射配置：`configs/openscenario_adapter_v1.json`。

ASAM 当前标准目录已发布比 1.0 更新的 OpenSCENARIO XML 版本；本项目此处固定 1.0，是为了先锁定可审查的最小契约，不把“标准最新版本”误写成 CARLA 运行时已经验证的版本。后续升级版本必须单独建立映射版本和回归证据。

## 直接映射

| 自定义 JSON | OpenSCENARIO 1.0 表达 | 备注 |
| --- | --- | --- |
| `scenario.duration_seconds` | `Storyboard.StopTrigger/SimulationTimeCondition` | 可直接表达场景停止时间 |
| `lead_vehicle.initial_distance_m` | 前车相对主车 `RelativeObjectPosition.dx` | 仅表达初始纵向间距 |
| `pedestrian.forward_distance_m` | 行人相对主车 `RelativeObjectPosition.dx` | 以主车为参考对象 |
| `pedestrian.roadside_offset_m` | 行人相对主车 `RelativeObjectPosition.dy` | 正负横穿方向仍需 CARLA 侧约定 |
| `lead_vehicle.brake_trigger_seconds` | 前车急刹事件的仿真时间触发器 | 动作使用 `SpeedAction` 目标速度 0 |
| `pedestrian.trigger_seconds` | 行人横穿事件的仿真时间触发器 | 行为通过 `CARLA:pedestrian_crossing` 自定义命令保留 |

## 保留但不伪装成标准语义的字段

以下字段会写入 OpenSCENARIO 参数声明或对象属性；条件、实测风险和来源血缘保留在适配清单中，CARLA 执行字段保留在编译后的 CARLA JSON 中：

- 天气八维参数。
- `traffic_manager_seed`、风险目标档和来源血缘。
- 前车刹车强度、行人速度、CARLA blueprint。
- `traffic`、`sensors`、`risk_evaluation` 和 `output` 全部基础配置。

这些字段是 CARLA 执行所需的工程信息。OpenSCENARIO 1.0 文件中的 `carla_*` 参数不会被解释为跨仿真器通用天气、传感器或风险模型。

## 当前明确不支持

下列内容在 V1 中不会被声称为 OpenSCENARIO 可执行能力：

1. 将 `ego_spawn_index` 解析成真实地图坐标和车道拓扑。
2. 把 CARLA RGB、Depth、Semantic、Collision 传感器和写盘队列映射成标准场景语义。
3. 将 `heuristic_v2`、TTC、碰撞统计或路线严格验收写成 OpenSCENARIO 标准字段。
4. 将 `waypoint_follower_v1` 控制器和 Traffic Manager 行为转换成跨仿真器控制器。
5. 从无地图坐标的 `roadside_offset_m` 自动推导行人完整横穿轨迹。
6. 直接保证生成的 `.xosc` 能由 ScenarioRunner 无旁路脚本执行。

其中行人事件使用 `UserDefinedAction/CustomCommandAction`，命令名固定为 `CARLA:pedestrian_crossing`。它是可追溯的扩展占位，不是当前阶段的运行时插件。

### 为什么暂不支持

| 边界 | 当前原因 | 当前替代方式 |
| --- | --- | --- |
| 真实地图坐标绑定 | 生成记录只有 `ego_spawn_index` 和相对距离，没有真实 `x/y/z`、道路 ID、车道 ID 或 `.xodr` 路网引用；坐标必须结合 CARLA 当前地图查询 waypoint 后才能确定。 | CARLA JSON 继续保留 `ego_spawn_index`，由 Scene 04 在运行时选择出生点和道路 waypoint。 |
| 完整行人横穿轨迹 | `forward_distance_m`、`roadside_offset_m` 和 `speed_mps` 只能描述参数，不能唯一确定从哪一侧人行道出发、穿过哪些车道以及终点在哪里；这些信息依赖地图几何。 | XOSC 保留初始相对位置和触发时间；完整轨迹仍由 Scene 04 的 sidewalk/waypoint 逻辑生成。 |
| 传感器/风险算法标准化映射 | RGB、Depth、Semantic、Collision 的写盘队列、帧数门槛和 `heuristic_v2` 都是本项目 CARLA 执行与评估实现，没有已冻结的跨仿真器扩展契约。 | 传感器、风险评估、遥测和严格验收继续由 `.carla.json`、Scene 04 和 `metadata.json` 负责。 |
| ScenarioRunner 实际执行兼容 | 当前 XOSC 使用逻辑地图名而非已验证的 `.xodr` 文件，并包含 `CARLA:pedestrian_crossing` 自定义命令；尚未实现 ScenarioRunner 侧插件，也尚未完成 1.0 单场景实机冒烟。 | 当前只把 XOSC 作为静态交换产物，先验证生成 CARLA JSON 的实机运行。 |

这些限制是为了保持证据边界：静态文件生成不能替代地图绑定、运行时行为和传感器/风险验收。

## 输出与验收

```powershell
python tools\convert_scenario_to_openscenario.py `
  --input data\scenarios\seed_v1\example_record.json `
  --output-dir artifacts\openscenario_adapter_v1\example
```

输出三个文件：

- `<sample_id>.xosc`：OpenSCENARIO 1.0 最小交换文件。
- `<sample_id>.carla.json`：由现有 `compile_carla_config` 生成的 Scene 04 配置。
- `<sample_id>.adapter_manifest.json`：源记录、映射、基础配置和 XOSC 哈希，以及字段覆盖边界。

只做静态校验：

```powershell
python tools\convert_scenario_to_openscenario.py `
  --input data\scenarios\seed_v1\example_record.json `
  --validate-only
```

静态通过只证明：输入记录合法、映射配置合法、XML 可解析且包含实体/事件/停止触发器、CARLA JSON 具备 Scene 04 的顶层结构。它不证明 CARLA 服务在线、ScenarioRunner 能执行自定义命令、传感器能写盘或路线能完成。

## 后续边界

阶段四 4.2 仍需处理运行时导入和旁路插件：真实 `.xodr`/地图绑定、`ego_spawn_index` 到 Transform、行人轨迹生成、CARLA 天气/传感器注入和 ScenarioRunner 执行适配。2026-08-18 已完成一次适配器生成 CARLA JSON 的本地单场景冒烟，但该配置未启用路线锁定，且未执行 `.xosc` 文件本身；因此不能把 V1 写成“OpenSCENARIO 与 CARLA 无缝对接”。

## 未来优化方向

OpenSCENARIO XML `1.4` 暂不替换当前 1.0 运行目标，后续作为独立的标准交换适配方向：

1. 新增 `custom_json_to_openscenario_exchange_v1_4` 映射版本，不修改现有 1.0 运行适配器。
2. 用 ASAM 1.4 Schema 做结构校验，并维护 1.0/1.4 字段差异和降级策略。
3. 只有在目标工具链明确支持 1.4、单场景执行通过且证据字段完整后，才考虑把 1.4 纳入运行验收。
