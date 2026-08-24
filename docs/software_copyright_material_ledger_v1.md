# 软著材料整理台账 V1

_项目：基于 CARLA 的自动驾驶极端场景生成与仿真测试系统 V1.0；用途：阶段五前置材料整理；不等同于申请提交_

## 台账定位

这份台账把“现在维护的工程底稿”和“正式申请前才冻结的材料”分开。当前只记录真实存在的代码入口、测试结果、运行证据和明确边界，不提前制作最终截图，不把规划能力写成已实现功能。

正式申请材料应以最终冻结提交为准。当前阶段的文档、清单和测试结果用于减少后续整理工作量，不能替代申请表、软件说明书、源代码鉴别材料或主管部门的正式要求。

## 当前冻结识别

| 项目 | 当前记录 | 正式申请前动作 |
|---|---|---|
| 拟登记软件名称 | 基于CARLA的自动驾驶极端场景生成与仿真测试系统 V1.0 | 与最终软件界面、说明书和申请表统一核对 |
| 当前工程基线 | 由 `tools/check_stage5_freeze.cmd` 读取的 Git `HEAD`；当前材料基线为阶段五 M08 链路 | 功能完成后记录并冻结最终 V1.0 提交 |
| 当前运行基线 | CARLA 0.9.16、`Carla666-0916` | 冻结版本后重新做一次环境和版本核对 |
| 当前软件形态 | Python 命令行、JSON/CSV 文件接口、本地单进程 Web 管理入口；Web 已含生成/校验/风险三条任务流程 | 说明书按实际交付形态描述，不虚构多用户产品 |
| 当前主演示 | `tools/stage5_demo.cmd`，默认离线、`carla_connected=false`；实机展示证据另见 ScenarioRunner 关联完整验收 | 冻结版本重新运行并归档最终 `demo_manifest.json`，同时复核实机验收轻量证据 |
| 当前场景库 | 117 个独立场景、351 次来源批次严格验收证据 | 复核库快照、证据等级和路径是否仍与冻结版本一致 |

## 模块材料台账

| 模块 | 代码入口 | 当前可引用材料 | 当前状态 | 正式申请前补充 |
|---|---|---|---|---|
| M01 场景生成 | `tools/generate_seed_dataset.py`、`tools/generate_with_model.py`、`tools/run_diffusion_comparison.py`、`models/`、`training/` | 生成记录、Schema、模型选型报告、四生成器离线对照 | 已验证实现 / 研究原型 | 选定最终展示命令和一组可复现输入输出 |
| M02 约束校验 | `core/scenario_validator.py`、`core/physical_constraints.py`、`tools/check_physical_constraints.py`、`schemas/` | Schema、语义校验、参数级物理约束、配置编译和 JSON 报告 | 已验证实现 | 固定说明书中的正常流程、一个负例和物理约束报告 |
| M03 场景库 | `core/scenario_library.py`、`tools/build_scenario_library.py`、`tools/query_scenario_library.py` | `entries.jsonl`、`index.csv`、质量分析报告、查询回归 | 已验证实现 | 冻结库快照并确认材料中的数量和证据分层 |
| M04 仿真采集 | `scenes/scene_04_parameterized.py`、`core/sensor_pipeline.py`、`core/route_follower.py`、`tools/check_scenario_runner_acceptance.py` | CARLA 0.9.16 运行证据、`metadata.json`、`telemetry.csv`、`acceptance_result.json`；四类传感器/路线/风险单样本通过 | 已验证实现 / 原型 | 冻结版本复核提交哈希和证据路径，重新采集最终截图 |
| M05 风险评估 | `core/risk_metrics.py`、`analysis/` | `heuristic_v2` 分解、风险报告、批次统计 | 已验证实现 | 说明书中标注这是仿真遥测启发式指标，不是事故概率 |
| M06 实验复现 | `batch_runner.py`、`tools/server_*.cmd`、`configs/` | 计划、种子、配置哈希、服务器任务和轻量汇总 | 已验证实现 / 原型 | 整理一条最小复现路径，隐藏服务器内部细节 |
| M07 Web 管理入口 | `tools/web_app.py`、`tools/web_app.cmd`、`tools/scenario_dashboard.py`、`core/web_task_orchestrator.py` | 页面级回归、HTTP 接口、场景库列表/详情、生成/校验/风险表单和任务结果 | 首期 Web 工作流 | 冻结版本采集页面截图；不宣称多用户、权限和场景库写入能力 |
| M08 最小演示编排 | `tools/stage5_minimal_demo.py`、`tools/stage5_demo.cmd`、`docs/scenario_runner_full_acceptance_v1.md` | `demo_manifest.json`、配置、`.xosc`、适配清单、完整验收轻量证据、2 项单元测试 | 阶段五已建立 / 离线原型 + 独立实机证据 | 冻结版本重新运行，作为说明书总入口；实机验收仍需单独复核 |

