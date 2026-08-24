# 阶段五成果材料索引 V1

_更新日期：2026-08-24；用途：阶段五系统集成、论文/软著前置整理和证据追溯；不等同于最终申请材料_

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
| 当前清单 SHA-256 | `f1e12575607d45178143d622ac577dfe249e65c69baa1269584d0b071582a824` |
| 当前清单关键计数 | M03 `117` 个场景；M07 `117` 行、`351` 条严格验收来源证据 |

当前 SHA-256 对应 2026-08-24 本机 `Carla666-0916` 环境的一次通过运行。由于 `artifacts/` 不入 Git，正式申请前必须在最终冻结提交上重新运行并更新本表，不得把当前哈希当作最终版本哈希。

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
| M02 约束校验 | `core/scenario_validator.py`、`core/physical_constraints.py`、`core/differentiable_closed_loop.py`、`tools/check_physical_constraints.py`、`tools/run_differentiable_closed_loop.py`、`schemas/` | Schema、语义校验、参数级硬约束、Scene 04 配置编译、Torch 可微代理损失、可选 PyBullet 离散几何校验、负例测试和 P4 JSON manifest | E2 | 静态通过不等于 CARLA 运行通过；代理损失不等于 observed_risk；PyBullet 分支不提供梯度或车辆动力学证据 |
| M03 场景库 | `core/scenario_library.py`、`core/scenario_query.py`、`tools/build_scenario_library.py`、`tools/query_scenario_library.py`、`tools/scenario_dashboard.py` | `entries.jsonl`、`index.csv`、质量报告、CLI/Web 受控查询回归 | E2/E4（历史） | `117` 个独立场景、`351` 条来源证据；结构化条件与白名单关键词可组合；真实性为 `not_assessed` |
| M04 仿真采集 | `scenes/scene_04_parameterized.py`、`core/sensor_pipeline.py`、`core/route_follower.py` | 0.9.16 `metadata.json`、`telemetry.csv`、传感器和路线验收；`seed_v1_high_0165` 完整验收 `acceptance_result.json` | E4（历史）/ E4（2026-08-24） | 完整验收是单样本旁路 CARLA JSON 证据，不等价于 XOSC 原生承载这些语义 |
| M05 风险评估 | `core/risk_metrics.py`、`analysis/` | `heuristic_v2` 分解、历史风险报告和批次统计 | E4（历史） | 启发式仿真指标，不是事故概率；M08 不产生新风险 |
| M06 实验复现/任务编排 | `batch_runner.py`、`core/web_task_orchestrator.py`、`tools/measure_stage5_metrics.py`、`tools/benchmark_stage5_generation_baseline.py`、`tools/server_*.cmd`、`configs/` | 提交哈希、配置/种子、服务器任务或 Web 任务请求 | Web 任务回归、任务 JSON、同 CPU baseline 汇总、指标报告、服务器轻量汇总 | E2/E4（历史） | 离线生成 baseline 已补齐；CARLA 墙钟为执行时间代理；实车路测成本、人工规则编辑计时和行业覆盖率分母仍未建立，90%/11 倍/90% 原始目标不宣称达成 |
| M07 Web 管理入口 | `tools/web_app.py`、`tools/web_app.cmd`、`tools/scenario_dashboard.py`、`core/web_task_orchestrator.py` | 页面级回归、HTTP 接口、场景库列表/详情、生成/校验/风险表单、任务状态和结果 | E2 | 本地单进程 Web 首期，暂无多用户、权限或生产部署 |
| M08 最小演示编排 | `tools/stage5_minimal_demo.py`、`tools/stage5_demo.cmd` | `demo_manifest.json`、静态配置、`.xosc`、适配清单；完整实机证据另见 ScenarioRunner 关联验收文档 | E2 | M08 默认离线；实机证据必须引用独立验收 manifest，不由一键离线演示自动产生 |

证据等级定义见 [`stage4_quality_gate_and_experiment_closure_v1.md`](stage4_quality_gate_and_experiment_closure_v1.md)。M08 清单只汇总 M03/M05/M07 的历史或静态证据，不提升其证据等级。

## 相关材料入口

| 材料 | 用途 |
|---|---|
| [`stage5_minimal_demo_and_interface_catalog_v1.md`](stage5_minimal_demo_and_interface_catalog_v1.md) | 一键链路、接口顺序和验收条件 |
| [`stage5_user_operation_guide_v1.md`](stage5_user_operation_guide_v1.md) | 操作步骤、静态检查和真实运行边界 |
| [`software_copyright_material_ledger_v1.md`](software_copyright_material_ledger_v1.md) | 软著前置台账、S01–S09 截图归档和冻结触发条件 |
| [`software_copyright_module_mapping_v1.md`](software_copyright_module_mapping_v1.md) | M01–M08 模块职责与软著章节映射 |
| [`software_copyright_interface_spec_v1.md`](software_copyright_interface_spec_v1.md) | 命令入口、数据契约、输出和异常边界 |
| [`stage4_quality_gate_and_experiment_closure_v1.md`](stage4_quality_gate_and_experiment_closure_v1.md) | 阶段四证据等级和研究结论边界 |
| [`scenario_runner_full_acceptance_v1.md`](scenario_runner_full_acceptance_v1.md) | ScenarioRunner 直执行与 Scene 04 完整传感器/路线/风险双层证据 |
| [`stage5_freeze_preflight_v1.md`](stage5_freeze_preflight_v1.md) | V1.0 冻结前自动检查项和 PENDING 清单 |
| [`stage5_metrics_baseline_v1.md`](stage5_metrics_baseline_v1.md) | 计划书成本、效率和覆盖率测量口径、同 CPU baseline 与证据边界；可由 `tools\\run_stage5_metrics_baseline.cmd` 重建 |
| [`stage5_external_cost_and_coverage_estimate_v1.md`](stage5_external_cost_and_coverage_estimate_v1.md) | 公开资料锚点、实车成本三档区间、行业覆盖率分母边界、`0.960341x` 解释和优化实验顺序；不替代项目实测 |

## 正式冻结前动作

1. 冻结 V1.0 功能范围、软件名称、模块术语和最终提交。
2. 在冻结提交上重新运行 M08、全量测试和 `compileall`。
3. 将新的 `demo_manifest.json` SHA-256、运行日期和环境版本更新到本索引。
4. 复核 `artifacts/stage5_web_screenshots_v1/` 中的 S01–S09 Web 截图，并另行采集一键演示、CARLA 实机结果和 OpenSCENARIO 适配产物截图；截图不得使用未冻结版本作为最终申请证据。
5. 依据当期官方要求整理软件说明书、源代码鉴别材料和申请主体信息。

在正式冻结前，本索引和 M08 清单属于工程底稿，不代表软著已经申请或登记。
