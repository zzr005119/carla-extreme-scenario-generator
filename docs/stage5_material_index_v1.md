# 阶段五成果材料索引 V1

_更新日期：2026-08-23；用途：阶段五系统集成、论文/软著前置整理和证据追溯；不等同于最终申请材料_

## 索引定位

本索引把 M01–M08 的代码入口、当前可引用证据、阶段五一键演示清单和正式冻结前动作集中到一个入口。它只登记已经存在或可以由仓库命令重建的材料，不把规划能力写成已完成能力。

阶段五默认演示是离线链路：它读取一个场景记录，完成校验、配置编译、场景库查询、静态 OpenSCENARIO 适配和 Dashboard 数据核对，然后写出 `demo_manifest.json`。默认不连接 CARLA，不产生新的 `observed_risk`，也不启动 GPU 任务。

## 主审计入口

| 项目 | 当前记录 |
|---|---|
| 一键入口 | `tools/stage5_demo.cmd` |
| 核心编排器 | `tools/stage5_minimal_demo.py` |
| 默认产物目录 | `artifacts/stage5_minimal_demo_v1/`（被 Git 忽略，可重建） |
| 主清单 | `artifacts/stage5_minimal_demo_v1/demo_manifest.json` |
| 当前清单格式 | `stage5_minimal_demo_v1_manifest` / `v1` |
| 当前运行模式 | `offline_static_and_evidence` |
| 当前 CARLA 状态 | `carla_connected=false`；`new_carla_risk_evaluation=false` |
| 当前清单 SHA-256 | `7d0e566bb45d75cf18fe946abd2a09ac57c30f2c938d05e5e002819c3e40abfd` |
| 当前清单关键计数 | M03 `117` 个场景；M07 `117` 行、`351` 条严格验收来源证据 |

当前 SHA-256 对应 2026-08-23 本机 `Carla666-0916` 环境的一次通过运行。由于 `artifacts/` 不入 Git，正式申请前必须在最终冻结提交上重新运行并更新本表，不得把当前哈希当作最终版本哈希。

## 重建命令

在项目根目录执行：

```powershell
tools\stage5_demo.cmd --output-dir artifacts\stage5_minimal_demo_v1
Get-FileHash artifacts\stage5_minimal_demo_v1\demo_manifest.json -Algorithm SHA256
```

验收时至少核对：

1. `demo_manifest.json` 的 `format` 为 `stage5_minimal_demo_v1_manifest`；
2. `execution_mode` 为 `offline_static_and_evidence`；
3. `carla_connected` 和 `stages.M05_risk_evidence.new_carla_risk_evaluation` 均为 `false`；
4. `stages.M02_validation_and_compile.status`、`stages.M04_static_simulation_adapter.status`、`stages.M07_dashboard_data.status` 和 `stages.M08_demo_orchestrator.status` 均为 `passed`；
5. M03 场景条目数与 M07 `row_count`、`entry_count`、`summary_entry_count` 一致；
6. 输出目录中存在输入副本、编译配置、`.xosc`、`.carla.json`、适配清单和主清单。

## M01–M08 材料地图