## 本轮整理验收

_验收日期：2026-08-24；以下结果属于当前工程底稿，正式申请前仍需在 V1.0 冻结提交上重新执行。_

| 检查 | 当前结果 | 证据边界 |
|---|---|---|
| 全量单元测试 | `126` 项通过，`1` 项按预期跳过 | 跳过项依赖可选 Stable-Baselines3；Gymnasium 缺失断言按设计执行，不影响 M01–M08 基础链路，不能据此证明训练能力 |
| Python 编译检查 | `core/`、`tools/`、`scenes/`、`analysis/`、`models/`、`training/`、`tests/` 通过 `compileall` | 只证明模块可编译，不替代 CARLA 实机验收 |
| M08 一键演示 | M01–M08 离线最小链路通过；117 个独立场景、351 条严格验收来源证据 | `carla_connected=false`，未启动 CARLA、未产生新风险结果、未占用 GPU |
| 文档差异检查 | `git diff --check` 通过 | 只检查空白和补丁格式，不代表内容已经成为最终申请材料 |
| Web P0 真实冒烟 | 页面 `200`；生成/校验/风险 `completed`；CARLA 取消 `cancelled` | 只证明本机 Web 任务和显式外部执行边界，不证明在线 CARLA 训练 |
| ScenarioRunner 关联完整验收 | `seed_v1_high_0165`：RGB/Depth/Semantic 各 `200` 帧；Collision 独立状态门通过；路线双车在途率 `1.0`；风险 `40.843/medium`；`13/13` 检查通过 | 同一输入的 XOSC 直执行与 Scene 04 完整验收分层记录；不证明跨地图或批量泛化 |

## 材料分层

### 现在持续维护

- 模块与代码入口映射。
- 输入、输出和失败边界。
- 测试命令、测试结果和提交哈希。
- CARLA 实机证据的目录、版本、种子和严格验收字段。
- M08 `demo_manifest.json` 及其限制字段；阶段五成果索引见 `docs/stage5_material_index_v1.md`。
- 冻结前自动检查命令 `tools/check_stage5_freeze.cmd` 及其 `PASS/FAIL/PENDING` 输出。
- 未完成能力清单：ScenarioRunner 跨地图/批量泛化、RL 泛化、真实性评估、多用户产品化。

### 正式申请前冻结

- 软件名称、版本号和最终功能范围。
- 最终代码提交和运行环境说明。
- 软件说明书中的模块顺序、操作步骤和术语。
- 从冻结版本重新采集的操作截图。
- 申请所需的源代码鉴别材料、文档页数和格式。
- 申请主体、著作权人、开发完成日期等非代码信息。

## 截图清单

P0 已通过。以下 9 张图已从用户截图目录归档到
`artifacts/stage5_web_screenshots_v1/`，作为当前 Web 功能的暂定最终截图。它们仍需在正式 V1.0 冻结提交后复核页面版本、路径和数据口径，才能作为最终申请材料使用。

| 编号 | 截图主题 | 归档文件 | 当前状态 | 采集/使用要求 |
|---|---|---|---|---|
| S01 | Dashboard 首页 | `artifacts/stage5_web_screenshots_v1/Dashboard 首页.png` | 已归档（暂定） | 保留 117 个独立场景、351 条严格验收证据等总览数据 |
| S02 | 场景库筛选页 | `artifacts/stage5_web_screenshots_v1/场景库筛选页.png` | 已归档（暂定） | 保留筛选条件、结果数量和列表内容 |
| S03 | 场景详情页 | `artifacts/stage5_web_screenshots_v1/场景详情页.png` | 已归档（暂定） | 区分 `target_risk_level` 与 `observed_risk`，不混写为实测风险 |
| S04 | 生成页面提交前 | `artifacts/stage5_web_screenshots_v1/生成页面提交前.png` | 已归档（暂定） | 显示生成器、目标风险、天气标签、数量和随机种子 |
| S05 | 生成成功结果 | `artifacts/stage5_web_screenshots_v1/生成成功结果.png` | 已归档（暂定） | 显示完成状态、生成数量和 JSONL 产物 |
| S06 | 校验成功结果 | `artifacts/stage5_web_screenshots_v1/校验成功结果.png` | 已归档（暂定） | 显示 Schema/语义、物理约束和配置编译结果 |
| S07 | 校验失败结果 | `artifacts/stage5_web_screenshots_v1/校验失败结果.png` | 已归档（暂定） | 显示字段路径、错误原因和失败状态 |
| S08 | 风险分析成功结果 | `artifacts/stage5_web_screenshots_v1/风险分析成功结果.png` | 已归档（暂定） | 标注 `observed_risk`、`heuristic_v2` 和证据来源 |
| S09 | 任务管理页 | `artifacts/stage5_web_screenshots_v1/任务管理页.png` | 已归档（暂定） | 保留生成/校验/风险终态，以及 CARLA 显式确认/取消边界 |

### 待正式冻结后补充或复核

| 项目 | 推荐入口 | 当前状态 | 使用边界 |
|---|---|---|---|
| 一键演示成功和输出目录 | `tools/stage5_demo.cmd` | 待补采 | 必须同时保留 `demo_manifest.json`，标注默认离线 |
| CARLA 运行结果 | Scene 04 + `metadata.json` + `acceptance_result.json` | 已有单样本轻量证据 | 只使用严格验收通过的真实记录；正式冻结前复核路径和哈希 |
| OpenSCENARIO 适配产物 | M08 输出目录 | 待补采 | 只能写“最小交换子集”，不写直执行兼容 |

## 证据边界

以下内容可以写入工程材料，但必须带限定：

- 阶段四独立策略运行 `54/54` 严格验收通过，表示当前样本集合的运行质量门通过，不表示 RL 泛化。
- M08 默认离线，`carla_connected=false`，M05 读取历史场景库风险，不产生新的实测风险。
- 风险代理只用于候选筛选和实验排序，不替代 `heuristic_v2`、碰撞回调或路线验收。
- 场景库真实性为 `not_assessed`，不能写成真实道路分布代表库。
- OpenSCENARIO 已完成一条最小 ScenarioRunner 直执行，并有一条关联样本通过 Scene 04 完整验收；仍不能写成跨地图、批量或 XOSC 原生完整语义兼容。

## 正式整理触发条件

只有以下条件基本满足后，才从“前置台账”切换到“正式申请包”：

1. 阶段五核心入口和最终软件范围不再发生结构性变化；
2. M08 演示、Dashboard、必要的 CARLA 实机展示和全量回归均基于同一冻结提交；
3. 软件名称、版本号、模块名称和操作术语已经统一；
4. 项目负责人确认申请主体和登记信息；
5. 再按当期官方申请要求核对格式和提交材料。

在此之前，不提交申请、不制作声称最终版本的截图，也不删除历史证据。