| 模块 | 主要代码入口 | 当前可引用材料 | 证据等级 | 当前边界 |
|---|---|---|---|---|
| M01 场景生成 | `tools/generate_seed_dataset.py`、`tools/generate_with_model.py`、`tools/run_diffusion_comparison.py`、`models/`、`training/` | `data/scenarios/seed_v1/`、四生成器离线对照、`docs/generator_diffusion_comparison_v1.md`、模型选型报告 | E2 | 参数生成和离线对照，不代表实测风险控制；Diffusion 含设计区间投影 |
| M02 约束校验 | `core/scenario_validator.py`、`core/physical_constraints.py`、`tools/check_physical_constraints.py`、`schemas/` | Schema、语义校验、参数级物理约束、Scene 04 配置编译、负例测试和 JSON 报告 | E2 | 静态通过不等于 CARLA 运行通过；物理指标为运行前近似 |
| M03 场景库 | `core/scenario_library.py`、`core/scenario_query.py`、`tools/build_scenario_library.py`、`tools/query_scenario_library.py`、`tools/scenario_dashboard.py` | `entries.jsonl`、`index.csv`、质量报告、CLI/Web 受控查询回归 | E2/E4（历史） | `117` 个独立场景、`351` 条来源证据；结构化条件与白名单关键词可组合；真实性为 `not_assessed` |
| M04 仿真采集 | `scenes/scene_04_parameterized.py`、`core/sensor_pipeline.py`、`core/route_follower.py` | 0.9.16 `metadata.json`、`telemetry.csv`、传感器和路线验收 | E4（历史） | 真实运行必须单独启动并重新检查版本、服务和严格验收 |
| M05 风险评估 | `core/risk_metrics.py`、`analysis/` | `heuristic_v2` 分解、历史风险报告和批次统计 | E4（历史） | 启发式仿真指标，不是事故概率；M08 不产生新风险 |
| M06 实验复现/任务编排 | `batch_runner.py`、`core/web_task_orchestrator.py`、`tools/server_*.cmd`、`configs/` | 提交哈希、配置/种子、服务器任务或 Web 任务请求 | Web 任务回归、任务 JSON、服务器轻量汇总 | E2/E4（历史） | 离线任务使用 CPU；CARLA 任务仅外部显式确认，服务器结果不以大文件或模型权重形式入 Git |
| M07 Web 管理入口 | `tools/web_app.py`、`tools/web_app.cmd`、`tools/scenario_dashboard.py` | 页面级回归、HTTP 接口、场景库列表、详情和任务状态 | E2 | 本地单进程 Web，暂无多用户、权限或产品化部署 |
| M08 最小演示编排 | `tools/stage5_minimal_demo.py`、`tools/stage5_demo.cmd` | `demo_manifest.json`、静态配置、`.xosc`、适配清单 | E2 | 最小交换适配，不证明 ScenarioRunner 直执行 |

证据等级定义见 [`stage4_quality_gate_and_experiment_closure_v1.md`](stage4_quality_gate_and_experiment_closure_v1.md)。M08 清单只汇总 M03/M05/M07 的历史或静态证据，不提升其证据等级。

## 相关材料入口

| 材料 | 用途 |
|---|---|
| [`stage5_minimal_demo_and_interface_catalog_v1.md`](stage5_minimal_demo_and_interface_catalog_v1.md) | 一键链路、接口顺序和验收条件 |
| [`stage5_user_operation_guide_v1.md`](stage5_user_operation_guide_v1.md) | 操作步骤、静态检查和真实运行边界 |
| [`software_copyright_material_ledger_v1.md`](software_copyright_material_ledger_v1.md) | 软著前置台账、截图计划和冻结触发条件 |
| [`software_copyright_module_mapping_v1.md`](software_copyright_module_mapping_v1.md) | M01–M08 模块职责与软著章节映射 |
| [`software_copyright_interface_spec_v1.md`](software_copyright_interface_spec_v1.md) | 命令入口、数据契约、输出和异常边界 |
| [`stage4_quality_gate_and_experiment_closure_v1.md`](stage4_quality_gate_and_experiment_closure_v1.md) | 阶段四证据等级和研究结论边界 |
| [`stage5_freeze_preflight_v1.md`](stage5_freeze_preflight_v1.md) | V1.0 冻结前自动检查项和 PENDING 清单 |

## 正式冻结前动作

1. 冻结 V1.0 功能范围、软件名称、模块术语和最终提交。
2. 在冻结提交上重新运行 M08、全量测试和 `compileall`。
3. 将新的 `demo_manifest.json` SHA-256、运行日期和环境版本更新到本索引。
4. 另行采集 Dashboard、M02 负例、CARLA 实机结果和风险分析截图；截图不得使用未冻结版本作为最终申请证据。
5. 依据当期官方要求整理软件说明书、源代码鉴别材料和申请主体信息。

在正式冻结前，本索引和 M08 清单属于工程底稿，不代表软著已经申请或登记。
