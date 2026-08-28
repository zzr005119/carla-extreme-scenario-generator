# PROJECT.md — 项目状态总览

> 本文件由 Codex agent 自动维护，仅记录当前有效状态。

## 基本信息
- **项目名称**：基于生成式AI的自动驾驶极端场景库构建与仿真测试平台
- **软著登记名称**：基于CARLA的自动驾驶极端场景生成与仿真测试系统 V1.0
- **终极目标**：完成可运行的软件 V1.0，并申请一项计算机软件著作权登记
- **GitHub**：https://github.com/zzr005119/carla-extreme-scenario-generator
- **源码仓库**：`D:\Xx\竞赛\大创实施ing`
- **CARLA 0.9.16 当前验证基线**：`F:\Carla\carla-0.9.16`
- **本机项目 Anaconda 环境**：`D:\ANACONDA\envs\Carla666-0916`
- **CARLA 运行输出**：`F:\Carla\output-0.9.16`
- **服务器运行仓库**：`/home/zhaozirong/projects/carla-extreme-scenario-generator`
- **内网 Git 远端**：`lab` → `zhaozirong@192.168.110.170:/home/zhaozirong/git/carla-extreme-scenario-generator.git`
- **CARLA 0.9.15 历史证据**：`artifacts/carla_0915_runtime_evidence/`（本地忽略目录）
- **最后更新**：2026-08-28

## 当前阶段
**大创已完成阶段四“仿真平台与对抗性测试代理”的硬质量门和当前证据收口，现转入阶段五“系统集成与成果产出”。阶段四形成了 OpenSCENARIO 最小交换适配、对抗性代理契约、闭环编排、Gymnasium/SB3 工程链路、非学习基线、冻结代理训练与真实 CARLA 独立评估。18 个独立策略 pair 的 `54/54` 条运行通过版本、RGB、服务健康、`heuristic_v2` 和路线严格验收；LHS/high 的 9 个独立候选完成边界校准。现有证据证明工程链路可复现，但不证明 SAC 或 rule-guided LHS 的普遍优势，不支持把风险代理升级为实测风险或在线训练 reward。阶段四综合结论见 `docs/stage4_quality_gate_and_experiment_closure_v1.md`。**

当前完成的是一套 **CARLA 极端场景仿真 Demo**，它是后续生成式 AI 场景生成、物理校验和自动化测试的仿真底座，不是项目终点，也不是最终软件封版。风险指标 V2 已完成离线分析和 CARLA 实机回归。

CARLA 0.9.16 独立环境 `Carla666-0916` 已安装 Python API 0.9.16；客户端/服务端版本、`Town10HD_Opt` 地图加载、项目配置静态校验和同一冻结场景三个交通种子的完整严格回归均已通过。从 2026-08-15 起，后续新增实验统一使用 0.9.16。CARLA 实机任务遵循“服务器优先、连接或健康检查失败后回退本机”的规则；服务器使用配置中的 `Carla666-0916`，本机固定使用 `D:\ANACONDA\envs\Carla666-0916`。CARLA 0.9.15 程序、旧运行副本、安装包、旧 Conda 环境和本机残留 Python 包均已删除；历史 JSON、CSV、日志和说明文件仅作为证据保留，历史原始传感器帧不再保留。
服务器已部署并实测导入 `AdditionalMaps_0.9.16.tar.gz`，可用地图数为 `21`，`Town06` 与 `Town07` 已成功加载验证。

阶段一中的 CARLA 环境、场景参数化、多传感器采集和批量验证已完成；生成式 AI 相关文献已完成第一轮收集和模型选型调研（56 篇索引、46 篇本地 PDF），公开数据集调研仍需补齐。阶段二已完成 15 维统一表示、种子数据集、条件 GMM、轻量条件表格 CVAE、多随机种子训练、离线评估、受控重复性验证、三生成器 108 次严格验收、风险反馈 V1—V5、碰撞边界主动补样、物理交互派生特征增强、候选重评分和配对实机验证；冻结的 27 维随机森林代理保留服务器模型权重与本地轻量结论。阶段三从统一场景库 V1 的数据契约和质量评估入口开始。

## 整体阶段顺序
1. ✅/▶ **基础调研与环境搭建**：CARLA、Python、Git/GitHub 和仿真底座已完成；生成式 AI 文献第一轮收集和模型选型已完成，公开数据集收集与预处理仍需补齐。
2. ✅ **生成式 AI 模型与物理约束**：场景 Schema、独立校验器、种子数据集、LHS/GMM/CVAE、确定性控制器、严格验收、风险反馈 V1—V5、物理增强代理与配对实机验证均已形成可复现工程基线；潜空间条件 Flow 延后评估，不作为阶段二完成条件。
3. ✅ **极端场景库与质量评估**：统一条目、来源追踪、哈希去重、真实性/多样性/危险性/可执行性指标、结构化检索索引、质量分析基线、接口回归门槛、软著模块映射、接口规格和 Dashboard 页面级回归均已完成；软著演示截图后置到正式申请准备阶段。
4. ✅ **仿真平台与对抗性测试代理**：硬运行质量门和当前证据已收口；OpenSCENARIO 最小交换、ScenarioRunner 单场景直执行、同样本 Scene 04 完整多传感器/路线/风险验收、代理契约、闭环编排、Gymnasium/SB3 工程链路、冻结代理、非学习基线、真实 CARLA 独立评估、重复测量和 LHS/high 边界校准均已形成可复现基线。RL 泛化、CARLA 在线训练和跨地图/批量 ScenarioRunner 语义仍未完成，不作为已实现能力。
5. ▶ **系统集成与成果产出**：当前阶段。整合“生成—管理—测试—评估”冻结入口，统一质量门与证据引用，准备论文、软著和结题材料。

## 新总体目标与完成边界
- **当前总目标**：先完成可访问、可演示、可扩展的 Web 管理系统，再继续补齐计划书中除明显夸张或特别耗时目标外的核心技术目标；Web 系统不是项目终点。
- **Web 首期完成要求**：统一入口、Dashboard 首页、场景库列表、场景详情、117 个独立场景和 351 条严格验收来源证据的展示；生成、校验、风险分析已接入可操作表单、任务轮询和结构化结果，CARLA 仍保持显式外部执行。
- **研究目标完成要求**：保留 LHS/GMM/CVAE 工程基线，补做可验证的物理约束模块、生成模型小规模对照、受控条件检索和自动风险分析/测试编排；每项结论必须区分静态校验、离线结果和 CARLA 实机证据。
- **规模目标降级规则**：计划书中的 10,000 场景扩库改为可扩展生成与入库流水线，并以当前 117 条质量门快照作为已验证规模；90% 成本降低、11 倍效率、90% 覆盖率在同口径基线和实测完成前不得宣称达成。
- **明确后置/不作为当前完成条件**：CARLA 在线 RL 泛化、ScenarioRunner 跨地图/批量完整语义、自然语言自由检索、真实 PyBullet 可微物理闭环和跨地图真实性结论；本阶段已完成一条原生直执行及一条关联样本的 Scene 04 完整验收，但不冒充泛化能力。
- **封板决策**：当前不把既有命令行 Demo 提交冻结为最终 V1.0；待 Web 首期和核心目标清单收口后，再统一做最终冻结、截图和软著申请材料。

## 技术路线与选型
- **Web 服务**：首期使用 Python 标准库 `http.server`，在现有 `scenario_dashboard.py` 数据契约上增加 `tools/web_app.py` 统一入口；任务状态由 `core/web_task_orchestrator.py` 持久化到独立 JSON 目录。后续有多用户、权限或高并发需求时，再评估迁移 FastAPI。
- **页面层**：服务端输出轻量 HTML/CSS/原生 JavaScript；复用现有 JSON/CSV 场景库，不引入 React/Vue 和微服务，保持单机演示与软著取证简单可复现。
- **数据层**：场景库继续使用 `entries.jsonl`、`index.csv`、`summary.json`；不立即迁移数据库。任务记录确有持久化需求时，新增 SQLite 任务表，不改动既有场景证据格式。
- **生成模型**：LHS 作为工程基线，条件 GMM 作为统计对照，表格 C-VAE 作为当前生成式 AI 主线；轻量条件表格 Diffusion 已完成小规模可比实验，不替换已验证基线。
- **物理约束**：先实现可单元测试、可报告的参数级物理约束校验；PyBullet 可作为独立适配模块，不能在没有实测证据时写成已完成的可微训练系统。
- **仿真与风险**：CARLA `0.9.16` + `Carla666-0916`，复用 OpenSCENARIO 1.0 最小交换适配和 `heuristic_v2` 风险代理；`target_risk_level` 仅是设计条件，`observed_risk` 才是实测结果。
- **计算资源**：Web、文档、静态校验和离线分析默认使用 CPU；需要 GPU 的模型实验优先使用 GPU1，但先检查并避让现有 TensorRT 服务；GPU0 的 vLLM 不修改；多场景 RL 已完成 CPU 计划生成和 dry-run，真实训练仍须服务器显式启动 CARLA 后运行。

## 阶段推进清单
> 待办区只保留尚未完成的事项。完成一项后，从本清单删除，并在“当前工作”或对应文档中保留一条证据索引；`⏸` 表示明确暂缓，不计入当前完成条件。

1. ▶ **S5-WEB-03 Web 展示取证**：9 张 Web 功能截图已暂定归档到 `artifacts/stage5_web_screenshots_v1/` 并登记到软著台账；正式 V1.0 冻结后仍需复核截图与提交版本一致，并补采一键演示、CARLA 实机和 OpenSCENARIO 证据图。
2. ⏸ **S5-SCALE-01 10,000 场景扩库**：降级为可扩展流水线设计和当前规模质量验证，不作为阶段五阻塞项。
3. ▶ **S5-RL-01 CARLA 在线 RL**：修复后的 SAC `256` 步 canary 已在服务器 GPU1 完成，质量门 `15/15` 通过，`265/265` 条 CARLA 执行严格通过，模型与 checkpoint 已保存于独立 retry 目录。原 `10,000` 步主训练保留 `1,000` 和 `2,000` 步 checkpoint；当前已由阶段 03 从 `2,000` 步 checkpoint 恢复运行，目标总步数 `10,000`，作业 `carla-rl-03-resume-sac-10000-v1_20260828_112459`。训练完成后仍需运行质量门和冻结 dev/test 评估，当前不能写成 RL 泛化结论。协议见 `docs/carla_online_rl_multiscene_v1.md`。
4. ✅ **S5-XOSC-01 ScenarioRunner 单场景直执行与关联完整验收**：服务器 CARLA 0.9.16 + ScenarioRunner 0.9.16 已完成 `seed_v1_high_0165` 原生 XOSC 加载、Storyboard 运行和清理；同一输入的 Scene 04 旁路配置又通过 RGB/Depth/Semantic/Collision、waypoint 路线、服务健康、风险和清理统一门。纯 XOSC 无 criteria，不产生风险 JSON/JUnit，仍不宣称 XOSC 原生承载完整语义；证据见 `docs/scenario_runner_direct_execution_v1.md` 和 `docs/scenario_runner_full_acceptance_v1.md`。
5. ✅ **S5-PYBULLET-01 P4 边界收口**：`core/differentiable_closed_loop.py` 已形成 Torch 可微运动学代理、碰撞/安全间距/控制平滑/加速度越界四项软损失、`L_adv + lambda_1 L_physics + lambda_2 L_control` 组合点、可选 PyBullet DIRECT 几何接触回放和硬约束质量门；`tools/p4_differentiable_boundary.cmd` 输出统一 P4 manifest。固定环境 `Carla666-0916` 的 `tests.test_runtime_adapters` 为 `9/9` 通过；服务器 PyBullet `3.2.7` 增强回放已验证，contact probe 报告 `63` 个负间距步和 `41` 个接触点。真实 PyBullet 可微刚体、车辆动力学闭环和训练接入仍未完成，边界见 `docs/differentiable_closed_loop_v1.md`，服务器记录见 `docs/p4_server_validation_v1.md`。
6. ⏸ **S5-ABL-01 完整消融实验与结题报告**：放在 Web、在线 RL、ScenarioRunner 和可微闭环证据收口后统一设计、执行和写作。

## 计划书目标映射
| 计划书目标 | 当前处理 | 验收要求 |
|---|---|---|
| 生成式 AI 场景生成 | 已有 LHS/GMM/CVAE；Diffusion 小规模对照已完成 | 生成记录、Schema 校验、统一离线指标和代理排序 |
| 物理约束与可执行性 | 参数级硬约束 + Torch 可微运动学软损失 + PyBullet 离散校验边界已完成；真实 PyBullet 可微训练和生成模型训练接入后置 | P4 manifest、梯度检查、PyBullet 可用性/接触报告、失败报告、CARLA 配置编译 |
| 极端场景库 | 已完成 117 条独立场景快照 | 证据链、去重、查询和质量门 |
| 多维质量评估 | 已有危险性/可执行性/重复性等基线 | 明确 `not_assessed` 的真实性边界 |
| 对抗性测试与自动风险分析 | 已有代理闭环和 `heuristic_v2` 结果回填 | Web 任务接口 + 实机证据分级 |
| CARLA/OpenSCENARIO 适配 | 已完成最小交换子集、一条 ScenarioRunner 直执行和一条关联完整验收 | 不宣称跨地图/批量或 XOSC 原生完整多传感器/风险语义 |
| Web 自动化测试平台 | 当前优先建设 | 页面、API、任务状态和结果展示回归 |
| 规模化扩库与宣传指标 | 降级为可扩展设计/待测基线 | 未完成同口径实测前不得宣称达成 |

## 软著材料同步要求
- Web 每新增一个可见模块，就同步更新 `docs/software_copyright_module_mapping_v1.md`、`docs/software_copyright_interface_spec_v1.md` 和 `docs/software_copyright_material_ledger_v1.md` 的入口、功能、证据和边界。
- Web 页面截图已先按暂定最终版本归档到 `artifacts/stage5_web_screenshots_v1/`；正式申请仍需基于最终冻结提交复核截图、操作说明、代码鉴别材料和申请主体信息，当前不声称已完成软著申请。

## 当前 Demo 子阶段
1. ✅ 极端天气、多危险叠加和行人突发场景。
2. ✅ RGB、Depth、SemSeg 和碰撞传感器集成。
3. ✅ JSON 参数化、同步步进、批次运行和重复统计。
4. ✅ 风险指标 V2、结果图表与离线分析报告。
5. ✅ V2 实机回归；✅ 第一版生成模型离线基线；✅ 两轮 CVAE 生成样本抽样验证；✅ 第一轮 36 次多种子问题诊断；✅ 路线失败诊断；✅ 确定性 waypoint 控制器；✅ V3 九次实机严格验收；✅ V4 三十六次实机严格验收；✅ 三生成器 108 次仿真、严格验收与阶段结论冻结；✅ 风险反馈数据集 V1 与代理基线；✅ 代理误差和排序稳定性诊断 V1；✅ 反馈候选 81 次外部验证；✅ 风险反馈数据集、风险代理和碰撞通道诊断 V2；✅ 双通道离线评分与 54 次配对计划；✅ 双通道 54 次配对实机验证；✅ 风险反馈 V3 合并与复训；✅ V3 候选池重评分；✅ 碰撞边界主动补样 V1 的 54 次多传感器实机验证；✅ 风险反馈 V4、V3/V4 对比和风险分数拆解校准 V1；✅ 物理交互派生特征增强 V1；✅ 1536 候选增强代理重评分；✅ 物理增强配对验证 54/54 严格验收与 9/9 配对分析；✅ 风险反馈 V5 复训与 27 维代理冻结；✅ 场景库 V1 数据契约、117 场景扩库与离线查询入口；✅ 场景库质量分析基线；✅ 构建与查询接口回归测试及质量门冻结；✅ 软著系统模块映射与接口规格；✅ M07 Dashboard 页面级回归；✅ OpenSCENARIO/CARLA 适配器 4.1；✅ 对抗性测试代理 V1 契约；✅ 闭环编排 V1 单步真实冒烟；✅ 闭环编排 V1 多步真实冒烟；✅ 编排失败中止、无效候选恢复与重复场景截断测试；✅ Gymnasium 外壳、服务器 `check_env` 与环境级 CARLA 冒烟；✅ 分层场景采样与四类非学习离线基线；✅ reward V2；✅ 四策略 60/60 CARLA 严格对照；✅ Stable-Baselines3 兼容性与低成本训练入口；✅ 冻结 27 维风险代理训练执行器；✅ 多随机种子代理基准；✅ SAC/rule-guided LHS 12 分层 CARLA 独立评估；✅ 3 个原始 pair 的重复 Traffic Manager 种子复验；✅ 6 个未覆盖分层扩展的 18/18 CARLA 严格验收；✅ 18 个独立 pair 合并统计；✅ 阶段四质量门审计；✅ 2 个优先分层的 18/18 重复测量；✅ LHS/high 候选参数与风险代理排序边界复核、9 个独立候选严格验收与校准 V2；✅ 阶段四质量门和实验结论收口；✅ S5-CORE-02 Diffusion 四生成器 512 条离线对照与统一排序验收。

## CARLA Demo 已验证成果
- 场景脚本：`scene_01` 至 `scene_04`。
- 多传感器：RGB、Depth、Semantic Segmentation 和 Collision。
- 场景行为：暴雨、浓雾、夜间、前车急刹、行人突然冲出、全图绿灯。
- 数据输出：每次运行生成配置快照、`metadata.json`、`telemetry.csv` 和传感器文件。
- 仿真控制：同步模式、`0.05 s` 固定步长、Traffic Manager 种子和世界状态恢复。
- 批量能力：五组变体、分轮递增种子、逐次日志、运行计划、明细 CSV 和聚合 CSV。
- 完整批次：`15/15` 成功，传感器完整率和 CARLA 服务健康率均为 `100%`，共记录 `9000` 个相机帧。
- 最终批次目录：`F:\Carla\test\output\batches\rainy_night_variants\20260806_161712`。
- V2 离线分析：`short_headway` 以 `61.462 ± 0.146` 排名第一；`dense_fog` 和 `fast_pedestrian` 相比 baseline 分别提高 `2.030` 和 `3.511` 分。
- V2 分析目录：`F:\Carla\test\output\batches\rainy_night_variants\20260806_161712\risk_v2_analysis`。
- V2 实机回归：运行 `20260812_120439` 完成，`heuristic_v2` 得分 `63.456`、等级 `high`，无碰撞，RGB/Depth/SemSeg 各 `200` 帧，传感器写盘完成，CARLA 服务健康检查通过。

## 当前工作
- 软著前置材料整理 V1 已完成：新增 `docs/software_copyright_material_ledger_v1.md`、`docs/stage5_user_operation_guide_v1.md` 和 `docs/stage5_material_index_v1.md`；模块映射、接口规格和阶段五成果索引已统一到 M01–M08 口径。当前不制作最终申请截图、不提交软著，待 V1.0 功能和提交冻结后统一采集、核对与整理。
- V1.0 冻结前检查已建立：`tools/check_stage5_freeze.cmd` 覆盖材料入口、M01–M08 口径、M08 清单契约、117/351 场景库计数、产物哈希、Carla666-0916 环境和工作区状态；当前内容检查 `30 PASS / 0 FAIL`，加 `--require-clean` 的冻结模式为 `31 PASS / 0 FAIL`，正式提交、最终截图和申请主体信息仍为 PENDING。
- 阶段五 M08 一键最小演示链路 V1 已建立：`tools/stage5_demo.cmd` 优先使用 `Carla666-0916` 环境，默认离线串联 M01 场景记录、M02 校验/编译、M03 场景库查询、M04 OpenSCENARIO 静态适配、M05 历史风险证据、M06 复现清单和 M07 Dashboard 数据校验，输出统一 `demo_manifest.json`；默认 `carla_connected=false`，不隐式启动 CARLA。接口清单见 `docs/stage5_minimal_demo_and_interface_catalog_v1.md`。
- 阶段四综合质量门与实验结论已收口：硬运行门通过，工程接口门按证据等级归档，SAC/rule-guided LHS 泛化、风险代理升级和 CARLA 在线训练仍明确为未证明；ScenarioRunner 已完成一条最小 XOSC 实机直执行，但完整多传感器/风险语义仍后置。报告见 `docs/stage4_quality_gate_and_experiment_closure_v1.md`。
- 当前进入阶段五，优先整合“生成、校验、场景库、仿真、风险分析、实验编排、Web Dashboard”的冻结入口，并准备软著、论文和结题材料；不继续无目标扩展阶段四 CARLA 实验。
- 多场景 RL 泛化准备 V1 已完成：`core/carla_rl_plan.py` 和 `tools/prepare_carla_rl_multiscene_plan.py` 将场景库固定为 `train/dev/test=66/27/24`，按 12 个生成器×风险分层分配，并检查 canonical ID/scenario hash 泄漏；`tools/train_carla_rl.py` 保留单记录冒烟兼容，同时支持 SAC/PPO、多场景 sampler、`1,000` 步 checkpoint、`.zip` resume、run/checkpoint manifest；`tools/evaluate_carla_rl_multiscene.py` 支持冻结 dev/test split。服务器操作已拆为 00 准备、01 SAC 256 canary、02 SAC 10,000 主训练、03 断点恢复、04 dev 评估、05 test 验收六个独立入口；canary 已由 `tools/check_carla_rl_training.py` 验收通过，当前阶段 03 正在从 `2,000` 步恢复，训练质量门和 dev/test 评估结论待任务完成后回收。说明见 `docs/carla_online_rl_multiscene_v1.md`。
- Web 产品化首期 P0 已完成：统一入口 `tools/web_app.py`/`tools/web_app.cmd` 复用场景库 API，提供 Dashboard、场景列表、详情、受控查询、健康检查，以及生成/校验/风险分析三条可操作表单流程；提交后由 CPU worker 执行，页面轮询任务状态并展示成功产物、结构化失败和取消结果。已修复任务页内联 JavaScript 转义错误，并用 Edge 无界面浏览器确认 `/api/tasks` 结果可实际渲染到任务表；任务结果列已固定宽度并单行省略，完整内容通过悬浮提示查看。校验支持 JSON/JSONL、物理约束和可选 CARLA 配置编译；CARLA 任务显式确认或取消后仍转交外部入口，不由 Web 启动。全量回归为 `145 passed / 1 skipped`，真实 HTTP 冒烟覆盖页面 `200`、三类任务完成、CARLA 取消和 `carla_connected=false`。说明见 `docs/stage5_web_product_flow_v2.md`。
- 后置能力入口已建立并分级：`tools/train_carla_rl.py` 仍是 Gymnasium/SB3 依赖预检与显式在线训练门；`tools/run_scenario_runner.py` 已支持 TM 端口、同步、地图和 ego 等参数，并完成一条真实单场景直执行；`core/differentiable_closed_loop.py` 提供 Torch 可微运动学及可选 PyBullet 离散校验。缺少可选依赖或 CARLA 服务时，入口明确返回阻塞/预检状态。
- `S5-CORE-01` 参数级物理约束 V1 已完成：`core/physical_constraints.py` 和 `tools/check_physical_constraints.py` 提供有限值、时间窗口、行人横穿完成时间和运动学边界检查，并输出带字段路径/错误代码/指标的 `physical_constraint_report_v1`；本机和服务器 `Carla666-0916` 均完成种子数据集 `256/256` 条硬约束通过、`0` 条非法。该结果是 CPU 静态参数验证，不产生新的 CARLA 风险结果；说明见 `docs/physical_constraints_v1.md`。
- `S5-PYBULLET-01` P4 边界收口：`build_p4_boundary_manifest` 将可微 Torch 代理、`L_adv + lambda_1 L_physics + lambda_2 L_control` 组合点、PyBullet 离散回放和参数级硬门汇总为可审计 JSON；固定环境本机适配测试为 `9/9`，服务器 PyBullet `3.2.7` contact probe 为 `63` 个负间距步、`41` 个接触点。本机缺少可选 PyBullet 按契约跳过；该成果证明接口和离散边界，不证明真实 PyBullet 可微刚体、CARLA 车辆物理或生成模型/RL 训练接入；说明见 `docs/differentiable_closed_loop_v1.md` 和 `docs/p4_server_validation_v1.md`。
- `S5-PYBULLET-02` P4.1 MJX-JAX 最小 PoC 已完成：服务器 Linux CPU 正式证据使用 `/home/zhaozirong/software/envs/MJXPoC-Linux`；GPU1 另有独立 `/home/zhaozirong/software/envs/MJXPoC-Linux-GPU1`，不修改正在运行的 SAC/CARLA。CPU `horizon=32, force=4` 下，前向梯度与有限差分相对误差为 `2.53e-10`，与原生 MuJoCo 轨迹最大位置误差为 `1.11e-16 m`；GPU1 同口径设备为 `cuda:0`（物理 GPU1），误差为 `1.42e-10`，JAX 额外显存约 `704 MiB`。`horizon=128, force=5` 高接触压力测试中，CPU/GPU 损失差为 `2.63e-13`、梯度差为 `9.06e-14`，两者均通过原生 MuJoCo 对齐门。有限差分坐标已固定在执行器约束区间内部，避免边界裁剪造成单边扰动。源码复核确认 `solver_iterations=1` 可绕过动态 `while_loop` 并恢复 `jax.grad`，但该路线尚未通过高接触/摩擦精度门；新增 `loss_with_custom_vjp()`，在正常多次迭代前向上用 `jacfwd` 实现可审计的 forward-over-reverse VJP，CPU/GPU 服务器复现中与 `jacfwd` 最大绝对差均为 `0`，尚未完成高维性能评估。GPU1 仅允许显式 `CUDA_VISIBLE_DEVICES=1`、JAX 显存上限和短时受控测试；尚未接入 CVAE、Diffusion、RL 或 CARLA；证据见 `docs/p4_1_mjx_differentiable_poc_v1.md` 和 `artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_custom_vjp.json`、`manifest_server_gpu1_custom_vjp_v2.json`、`manifest_server_cpu_high_contact_v1.json`、`manifest_server_gpu1_high_contact_v1.json`。
- `S5-PYBULLET-02` 性能基准已补充：`horizon=128`、batch `1/4/16` 的前向吞吐为 CPU `53.824/104.978/372.029` 次/秒、GPU1 `13.630/69.466/241.449` 次/秒；自定义 VJP 吞吐为 CPU `5.279/6.386/10.303` 次/秒、GPU1 `8.716/27.103/109.800` 次/秒。结论是当前小场景前向不值得迁移 GPU，批量自定义 VJP 在 GPU1 上有明显收益；GPU1 仍只做显存受限、批量受控实验。证据见 `artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_performance_v1.json`、`manifest_server_gpu1_performance_v1.json`。
- `S5-PYBULLET-02` 扩大规模性能基准已补充：`horizon=256`、batch `32/64` 时，GPU1 前向吞吐相对 CPU 为 `1.28x/0.99x`，自定义 VJP 梯度吞吐相对 CPU 为 `22.22x/27.23x`；结论仍是按 batch/场景规模选择设备，GPU1 优先用于批量梯度反传，短任务不频繁重启进程。证据见 `artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_performance_h256_b32_b64_v1.json`、`manifest_server_gpu1_performance_h256_b32_b64_v1.json`。
- `S5-PYBULLET-02` 双动态刚体接触压力测试已完成：服务器 CPU/GPU1 均完成 `horizon=128, force=5`，最小间距均为 `-6.104719 m`，损失差 `4.97e-14`、梯度差 `2.31e-16`，原生 MuJoCo 对齐误差均小于 `1e-12 m`。该结果证明多刚体接触的数值路径和设备一致性，但暴露严重穿透，未通过物理真实性门；下一步先做接触稳定性参数扫描，不接入 CVAE/Diffusion 训练。证据见 `artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_multibody_v1.json`、`manifest_server_gpu1_multibody_v1.json`。
- `S5-PYBULLET-02` 双动态刚体首轮接触压力测试的间距统计口径已发现并修正：旧 `manifest_server_cpu_multibody_v1.json`/`manifest_server_gpu1_multibody_v1.json` 仅保留为历史诊断，不作为物理真实性证据；正式口径使用 `surface_gap_m = initial_gap + lead_qpos - ego_qpos`，并由 `tests/test_mjx_multibody_probe.py` 回归锁定。
- `S5-PYBULLET-02` 接触稳定性筛选已完成：8 组平衡参数组合在 CPU/GPU1 均 `8/8` 通过，最大 CPU/GPU 间距差 `8.88e-16 m`，最小真实间距 `3.393202 m`；代表性 `iterations=4` 候选的自定义 VJP 与 `jacfwd` 最大差均为 `0`。独立相向运动边界扫描又在服务器 CPU 完成 `6` 组：`6/6` 数值门通过，`4` 组发生接触，接触门 `3/4` 通过，`ego=3.0/lead=-3.0` 最大穿透 `0.080471 m`，整体物理真实性门为 `false`。GPU1 复核因 CARLA 持有项目锁暂缓，未绕过锁。该结果只证明受控小场景的数值边界，不证明车辆动力学真实性；暂不进入 CVAE/Diffusion 长时序训练。证据见 `artifacts/p4_1_mjx_differentiable_poc_v1/server_cpu_contact_boundary_v1/manifest.json` 和 `manifest_server_gpu1_contact_boundary_blocked_v1.json`。
- `S5-CORE-02` 生成模型小规模对照已完成：新增轻量条件表格 Diffusion、训练入口、统一生成入口和四生成器对照编排；四生成器各按 low/medium/high/critical 每档 `32` 条，共 `512` 条离线记录，统一 Schema 有效率和唯一率均为 `100%`。Diffusion 使用显式目标档设计区间投影后四档设计一致率为 `100%`；冻结风险代理下四种生成器均保持 `low < medium < high < critical` 的档位均值排序。该结果仅是 E2 本机离线参数证据，不新增 CARLA 实测，不替换 CVAE 主线；完整边界见 `docs/generator_diffusion_comparison_v1.md`，复现入口为 `tools/run_diffusion_comparison.cmd`。
- `S5-CORE-03` 受控条件检索已完成：`core/scenario_query.py` 统一 CLI 与 `GET /api/scenarios/search` 的结构化条件、范围校验和白名单关键词匹配；结构化条件与关键词可组合，非法条件返回 HTTP `400`，定向回归 `14` 项通过。查询只读索引，不解析自然语言、不启动 CARLA、不产生新的风险证据；说明见 `docs/controlled_scenario_query_v1.md`。
- `S5-CORE-04` Web 任务编排已完成：`core/web_task_orchestrator.py` 和 `tools/web_app.py` 提供 generation、validation、risk_analysis、carla 四类任务的提交、状态、结果和取消/确认接口；前三类使用本机 CPU worker，CARLA 任务默认 `awaiting_confirmation`，确认后仅登记 `confirmed_manual` 外部执行，绝不由 Web 进程隐式启动 CARLA。生成/校验/风险三页已产品化，校验支持 JSONL 逐条结果；页面、任务和全量回归均通过；接口见 `docs/software_copyright_interface_spec_v1.md`。
- `S5-CORE-05` 计划书指标同口径 baseline 已补齐：`tools/benchmark_stage5_generation_baseline.py` 在同一 CPU/Python/15 维范围/Schema 契约下，对 LHS 与 `uniform_rule` 各做五次、每次 `2048` 条生成；本轮总吞吐为 `3612.599633` vs `3761.787593` 条/s（系统侧 `0.960341x`，远未达到计划书 11 倍；CPU 墙钟仍会有调度波动）。同一 0.9.16 Gymnasium CARLA 冒烟的严格验收时间代理为 `12.9075` vs `13.622` s（下降 `5.2452%`，不是实车路测成本）。同一 `seed_v1` 的 `21` 个条件签名覆盖为 `100%` vs 固定规则模板 `4.761905%`；这不是行业覆盖率分母。计划书原始三项目标仍按证据边界分别标记为 `not_assessed` 或 `not_met_on_rule_proxy`。可复现入口为 `tools/run_stage5_metrics_baseline.cmd`，报告见 `docs/stage5_metrics_baseline_v1.md`，原始结果在 `F:\Carla\project-transfer\stage5_metrics_p1_20260824`。
- `S5-CORE-06` 外部成本与覆盖率估算已建立：`sources/research_stage5_real_vehicle_cost.json` 收录 BTS/AAA、BLS、RAND 和 Mcity 公开锚点，`sources/research_stage5_scenario_coverage.json` 收录 NHTSA、ISO 34502、PEGASUS 和 SUNRISE 场景覆盖方法；`docs/stage5_external_cost_and_coverage_estimate_v1.md` 给出 `$146-$529/车时`、2,048 条 30 分钟实车单元约 `$149,504-$541,696` 的显式假设区间，并明确行业没有统一公开覆盖率分母。该估算不替代实车账单、人工计时或行业统计，90%/11 倍/90% 原始目标仍不宣称达成。
- 整理 CARLA Demo 作为仿真底座的接口和验证证据，不把它包装成最终系统。
- 软著系统模块映射 V1 已按阶段五前置材料口径更新：M01–M08 均已映射到当前代码入口、输入输出和证据边界；M07 已升级为生成/校验/风险三条 Web 工作流，M08 提供默认离线的一键最小演示。完整 OpenSCENARIO 多传感器语义、RL 策略泛化和场景真实性评估仍未完成；文档见 `docs/software_copyright_module_mapping_v1.md`、`docs/stage5_web_product_flow_v2.md`。
- 阶段四 4.1/4.2 已形成 `custom_json_to_openscenario_carla_v1`：输入复用 `generated_scenario` Schema，输出 OpenSCENARIO XML 1.0 最小交换子集、Scene 04 CARLA JSON 和哈希清单；车辆蓝图、ego 标记和显式地图位姿已适配 ScenarioRunner。适配器单元回归、`seed_v1` 全部 `256` 条记录静态转换和服务器 `seed_v1_high_0165` 单场景直执行均已通过；天气、传感器、风险算法、Traffic Manager、路线控制器等 CARLA 专属字段仍保持在旁路配置中。边界见 `docs/openscenario_carla_adapter_v1.md` 和 `docs/scenario_runner_direct_execution_v1.md`。
- `S5-XOSC-01` 运行证据已登记：服务器 ScenarioRunner `0.9.16` 使用 CARLA `0.9.16`、GPU1、TM `8100`，`seed_v1_high_0165` 返回码 `0`，生命周期日志完整，runtime manifest 标记 `completed_no_criteria`。纯 XOSC 无 criteria 且末尾有一次已移除 ego actor 的清理警告；该结果只证明单场景直执行，不产生风险/传感器/JUnit 结论。
- 对抗性测试代理 V1 契约已完成：采用场景间迭代模式，动作是 15 维归一化参数增量，观测是 34 维参数/条件/实测反馈向量；奖励分离风险增量、碰撞/事件奖励、无效候选、重复和运行失败惩罚，并固化 Schema/语义失败、严格验收失败、CARLA 服务异常、连续重复和最大步数终止条件。核心实现、配置、Schema、CLI 和文档分别位于 `core/adversarial_agent.py`、`configs/adversarial_agent_v1.json`、`schemas/adversarial_agent_v1.schema.json`、`tools/adversarial_agent_v1.py` 和 `docs/adversarial_test_agent_v1.md`。服务器已安装训练依赖并完成 SAC/PPO 各 64 步 mock 短训练；该结果只验证训练接口，不构成策略效果或 RL 有效性结论。
- 闭环编排 V1 已完成：`core/adversarial_loop.py` 和 `tools/run_adversarial_episode.py` 先执行严格基线，再执行固定动作候选，并将 metadata 解析为代理 EpisodeResult；`validate`、`mock`、`carla` 三种模式和服务器冒烟入口已建立。2026-08-19 服务器 CARLA `0.9.16` 单 episode 真实冒烟完成 `2/2` 次严格验收：基线风险 `26.536/medium`，候选风险 `28.939/medium`，实测增量 `+2.403`；两次均无碰撞、RGB 各 `100` 帧、路线双车在途率 `1.0`、最大路线偏差不超过 `1.000 m`、服务健康、客户端/服务端版本一致。证据已回收至 `F:\Carla\project-transfer\server-results\adversarial_loop_smoke_v1_20260819_123339`。该结果只证明执行链路和结果回填可用，不构成策略效果或 RL 有效性结论。
- 多步闭环真实冒烟已完成：配置 `configs/adversarial_loop_multistep_v1.json` 将 `max_agent_steps` 设为 `3`，服务器任务 `adversarial-loop-multistep-v1_20260820_132752` 执行基线加 3 个连续候选，共 `4/4` 次严格验收通过。风险序列为 `27.774 → 28.942 → 30.375 → 31.651`，基线到最终候选实测增量 `+3.877`；3 个 transition 的风险增量奖励项为 `0.01168`、`0.01433`、`0.01276`。四次均无碰撞、RGB 各 `100` 帧，路线和 CARLA 服务健康验收通过，客户端/服务端均为 `0.9.16`。证据已回收至 `F:\Carla\project-transfer\server-results\adversarial_loop_multistep_v1_20260820_132752`。本轮使用固定 15 维动作，结果只证明连续反馈、样本递进和风险回填链路可用，不代表 RL 策略已学习。
- 闭环异常路径编排测试已完成：`tests/test_adversarial_loop.py` 新增候选运行失败立即中止、可配置的无效候选跳过执行并在下一步恢复、连续重复候选达到阈值后截断三类用例；验证执行器调用序列、失败原因、奖励项、最终记录和终止状态。全仓库 `36/36` 单元测试、`compileall`、多步 `mock` CLI 和 `git diff --check` 均通过。该结果是纯 Python/mock 编排证据，不新增 CARLA 实机结论；默认配置仍保持无效候选立即终止。
- Gymnasium/SB3 接口评估 V1 已完成：确认 15 维归一化连续动作、34 维 `[0,1]` 观测、`reset/step` 返回契约以及 `terminated/truncated` 语义均可映射；可选外壳位于 `core/adversarial_gym_env.py`。服务器 `Carla666-0916` 已固定 Gymnasium `1.3.0`、Stable-Baselines3 `2.9.0` 和 PyTorch `2.12.1+cu126`，Gymnasium 与 SB3 两套 `check_env` 均通过。`tools/train_adversarial_sb3_smoke.py` 使用确定性 mock 风险函数完成 PPO/SAC 各 64 步短训练、模型保存、加载和预测；证据标记为 `training_plumbing_only`，不连接 CARLA，也不支持策略效果结论。`matplotlib` 缺口已按 `3.11.0` 补齐，服务器全量 `60/60` 测试通过，另有 1 项仅在 Gymnasium 缺失时运行的测试按预期跳过。评估文档见 `docs/adversarial_gymnasium_evaluation_v1.md`。
- Gymnasium 环境级 CARLA 冒烟已完成：服务器任务 `adversarial-gymnasium-smoke-v1_20260820_215156` 使用 Gymnasium `1.3.0` 执行一次 `reset()` 基线和两次 `step()` 候选，`3/3` 次严格验收通过。风险序列为 `27.764 → 28.899 → 30.353`，两次 Gymnasium transition 的 reward 为 `0.21135`、`0.21454`；三次均无碰撞、RGB 各 `100` 帧、路线双车在途率 `1.0`、CARLA 服务健康、客户端/服务端 `0.9.16` 一致，`terminated=false`、`truncated=false`。证据已回收至 `F:\Carla\project-transfer\server-results\20260820_215156_20260820_215411`。该结果证明 Gymnasium 外壳与真实 executor 的状态回填链路可用，不代表策略学习或 RL 训练有效。
- 分层场景采样与非学习离线基线 V1 已完成：`core/adversarial_sampling.py` 从场景库 `117` 条独立场景按 LHS/GMM/CVAE × low/medium/high/critical 的 12 个分层轮转，并在分层内平衡天气/危险标签和 Traffic Manager 种子；相同随机种子可复现样本与交通种子序列，采样元数据写入 Gymnasium `reset info.sampling`。首轮配置抽取 `24` 个独立场景，三个生成器各 `8` 条、四档各 `6` 条、三个交通种子各 `8` 次。fixed/random/LHS/rule-guided LHS 的原始首轮有效数分别为 `24/21/21/22`；独立有限重试流额外使用 `0/3/3/2` 次动作后全部补齐为 `24/24`，有效候选唯一率均为 `100%`，没有预算耗尽。最终离线结果位于 `F:\Carla\output-0.9.16\adversarial_baselines_v1\20260821_132033`，来源提交 `ab78246`，候选未运行 CARLA，不能据此评价风险收益或 RL 有效性。
- 四策略 CARLA 静态对照计划 V1 已完成：从一个完整 `12` 分层周期为每个场景准备 1 个共享基线和 fixed/random/LHS/rule-guided LHS 各 1 个候选，共 `12 + 48 = 60` 个计划运行；60 个场景记录、CARLA 配置和 Scene 04 `--validate-only` 全部通过，重试预算耗尽为 `0`。计划位于 `F:\Carla\output-0.9.16\adversarial_baseline_carla_plan_v1\20260821_132000`，来源提交 `ab78246`。该目录只保留静态计划证据；实机结果单独记录并继续按覆盖数量区分。
- 四策略 CARLA 首个 pair 实机冒烟已完成：服务器任务 `adversarial-baseline-carla-smoke-v1_20260821_134010` 执行共享基线加 fixed/random/LHS/rule-guided LHS 共 `5/5` 次严格验收；客户端/服务端均为 `0.9.16`，风险方法均为 `heuristic_v2`，RGB 各 `100` 帧，路线双车在途率均为 `1.0`，最大路线偏差不超过 `0.999 m`，服务健康。共享基线风险为 `94.081`，四候选风险为 `87.612/85.842/84.703/88.943`，相对增量均为负；该轮暴露的旧 reward 饱和问题已由后续 reward V2 修复。轻量证据回收至 `F:\Carla\project-transfer\server-results\20260821_134011_20260821_134314`。
- reward V2 已冻结：碰撞与安全事件由候选绝对奖励改为相对上一条严格结果的 `relative_capped_delta`；碰撞回调保留原始计数，但奖励只使用 0/1 碰撞状态差，非碰撞事件只统计按类型和原因去重的 `ego_safety_brake`。首个 pair 的旧 reward `0.635310/0.617610/0.606220/0.648620` 使用真实 metadata 重算后变为 `-0.064690/-0.082390/-0.093780/-0.051380`，4/4 与负风险增量方向一致。该修复避免高危基线已有碰撞时重复奖励候选，但不修改历史风险分和严格验收结论。
- 四策略完整 CARLA 对照已完成：服务器任务 `adversarial-baseline-carla-full-v1_20260821_152923` 基于提交 `a65254d` 执行 12 个共享基线和 48 个候选，`60/60` 严格验收通过；客户端/服务端均为 `0.9.16`，风险方法均为 `heuristic_v2`，RGB 各 `100` 帧，路线、传感器和服务健康全部通过。rule-guided LHS 在 `10/12` 个 pair 风险升高、`8/12` 次取得四策略最高风险，中位风险增量 `+2.045`；fixed 为 `9/12`、中位 `+0.525`；random 和 LHS 中位增量分别为 `-0.656/-0.821`。random 与 rule-guided LHS 各新增 1 个碰撞 pair，四策略各消除 1 个基线碰撞。每个分层只有一个 pair，当前只支持把 rule-guided LHS 作为主要非学习对照，不支持普遍优势结论。轻量结果位于 `F:\Carla\project-transfer\server-results\20260821_152924_20260821_155826`。
- Stable-Baselines3 低成本训练工程链路已完成：服务器任务 `adversarial-sb3-smoke-v1_20260821_165303` 基于提交 `352e86f` 运行，PPO 与 SAC 各训练 `64` 步，模型文件均成功保存并重新加载，确定性预测均生成合法 15 维候选；两套 `check_env` 均通过。摘要回收至 `F:\Carla\project-transfer\server-results\20260821_165304_20260821_165402\training_summary.json`。执行器为 `deterministic_mock_v1`，`carla_connected=false`、`supports_policy_effect_claim=false`；该证据只证明训练工程链路，不用于比较策略危险性。
- 冻结 27 维风险代理训练执行器已完成：`core/adversarial_proxy_executor.py` 在反序列化前校验模型 SHA-256，并固定 15 个原始参数 + 12 个 `physical_interaction_v1` 派生特征的顺序。服务器任务 `adversarial-sb3-proxy-smoke-v1_20260821_172514` 基于提交 `069a676` 使用 V5 随机森林模型完成 Gymnasium/SB3 两套 `check_env` 和 PPO/SAC 各 64 步训练；两个模型均保存、加载并生成合法候选，单次代理预测分为 `52.411` 和 `50.940`。代理只提供连续风险通道，专用训练配置将碰撞与事件奖励固定为 `0`；摘要回收至 `F:\Carla\project-transfer\server-results\20260821_172515_20260821_172622\proxy_training_summary.json`。该证据属于 `proxy_environment_only`，不构成 CARLA 策略效果结论。服务器全量 `63/63` 测试通过，另有 1 项缺失 Gymnasium 反向测试按预期跳过。
- 多随机种子冻结代理基准已完成：服务器任务 `adversarial-sb3-proxy-benchmark-v1_20260821_175339` 基于提交 `a62b48a` 训练 PPO/SAC 各 3 个种子、每模型 `4096` 步，并在同一组 24 个分层场景上与四类非学习策略进行等推理候选预算比较。SAC 的平均风险增量为 `+0.808`、中位增量 `+0.990`、正增量率 `77.8%`，`72/72` 候选有效；rule-guided LHS 对应为 `+0.910`、`+1.972`、`83.3%`。SAC 相对 rule-guided LHS 为 `19` 胜 `53` 负，当前只能作为 CARLA 独立验收的学习候选，不能替代规则基线。PPO 平均增量 `-1.390` 且有 1 个无效候选，不进入首轮实机验收。执行器将随机森林单样本推理线程固定为 `1` 后，完整任务耗时 `12` 分 `13` 秒；结果回收到 `F:\Carla\project-transfer\server-results\20260821_175341_proxy_benchmark_full`，详见 `docs/adversarial_proxy_benchmark_v1.md`。
- SAC/rule-guided LHS CARLA 独立评估 V1 已完成：服务器任务 `adversarial-policy-carla-full-v1_20260821_203104` 基于计划提交 `776c1e3` 和执行提交 `11f43de`，使用与上一轮代理起始集合不重叠的 12 个分层 pair，共 `36/36` 条严格验收通过；33 次为本任务实际执行、3 次复用已验收运行。SAC 平均风险增量 `-2.017`、中位 `+0.786`、风险升高 `8/12`；rule-guided LHS 平均 `-4.359`、中位 `+0.241`、风险升高 `6/12`。基线碰撞 `3/12`；SAC 候选碰撞 `2/12`（新增 0、消除 1），rule-guided LHS 候选碰撞 `2/12`（新增 1、消除 2）。36 条运行的版本、RGB 100 帧、路线、服务健康和 `heuristic_v2` 门均通过。目标档不匹配为候选描述性结果，不是运行失败；本轮不支持普遍策略优势。完整报告见 `docs/adversarial_policy_carla_evaluation_v1.md`，证据目录为 `F:\Carla\project-transfer\server-results\adversarial_policy_carla_full_v1_20260821_202710`。
- SAC/rule-guided LHS 重复 Traffic Manager 种子复验 V1 已完成：对 `apcv1_pair_02/07/08` 三个原始独立 pair 使用 `20260824/20260825/20260826` 三个种子，共 `9` 个重复 pair、`27/27` 条严格验收通过；实际执行 `25` 条、复用已验收 `2` 条。SAC 平均风险增量 `-3.483`、中位 `+0.334`、风险升高 `6/9`，rule-guided LHS 平均 `-10.712`、中位 `-28.684`、风险升高 `3/9`；共享基线碰撞 `6/9`，SAC 新增 `0`、消除 `3`，rule-guided LHS 新增 `3`、消除 `6`。27 条运行的版本、RGB 100 帧、路线、服务健康和 `heuristic_v2` 门均通过。3 个种子是同一原始场景的重复测量，不能把 `9` 个重复 pair 当作独立场景。报告见 `docs/adversarial_policy_carla_repeat_evaluation_v1.md`，证据目录为 `F:\Carla\project-transfer\server-results\20260822_104710_20260822_133247`。
- SAC/rule-guided LHS 未覆盖分层扩展 V1 已完成：服务器任务 `adversarial-policy-carla-expand-full-v1_20260822_140450` 从排除旧库 `36` 条条目后的可用集合中选取 CVAE/LHS/GMM 的 `critical` 与 `high` 分层，共 `6` 个新增独立 pair、`18/18` 条 CARLA 严格验收通过；其中 `15` 条为本轮新执行，`3` 条复用已通过冒烟结果。共享基线平均风险 `60.574`，基线碰撞 `2/6`；SAC 平均风险增量 `+8.636`、中位 `-0.265`、风险升高 `2/6`、新增碰撞 `2`；rule-guided LHS 平均风险增量 `+9.298`、中位 `+15.363`、风险升高 `4/6`、新增碰撞 `3`、消除碰撞 `1`。18 条运行的 0.9.16 版本、RGB 100 帧、路线、服务健康和 `heuristic_v2` 门均通过；本轮不支持普遍策略优势或增加在线训练预算。报告见 `docs/adversarial_policy_carla_expand_v1.md`，证据目录为 `F:\Carla\project-transfer\server-results\20260822_135901_20260822_141306`。
- SAC/rule-guided LHS 独立场景合并统计 V1 已完成：合并首轮 `12` 个独立 pair 与扩展 `6` 个独立 pair，共 `18` 个独立场景、`54/54` 条 CARLA 严格验收通过；重复 Traffic Manager 种子未计入独立样本。合并后 SAC 平均风险增量 `+1.534`、中位 `+0.246`、风险升高 `10/18`、新增碰撞 `2`、消除 `1`；rule-guided LHS 平均风险增量 `+0.193`、中位 `+1.128`、风险升高 `10/18`、新增碰撞 `4`、消除 `3`。该汇总仍是当前场景集合的描述性证据，不支持普遍策略优势。报告见 `docs/adversarial_policy_carla_independent_aggregate_v1.md`。
- 阶段四独立策略质量门审计 V1 已完成：合并 `54/54` 条运行的版本、RGB 100 帧、服务健康、`heuristic_v2` 和路线验收均通过；`53/54` 条为全程路线状态，唯一的 `1/54` 碰撞前路线验收发生在扩展 CVAE/critical 的 SAC 候选，碰撞前双车在途率 `1.0`、最大偏差 `0.992 m`，碰撞后偏离不计作路线门失败。碰撞按目标档集中于 high/critical，未发现服务、传感器或路线质量门的系统性回归；扩展候选无效尝试为 `0`，首轮的 `2` 次无效尝试均已恢复。报告见 `docs/adversarial_policy_carla_quality_gate_v1.md`。
- 未覆盖高风险分层策略重复测量 V1 已完成：对扩展 `CVAE/critical` 与 `LHS/high` 两个源场景使用 Traffic Manager 种子 `20260827/20260828/20260829`，共 `6` 个重复 pair、`18/18` 条 CARLA 严格验收通过；实际执行 `15` 条，复用冒烟 `3` 条。CVAE/critical 中共享基线、SAC、rule-guided LHS 均为 `3/3` 碰撞，但 SAC/LHS 风险增量均为负；LHS/high 中基线 `0/3` 碰撞，而 SAC 和 rule-guided LHS 均为 `3/3` 新增碰撞，平均风险增量分别为 `+29.254` 和 `+34.077`。18 条运行版本、RGB 100 帧、服务健康、`heuristic_v2` 和路线门均通过；6 条碰撞后路线状态偏离，碰撞前在途率均为 `1.0`、最大偏差 `0.992 m`。该重复证据将 LHS/high 标记为优先风险回归对象，不支持普遍策略优势。报告见 `docs/adversarial_policy_carla_repeat_expand_v1.md`，证据目录为 `F:\Carla\project-transfer\server-results\20260822_155626_20260822_160725`。
- 2026-08-18 已完成适配器生成 CARLA JSON 的单场景实机冒烟：CARLA 客户端/服务端均为 `0.9.16`，20 秒同步仿真完成，RGB/Depth/Semantic 各保存 `200` 帧，服务健康，事件和 `heuristic_v2` 风险结果均写入 `metadata.json`，无碰撞。该配置未启用路线锁定，因此只计为运行时冒烟，不计为路线严格验收；证据目录为 `F:\Carla\output-0.9.16\adapter_smoke\seed_v1_high_0165\20260818_222032`。
- 适配器冒烟期间曾发现本机默认 `python` 加载 CARLA `0.9.15`；该残留包已卸除，后续本机连接 CARLA 0.9.16 必须显式使用 `Carla666-0916` 环境。
- 运行环境规则已收口：服务器优先，SSH/RPC/健康检查失败才回退本机；本机固定使用 `D:\ANACONDA\envs\Carla666-0916`，运行前检查客户端/服务端均为 `0.9.16`。本机 Python 0.9.15 残留包已卸除。
- OpenSCENARIO XML 1.4 已登记为未来标准交换适配方向：后续单独建立 1.4 映射、Schema 校验和工具链运行证据，不替换当前 1.0 运行目标。
- 已完成 M01–M08 接口规格 V1：固化命令入口、核心函数、输入输出、运行可信条件、异常边界和验收矩阵；M08 默认离线且不产生新的 CARLA 风险结果；文档见 `docs/software_copyright_interface_spec_v1.md`。
- M07 只读可视化原型已完成：`tools/scenario_dashboard.py` 通过 Python 标准库读取场景库，提供本地页面、筛选、场景详情和只读 JSON 接口；数据契约回归与本地 HTTP 端点验证通过。
- 历史记录：阶段三已完成收口并进入阶段四；软著演示截图暂缓，待正式准备申请软著时基于冻结版本统一采集，不作为阶段四启动条件。当前项目已完成阶段四收口并处于阶段五。
- 阶段三验收门已加固：运行级严格验收同时要求运行完成、验收完成、实机确认、传感器完成、CARLA 服务健康、路线完成并通过以及元数据路径存在；现有三生成器对照 `108/108` 条运行明细继续满足新条件。场景库新增 `verification_basis`，明确区分 `direct_run_evidence` 与 `inherited_batch_acceptance`。
- 已确定第一版参数级场景表示：条件标签、天气、前车急刹、行人横穿、运行种子和实测风险标签。
- 已生成 `seed_v1`：共 `256` 条参数设计样本，低/中/高/临界风险目标各 `64` 条；训练/验证/测试集为 `180/40/36`，各风险档在各数据划分中保持平衡。
- 已建立 Schema 校验、语义校验和 CARLA 完整配置编译能力；全部 `256` 条记录均唯一且能编译为合法的 Scene 04 配置。
- 已建立 `literature_generative_ai_autonomous_driving/` 文献资料目录，收录 56 篇论文索引及 46 篇本地 PDF，覆盖安全关键场景生成、扩散模型、LLM、CARLA/OpenSCENARIO 和对抗测试。
- 已完成生成式 AI 模型选型：第一版采用约束感知的轻量条件表格 CVAE，生成 15 维连续场景参数；规则/LHS 与条件 GMM 作为对照。完整研究路线是“可行参数先验 + 风险反馈引导”，实测数据达到条件后再升级潜空间条件 Flow；LLM 仅作为可选条件解析器，不直接生成最终连续参数。
- 选型依据和适配细节见 `生成式AI模型选型调研报告.md`；始终严格区分参数设计目标 `target_risk_level` 与 CARLA 实测标签 `observed_risk`。
- 条件 GMM 已完成训练和验证集选型：最终选择单分量模型，训练/验证/测试平均对数似然分别为 `13.705`、`12.685`、`13.052`。
- 轻量条件表格 CVAE 已完成 5 个随机种子训练；最终按验证损失选择种子 `97`，测试损失 `0.005965`、重构损失 `0.005519`、KL `4.461`，当前默认 `beta=0.0001`，已避免初始实验中的明显潜变量塌缩。
- LHS、GMM、CVAE 已在低/中/高/临界四档各生成 `128` 条进行离线对比，12 组样本的 Schema/语义有效率和唯一率均为 `100%`。CVAE 的设计区间记录一致率为 `82.0%—93.0%`，高于 GMM 的 `29.7%—58.6%`，但仍低于规则/LHS 的 `100%`，因此当前不能声称 CVAE 优于规则生成器。
- `cvae_validation_v1` 已完成首轮实机验证：四个风险档各选择 1 条接近同档样本中心的 CVAE 代表样本，4/4 场景完成，传感器写盘和 CARLA 服务健康检查均通过。实测风险分别为低风险目标→`medium/38.464`、中风险目标→`medium/43.718`、高风险目标→`high/59.275`、临界风险目标→`high/65.420`，目标档位命中率为 `2/4`。该结果仅为每档 1 条的冒烟验证，不能作为模型总体命中率结论。
- 第二轮 `cvae_validation_v2` 已完成：排除首轮 4 条样本后，每档沿同档样本主要变化方向选取 3 条，共 12 条；12/12 场景完成，RGB 共 `1200` 帧，传感器写盘和 CARLA 服务健康检查均通过。四档实测平均分依次为 `26.292`、`29.604`、`57.335`、`65.302`，保持严格递增，目标档位与实测分数相关系数为 `0.664`；目标档位命中 `4/12`，其中临界目标 3 条全部实测为高风险。高风险样本 `cvae_high_20260813_0033` 单次运行记录 2 个碰撞事件并达到 `critical/86.538`。
- `cvae_repeatability_v1` 已完成：固定第二轮 12 个场景，完整交叉覆盖 Traffic Manager 种子 `20260821/22/23`，共 `36/36` 次运行完成，传感器写盘与 CARLA 服务健康检查均为 `36/36`。四档实测平均分为 `26.297`、`29.449`、`64.049`、`64.234`，数值上仍严格递增，但低/中以及高/临界间隔很小；逐次目标档命中 `14/36`，仅 `5/12` 个场景三次实测档位完全一致。
- 重复性诊断发现明显执行分支：三个交通种子平均分依次为 `53.646`、`31.404`、`52.972`，种子 `20260822` 系统性偏低；7 个不稳定场景主要由 TTC 与前车间距两个分量同时在低值和高值间切换造成，单次分数可跳变约 `40` 分。结合运行器仅设置 Traffic Manager 随机种子和自动驾驶、未显式锁定路线与车道行为，当前证据指向车辆路线/跟车关系发生语义漂移；该 36 次结果作为问题诊断有效，但不能作为“固定场景仅受微小随机扰动”的最终重复性结论。
- 碰撞样本 `cvae_high_20260813_0033` 在三个种子下均发生 `2` 个碰撞事件，三次得分为 `86.538/86.714/87.847`，碰撞危险性具有较强复现性；3 个临界目标样本共 9 次运行全部实测为 `high`，说明当前 `critical` 设计条件和 `heuristic_v2` 临界档定义仍未对齐。
- Scene 04 已增加可选路线锁定：为主车与前车生成相同的确定性 waypoint 路径，禁用自动及随机换道，并将行人横穿点绑定到该路径；每帧新增实际/计划道路与车道 ID、路径索引、路径偏差和在途状态，`metadata.json` 汇总双方全程在途率与最大偏差。旧配置默认不开启路线锁定，保持兼容。
- `cvae_repeatability_v2` 已完成 9/9 次 CARLA 仿真，传感器写盘和服务健康均为 9/9。三个场景在三个交通种子下的实测得分完全一致：低风险样本 `0.157/low`、中风险样本 `3.412/low`、高风险样本 `63.062/high`；场景内分数极差和三个种子平均分极差均为 `0`。但严格路线验收为 `0/9`：主车平均在途率 `0.2575`、前车平均在途率 `0.85`、双车同时在途率 `0.1417`，主车最大偏差 `81.163 m`。这些分数可作为确定性分支诊断，不得表述为路线锁定已验证成功。
- 项目内确定性 waypoint 跟踪控制器已通过 `route_controller_smoke_v1` 单场景实机严格验收：仿真、RGB 写盘和 CARLA 服务均正常，路线验收 `1/1`，主车、前车和双车同时在途率均为 `1.0`，双方最大路线偏差均为 `0.996 m`；中风险目标实测为 `medium/27.744`，最低 TTC `1.679 s`、最小净间距 `4.382 m`、无碰撞。该结果证明控制器在当前代表样本可用，但不能替代多场景多种子验证。
- 控制器诊断遥测已补齐至 `telemetry.csv`：包含主车安全制动原因、双方油门/制动/转向、控制器路径进度、路线拓扑匹配和控制模式；修复已同步到 CARLA 运行副本，后续完整回归将保留逐帧控制证据。
- `cvae_repeatability_v3` 已完成 9/9 次实机运行和严格验收：RGB 共 `900` 帧，传感器与服务健康均为 9/9，路线验收 9/9，主车、前车和双车同时在途率均为 `1.0`，双方最大路线偏差分别为 `1.043 m` 和 `1.062 m`，无碰撞。场景内分数标准差均值由 V1 的 `13.353` 降至 `0.368`，最大值由 `22.781` 降至 `0.635`，三个种子平均分极差由 `22.243` 降至 `0.471`；当前三个代表场景中的随机路线分支问题可以认为已消除。
- V3 三个目标档平均分为低 `24.611`、中 `27.330`、高 `42.204`，保持严格递增，目标档序号与实测分数相关系数为 `0.928`；逐次档位命中为 `5/9`。低风险样本仅因分数跨越 `25` 边界出现一次 medium，高风险目标三次稳定为 medium，说明剩余问题是风险条件与标准化驾驶策略的校准，而不是执行不稳定。
- 已冻结控制器配置 `waypoint_follower_v1`，记录传感器、路线、PID、安全制动和严格验收参数，并在 V4 清单中保存配置文件路径与 SHA-256 哈希，防止后续实验参数漂移。
- `cvae_repeatability_v4` 已完成 36/36 次实机运行和严格验收：传感器写盘、CARLA 服务健康和路线验收均为 36/36，RGB 共 `3600` 帧，主车、前车和双车同时在途率均为 `1.0`，双方最大路线偏差分别为 `1.047 m` 和 `1.077 m`，无碰撞。36 个遥测文件共 `14400` 行，控制诊断字段无缺失且全部使用冻结的 `waypoint_follower_v1`。
- V4 的场景内连续分数标准差均值为 `0.404`、最大值为 `0.638`，三个种子平均分极差为 `0.245`，`11/12` 个场景的三次实测档位完全一致。相比 V1，三项波动指标分别下降 `96.97%`、`97.20%` 和 `98.90%`；当前 12 个固定 CVAE 场景中的随机路线/车道执行分支可以认为已消除。
- V4 四个目标档平均实测分数为低 `23.956`、中 `27.715`、高 `43.091`、临界 `48.994`，保持严格递增，目标档序号与实测分数相关系数为 `0.956`；逐次目标档命中 `17/36`。高风险目标 9 次均为 `medium`，临界目标为 `medium` 6 次、`high` 3 次，说明当前剩余问题是目标风险条件与冻结安全驾驶策略下实测风险的校准，而不是仿真重复性。
- `generator_comparison_v1` 已生成：LHS、GMM、CVAE 各选低/中/高/临界 3 个场景，每种生成器 12 个、共 36 个独立样本；每个样本运行三个交通种子，共 108 次。交通种子属于同一场景的重复测量，不能将 36 次运行视为每个生成器的 36 个独立样本。
- 对照调度采用 9 个平衡组，每组完整覆盖三生成器 × 四风险档，并拆为 27 个四场景小批次；每个小批次包含四个风险档，组内运行顺序使用固定种子随机化。108/108 配置已通过 CARLA 运行副本 `--validate-only`，控制配置、基础配置、来源数据和选中记录均保存 SHA-256 哈希。
- 三生成器采用相同的 `spread` 抽样，在各自每个目标档沿第一主变化方向选择 0.1/0.5/0.9 分位附近样本。选中样本的同档平均参数距离为 LHS `0.619`、GMM `0.541`、CVAE `0.340`；设计区间记录一致率分别为 `1.000`、`0.667`、`0.917`。这些是离线抽样描述，不代表 CARLA 实测危险性。
- 三生成器对照已完成 `108/108` 次仿真和严格验收。原唯一失败样本 `lhs_critical_20260813_0101__tm_20260821` 重跑后通过：主车/前车最大路线偏差为 `1.002/0.979 m`，双车同时在途率为 `1.0`，传感器写盘完成且 CARLA 服务健康；实测风险为 `medium/49.550`。
- 最终工程对照显示：LHS 严格验收 `36/36`、目标命中率 `58.3%`、无碰撞；GMM 严格验收 `36/36`、目标命中率 `55.6%`、碰撞运行 `9/36`；CVAE 严格验收 `36/36`、目标命中率 `47.2%`、无碰撞。冻结 LHS 为工程基线、GMM 为高风险压力分支、CVAE 为实测风险反馈研究分支。

## 核心结构
- `scenes/scene_01_extreme_weather.py`：极端天气场景。
- `scenes/scene_02_multi_hazard.py`：多危险叠加场景。
- `scenes/scene_03_multi_sensor.py`：多传感器与行人鬼探头场景。
- `scenes/scene_04_parameterized.py`：JSON 参数化主场景运行器。
- `core/risk_metrics.py`：遥测与启发式风险评分。
- `core/route_follower.py`：主车与前车的确定性 waypoint 跟踪控制器。
- `core/sensor_pipeline.py`：异步传感器写盘与完整性统计。
- `core/batch_statistics.py`：重复批次聚合统计。
- `batch_runner.py`：批次调度、日志和汇总入口。
- `configs/`：主场景和批次配置。
- `configs/route_control_profiles/waypoint_follower_v1.json`：已通过 V3/V4 实机验证的冻结控制器、传感器和严格验收配置。
- `schemas/generated_scenario.schema.json`：生成模型输出的参数级场景 Schema。
- `schemas/scenario_library_entry.schema.json`：场景库 V1 的参数、来源、证据、风险和质量统一条目 Schema。
- `core/scenario_validator.py`：Schema/语义校验和 CARLA 配置编译器。
- `core/physical_constraints.py`：参数级物理约束、危险边界提示和可审计报告核心函数。
- `core/scenario_library.py`：场景内容哈希去重、运行证据聚合和质量评估核心逻辑。
- `core/scenario_features.py`：15 维特征、条件编码和生成记录构建接口。
- `tools/generate_seed_dataset.py`：平衡风险分层与 Latin Hypercube 种子数据生成器。
- `tools/generate_with_model.py`：LHS、条件 GMM 和 CVAE 的统一生成入口。
- `tools/prepare_carla_validation.py`：生成模型样本抽样与 CARLA 配置编译。
- `tools/collect_carla_validation.py`：读取 CARLA 元数据并回填 `observed_risk`。
- `tools/build_scenario_library.py`：从严格验收实验构建场景库 JSONL、CSV 索引、汇总和哈希清单。
- `core/scenario_query.py`：统一校验结构化查询条件和白名单关键词，供 CLI 与 Web API 复用。
- `core/web_task_orchestrator.py`：统一 Web 任务提交、状态、结果和 CARLA 显式确认契约；离线任务使用 CPU worker，CARLA 不由 Web 进程启动。
- `tools/measure_stage5_metrics.py`：按固定输入、契约和验收门测量阶段五生成吞吐、测试时间代理和条件签名覆盖率；系统与 baseline 契约不一致时拒绝计算相对值。`tools/benchmark_stage5_generation_baseline.py` 提供同 CPU 的 LHS/规则采样复现实验。
- `tools/query_scenario_library.py`：按生成器、目标/实测风险、碰撞、证据粒度、质量等级、CARLA 版本、天气/危险标签、风险分数、多样性和白名单关键词组合筛选场景库，支持表格、CSV 和 JSONL 输出。
- `tools/web_app.py`、`tools/web_app.cmd`：阶段五 Web 统一入口；复用 M07 数据契约，提供 Dashboard、场景列表、详情、受控查询、健康检查和任务提交/状态/结果页面。
- `analysis/analyze_scenario_library.py`：生成场景库质量摘要、目标/实测矩阵、审查 CSV、Markdown 报告和 PNG/SVG 总览图。
- `configs/scenario_library_quality_gate_v1.json`：冻结当前场景库数量、证据分层、质量摘要和查询字段契约。
- `tests/test_scenario_library_interfaces.py`：构建器校验、质量摘要快照、查询筛选和 CSV 导出回归测试。
- `tools/test_scenario_library.cmd`：在 Windows CMD 中运行场景库回归测试。
- `models/`、`training/`：条件 GMM、轻量条件表格 CVAE、数据集与训练脚本。
- `analysis/evaluate_generators.py`：生成器合法性、条件一致性和多样性离线评估。
- `data/scenarios/seed_v1/`：第一版结构化参数种子数据集。
- `data/scenarios/scenario_library_v1/`：场景库 V1 的 117 个独立场景、351 次严格验收证据、质量分层和检索索引。
- `data/scenarios/scenario_library_v1/quality_analysis_v1/`：117 场景质量分析基线、4 份统计 CSV、报告、清单和总览图。
- `data/scenarios/cvae_validation_v1/`：四档 CVAE 代表样本及 CARLA 抽样验证清单。
- `data/scenarios/cvae_validation_v2/`：第二轮 12 条分层代表样本、运行清单、实测记录和分析报告。
- `data/scenarios/cvae_repeatability_v1/`：12 个固定场景的三交通种子复测清单和 24 次新增运行脚本。
- `tools/prepare_carla_route_regression.py`：生成 waypoint 控制器下的三场景九次受控回归包。
- `data/scenarios/cvae_repeatability_v2/`：路线锁定回归的 9 份配置、平衡运行计划和分批脚本。
- `data/scenarios/cvae_repeatability_v3/`：通过单场景冒烟后生成的确定性路线回归配置、严格验收清单、分批脚本和自动汇总入口。
- `data/scenarios/cvae_repeatability_v3/controlled_repeatability_conclusion.md`：V1/V2/V3 对照、控制遥测质量、风险解释和后续实验边界。
- `data/scenarios/cvae_repeatability_v4/`：12 场景 × 3 种子的实机记录、严格验收结果和正式结论。
- `tools/prepare_generator_carla_comparison.py`：统一抽样 LHS/GMM/CVAE，生成平衡组、运行配置、配置哈希和分批脚本。
- `tools/collect_carla_generator_comparison.py`、`analysis/analyze_carla_generator_comparison.py`：汇总严格验收、跨种子重复性和三生成器同口径实测指标。
- `data/scenarios/generator_comparison_v1/`：36 个独立场景、108 份配置、9 个平衡组、27 个四场景小批次和自动汇总入口。
- `tools/build_risk_feedback_dataset.py`：按独立场景聚合重复测量，构建风险反馈数据集。
- `analysis/train_risk_proxy.py`：训练均值基线、Ridge 和随机森林风险代理，并生成折外预测与误差报告。
- `data/scenarios/risk_feedback_v1/`：36 个独立场景的聚合特征、实测风险标签和代理模型评估结果。
- `analysis/analyze_risk_proxy_diagnostics.py`：执行重复分层 OOF，诊断分组误差、样本排名波动、Top-K 稳定性、模型一致性和碰撞/非碰撞误差差异。
- `core/physical_features.py`：从生成前可知的 15 维场景参数计算 12 个物理交互派生特征，不读取遥测、碰撞结果或风险标签。
- `analysis/analyze_physical_feature_enhancement.py`：在同一重复分层三折 OOF 下对比原始参数与物理增强特征的风险回归、碰撞分类和排名稳定性。
- `analysis/score_feedback_candidates_dual.py`：支持原始 15 维和原始参数加 12 个派生特征的 27 维模型空间，距离边界与多样性计算仍固定使用原始 15 维，隔离模型特征变化。
- `analysis/compare_candidate_scoring_feature_spaces.py`：比较两套特征空间的候选预测变化、短名单重合、碰撞倾向和选择多样性。
- `data/scenarios/risk_feedback_v1/diagnostics_v1/`：50 次重复三折诊断的完整结构化结果和工程结论。
- `tools/prepare_feedback_candidate_validation.py`、`tools/run_feedback_candidate_validation.py`：生成 27 场景 × 3 种子的平衡验证计划，并支持严格验收后的断点续跑。
- `tools/collect_feedback_candidate_validation.py`、`analysis/analyze_feedback_candidate_validation.py`：聚合外部验证结果，计算代理外部误差、Spearman、Top-9 重合度和高风险/碰撞发现率。
- `tools/server_feedback_validation.cmd`、`tools/server_jobs/feedback_candidate_validation_v1.sh`：服务器端一键执行单次冒烟、剩余批次和最终汇总。
- `tools/prepare_route_controller_smoke.py`：生成确定性路线控制器的单场景冒烟包。
- `data/scenarios/route_controller_smoke_v1/`：单场景配置、严格验收清单和一键运行脚本。
- `data/scenarios/carla_0916_migration_v1/`：CARLA 0.9.16 独立迁移配置、三交通种子严格验收结果和 0.9.15 同配置对照记录。
- `data/scenarios/carla_0915_runtime_evidence.md`：0.9.15 历史结构化运行证据的迁移范围、完整性校验和保留边界。
- `tools/collect_carla_repeatability.py`、`analysis/analyze_carla_repeatability.py`：区分仿真完成与严格验收，汇总路线、传感器和服务状态；非碰撞运行验收全程路线，碰撞运行可验收首次碰撞前路线并保留全程指标。
- `configs/server_workflow.json`：笔记本与服务器之间的 SSH、Git、Python、CARLA、GPU、端口和存储路径统一配置。
- `tools/server_sync.cmd`：将已提交代码通过内网裸 Git 仓库同步到服务器运行工作区，不推送 GitHub。
- `tools/server_carla.cmd`：启动、检查和停止服务器 CARLA；固定使用 GPU 1、RPC 端口 2000 和项目 GPU 互斥锁。
- `tools/server_carla_smoke.sh`：服务器 CARLA Python API 与当前地图连接冒烟检查，由后台任务入口执行。
- `tools/server_jobs/dual_channel_validation_smoke_v1.sh`：自动定位服务器最新双通道配对计划，只运行一个样本进行 CARLA 冒烟验证。
- `tools/server_jobs/dual_channel_validation_full_v1.sh`：自动定位服务器最新双通道配对计划，按计划顺序运行完整 54 次配对验证。
- `tools/server_jobs/dual_channel_validation_collect_v1.sh`：自动定位最新双通道配对计划并收集 54 次运行结果，生成严格验收和通道比较报告。
- `tools/server_risk_feedback_v3.cmd`、`tools/server_jobs/risk_feedback_v3.sh`：将双通道配对验证新增数据并入 V2 数据集，生成 V3 风险反馈数据、代理和重复诊断。
- `tools/server_dual_candidate_scoring_v3.cmd`、`tools/server_jobs/dual_candidate_scoring_v3.sh`：使用 V3 风险反馈数据对同口径 1536 个 LHS/GMM/CVAE 候选重新评分。
- `tools/server_multisensor_smoke_v1.cmd`、`tools/server_jobs/multisensor_smoke_v1.sh`：在不改变 RGB 基线的前提下，以低频 640×360 配置验证 RGB、Depth、Semantic 和 Collision 的实际写盘代价。
- `tools/server_physical_feature_enhancement_v1.cmd`、`tools/server_jobs/physical_feature_enhancement_v1.sh`：自动定位最新 V4 数据集并执行 50 次重复分层三折物理特征增强实验。
- `tools/server_physical_candidate_scoring_v1.cmd`、`tools/server_jobs/physical_candidate_scoring_v1.sh`：生成同一批 1536 个候选，分别完成原始 15 维与物理增强 27 维的风险/碰撞双通道评分并输出比较报告。
- `tools/server_run.cmd`、`tools/server_job_status.cmd`：同步后使用 `tmux` 后台运行模型或 CARLA 客户端任务，并查询日志与退出码。
- `tools/server_fetch_results.cmd`：只回收指定服务器输出目录中的 CSV、JSON、Markdown、文本和日志；默认跳过大于 20 MB 的文件及原始传感器帧。

## 技术栈
- **当前验证基线**：CARLA 0.9.16 位于 `F:\Carla\carla-0.9.16`；独立 Conda 环境 `Carla666-0916` 使用 Python 3.12.13、CARLA Python API 0.9.16、NumPy 2.5.0、Pillow 11.1.0、PyTorch `2.12.1+cu126` 和 TorchVision `0.27.1+cu126`。RTX 4060 CUDA 张量测试通过，`pip check` 无依赖冲突。
- **服务器运行基线**：实验室服务器 `factory22-srv` 已在 `/home/zhaozirong/software/envs/Carla666-0916` 建立 Python 3.12.13 环境；CARLA 0.9.16 位于 `/home/zhaozirong/software/carla-0.9.16`。CARLA PythonAPI、PyTorch CUDA、`Town10HD_Opt` 无桌面连接、项目单场景和完整项目批次均已在 GPU 1 通过。启动时必须使用 `CUDA_VISIBLE_DEVICES=1` 和 `-graphicsadapter=1`，避免占用运行 vLLM 的 GPU 0。
- **服务器模型依赖**：NumPy 2.5.0、PyTorch `2.12.1+cu126`、TorchVision `0.27.1+cu126`、Pandas 3.0.3、SciPy 1.18.0、Scikit-learn 1.9.0、Joblib 1.5.3、Matplotlib 3.11.0、Gymnasium 1.3.0 和 Stable-Baselines3 2.9.0 已安装，`pip check` 无冲突；LHS、GMM、CVAE 各生成 `32/32` 条高风险候选并完成统一离线评估，风险代理复训结果为 MAE `5.515`、RMSE `10.138`。
- **服务器批次验收**：`rainy_night_variants` 的 5 个变体 × 3 个交通种子已完成 `15/15`，传感器完整率和 CARLA 服务健康率均为 `100%`，RGB/Depth/SemSeg 共记录 `9000` 帧且无碰撞。`batch_runner.py` 支持 `--output-root` 和 `--traffic-manager-port`；服务器批次使用 TM 端口 `8100`，避开现有服务占用的 `8000/8001`。
- **双端开发基线**：笔记本作为代码、配置、测试和 Git 提交端；服务器作为模型训练、候选生成、风险分析、CARLA 仿真和批量实验执行端。日常代码通过内网 `lab` 远端同步，形成实质且已验证的阶段进展时同步推送 GitHub `origin`；服务器运行工作区禁止直接修改代码。
- **历史结果保留**：CARLA 0.9.15 的配置、清单、聚合结果和 `834` 个结构化运行文件仍保留；0.9.15 程序、Python 环境、压缩包和约 `14.24 GiB` 原始 PNG/NPY 帧已删除，不再作为可直接运行的复现环境。
- **总体研究核心**：PyTorch、GAN/VAE/扩散模型、物理约束或 PyBullet、强化学习、OpenSCENARIO/CARLA 适配。
- **平台工程计划**：首期 Python 标准库 Web 服务 + 原生 HTML/CSS/JavaScript，继续使用结构化 JSON/CSV；参数级物理约束使用 CPU 标准库实现；后续按写入、任务队列和权限需求评估 FastAPI/SQLite，React/Vue/Streamlit 均不作为当前首期依赖。

## 存储路径与缓存
- 项目环境、CARLA、模型、运行输出和开发缓存默认使用 `F:\`；项目规则已写入根目录 `AGENTS.md`。
- 当前 CARLA 运行时位于 `F:\Carla\carla-0.9.16`，项目输出位于 `F:\Carla\output-0.9.16`，Conda 根目录和 `Carla666-0916` 环境位于 `D:\ANACONDA`。
- Ubuntu 服务器没有 `F:\`，其运行时例外放在 `/home/zhaozirong/software`；`/data` 当前无写权限，项目源码和结构化数据已同步到 `/home/zhaozirong/projects/carla-extreme-scenario-generator`。模型产物位于 `/home/zhaozirong/software/models/carla-extreme-scenario-generator`，批次与模型验证输出位于 `/home/zhaozirong/software/output/carla-0.9.16`。
- 笔记本与服务器的临时交换目录为 `F:\Carla\project-transfer`。服务器模型权重、原始 RGB/Depth/SemSeg 和完整运行输出不回传；只将经过筛选的结构化汇总和少量示例图回收到笔记本，再决定是否纳入 Git。
- 原 `C:\Users\z'z'r\AppData\Local\pip\cache` 仅为可再生成的 pip 下载缓存，已清理约 `15.94 GB`；后续 `PIP_CACHE_DIR` 指向 `F:\Carla\project-cache\pip`。
- 原 `C:\Users\z'z'r\.cache\torch` 已迁移至 `F:\Carla\project-cache\torch`，原位置保留目录联接；`TORCH_HOME` 指向 F 盘。`HF_HOME` 和 `CONDA_PKGS_DIRS` 也已指向 `F:\Carla\project-cache` 下对应目录。
- `C:\Users\z'z'r\.cache\codex-runtimes` 属于 Codex 运行时缓存，未迁移；`C:\Users\z'z'r\AppData\Local\Temp` 属于系统临时目录，未整体移动或删除。二者是当前明确记录的 C 盘例外。

## 当前风险与约束
- `heuristic_v2` 的天气可见度来自 CARLA 参数代理，不是 RGB 图像实测能见度；指标用于同一场景族内部工程筛选。
- 每个变体目前只有 3 个随机种子，适合 Demo 对比，不足以形成统计显著性结论。
- `late_braking` 的 V2 风险为 `49.137 ± 22.718`，场景语义和稳定性仍不足。
- `seed_v1` 的风险等级和模型输出中的 `target_risk_level` 均是参数设计目标，不能视为真实风险标签；除前两轮 16 条 CVAE 样本外，`generator_comparison_v1` 已新增 36 个独立场景、108 次重复测量的 CARLA 实测 `observed_risk`。离线有效率仍不能替代 Actor 生成、场景完成和风险评分的实机证据。
- 当前 CVAE 主要学习人工设计的参数区间和相关关系，训练样本仅 `256` 条；它是参数生成与闭环接口基线，不代表已学习真实交通分布。
- 当前离线与实测结果均显示规则/LHS 在设计区间一致性和目标档命中率上强于 CVAE；CVAE 的后续价值需要通过实测风险反馈搜索证明。
- 两轮累计 16 条 CVAE 样本全部成功运行，说明参数生成到 CARLA 执行和风险回填链路已打通；但人工目标档与 `heuristic_v2` 实测档仍存在系统偏差，累计目标档命中 `6/16`，不能直接把设计条件当作模型已实现的风险控制能力。
- 第二轮进一步显示：参数设计档位与平均实测分数存在正向排序，但档位边界命中较差；低/中风险内部方差较大，高风险可跨越 medium 至 critical。`heuristic_v2` 的非碰撞权重总和为 `0.75`，而 critical 阈值为 `75`，因此无碰撞场景只有在其余风险分量全部达到最大值时才能进入 critical，这可能是临界目标持续落入 high 的结构性原因，需在更多重复实验后审查指标定义。
- 第一轮重复性诊断中，场景内分数标准差均值为 `13.353`、中位数为 `20.133`、最大值为 `22.781`，三个交通种子的整体平均分极差达到 `22.243`；当前最大干扰不是传感器或 CARLA 服务稳定性，而是未锁定的车辆路线/车道行为改变了前车危险是否真正作用于主车。
- 第二轮小规模回归中三个种子的得分完全一致，说明交通种子导致的随机分支跳变暂时消失；但 `TrafficManager.set_path` 未将主车持续约束在计划路径上，严格验收 `0/9`。当前不能把“零方差”直接归因于路线锁定成功，必须先修正控制器并复测。
- 新控制器已在 12 个固定 CVAE 场景、三个交通种子的 36 次回归中严格验收 36/36；当前可以表述为“受控工程重复性验证通过”，但三个种子仍不足以支持统计显著性声明，也不能外推到未测试场景。
- V4 唯一档位翻转样本的连续分数范围为 `24.283—25.078`，离散变化来自 `medium=25` 的边界；重复性判断继续以连续分数标准差和极差为主，档位一致率为辅。
- V4 高风险目标 9 次均稳定为 `medium`，临界目标也未达到 `critical`；三生成器同控制器实测对照进一步确认 CVAE 风险偏保守。不能通过弱化控制器或直接修改标签提高命中率，下一步应使用实测风险反馈改进候选搜索，并同步审查风险指标边界。
- 三生成器对照中每个“生成器 × 目标档”只有 3 个独立场景；三个交通种子是重复测量。因此本轮只支持工程描述性比较，不进行统计显著性检验。
- 风险反馈 V1 已将 108 次严格验收运行聚合为 36 个独立场景；15 维参数不含 `target_risk_level` 和 `generator` 输入。按 `generator × target_risk_level` 分层三折交叉验证，随机森林代理 MAE `5.515`、RMSE `10.138`、Spearman `0.902`，高及以上风险召回率 `75%`；该结果只支持候选排序基线，不代表真实交通风险预测能力。
- 风险代理诊断 V1 已在服务器完成 50 次重复分层三折 OOF。随机森林 MAE 为 `5.686 ± 0.289`、RMSE `10.124 ± 0.368`、Spearman 均值 `0.898`；Top-9 两两 Jaccard 均值 `0.708`，仅 6 个样本的 Top-9 入选率达到 80%。随机森林与 Ridge 的排序 Spearman 均值为 `0.910`、Top-9 Jaccard 均值为 `0.678`，说明总体排序方向较一致，但候选边界仍有明显波动。
- 当前 3 个碰撞场景的随机森林 MAE 为 `30.145`、平均偏差 `-30.145`，其余 33 个非碰撞场景 MAE 为 `3.462`；最大误差场景 `gmm_critical_20260813_0004` 被低估 `33.162` 分。现阶段不使用仅 3 个正样本训练碰撞分类器，而将碰撞边界作为独立主动补样通道；连续风险代理继续用于非碰撞候选预排序。
- 反馈候选评分 V1 已在服务器完成：LHS、GMM、CVAE 分别在 `high` 和 `critical` 生成 `256` 条，共 `1536` 条候选；统一使用 50 个按 `generator × target_risk_level` 分层 Bootstrap 的随机森林，输出预测均值、标准差、稳健分、重复 Top-K 入选频率、碰撞/非碰撞最近距离和多样性选择距离。
- 首次统一选择时 27 个候选全部塌缩到 `critical`，会把通道效果与目标档差异混杂；现已增加目标档配额并重新完成正式评分。最终每种生成器固定选择 9 条，其中稳定高分、高不确定性、碰撞边界各 3 条，且统一为 `high=3`、`critical=6`，总计 27 个唯一短名单。结果保存在 `data/scenarios/feedback_candidate_scoring_v1/`。
- 最终短名单的平均稳健预测分为 CVAE `53.523`、GMM `55.723`、LHS `56.103`；这些数值只表示旧风险代理下的候选优先级，不能解释为 CARLA 实测危险性，也不能据此宣布某个生成器更优。
- 反馈短名单外部验证 V1 已完成：27 个独立场景各覆盖三个 Traffic Manager 种子，共 `81/81` 次运行完成，传感器、CARLA 服务和碰撞感知路线验收均为 `81/81`。无碰撞运行继续验收全程路线；碰撞运行验收首次碰撞前路线，碰撞后全程指标仍保留，碰撞前偏离路线仍判失败。
- 27 个新增场景中高风险及以上 `24/27`、碰撞 `15/27`；81 次运行中碰撞 `45/81`。按生成器统计，CVAE、GMM、LHS 的高风险及以上分别为 `9/9`、`7/9`、`8/9`，碰撞场景分别为 `6/9`、`5/9`、`4/9`，实测均值分别为 `73.203`、`70.398`、`65.889`。
- 旧风险代理在外部验证上的 MAE 为 `18.055`、RMSE 为 `21.002`，预测均值与实测风险 Spearman 为 `-0.025`，稳健分 Spearman 为 `-0.018`，Top-9 重合 `4/9`、Jaccard `0.286`。当前证据说明旧代理能筛到危险区域，但在高风险区域内部排序基本失效，必须用新增实测反馈复训而不能继续直接复用 V1 排序。
- 风险反馈数据集 V2 已将原 36 个场景与新增 27 个场景合并为 63 个独立场景，三个生成器各 `21` 个，碰撞场景共 `18` 个；合并工具校验字段、重复种子、`sample_id` 去重和来源哈希，重新生成的 `dataset.csv` 哈希一致。正式 V2 代理训练和 50 次重复分层三折 OOF 在服务器执行，模型权重不回传 Git。
- 风险代理 V2 的随机森林 50 次重复 OOF MAE 为 `11.536`、RMSE 为 `14.343`、Spearman 为 `0.740`；同口径 Top-9 两两 Jaccard 由 V1 的 `0.708` 降为 `0.339`。碰撞场景 MAE 由 `30.145` 降为 `18.521`，但整体误差与排序稳定性变差，说明 V2 缓解了碰撞低估却不能作为单一连续风险排序器直接替代 V1。
- 独立碰撞倾向通道已完成 50 次重复三折 OOF：18 个碰撞正样本、45 个非碰撞负样本；随机森林 Average Precision 为 `0.532 ± 0.084`、ROC-AUC 为 `0.768 ± 0.052`、Recall 为 `0.689 ± 0.131`、F1 为 `0.557 ± 0.081`。该结果支持保留碰撞主动补样通道，但不支持跨地图或跨控制策略的碰撞概率声明。
- 双通道候选评分已完成：在 `1536` 个候选、5 轮重复和每轮 30 个 Bootstrap 模型上，单风险通道与双通道各选出 `27` 个候选，交集 `18` 个，Top-27 Jaccard 为 `0.500`；双通道候选平均碰撞倾向为 `0.784`，单风险通道为 `0.723`，但双通道稳定性为 `0.404`，略低于单风险通道的 `0.431`。该结果支持双通道提高碰撞边界覆盖的假设，但尚不能证明实测收益。
- 双通道配对验证计划已生成：单风险通道独有 `9` 个、双通道独有 `9` 个，共 `18` 个独立场景 × `3` 个 Traffic Manager 种子 = `54` 次计划运行；`54/54` 份配置已静态校验通过，尚未进行 CARLA 实机验证。计划目录为 `F:\Carla\project-transfer\server-results\plan_20260816_092656`。
- 双通道配对计划单样本冒烟已通过：客户端/服务端均为 CARLA `0.9.16`，路线控制启用，RGB 写盘 `100` 帧，严格验收通过，风险分 `48.886`、等级 `medium`、碰撞 `0`，CARLA 服务健康检查通过；该结果只证明执行链路可用，不代表 54 次整体结论。
- 双通道配对实机验证已完成：`54/54` 次运行完成并严格验收，传感器写盘、路线验收和 CARLA 服务健康均为 `54/54`；聚合为 `18` 个独立场景，其中 `6` 个碰撞场景、`905` 个碰撞事件。9 组生成器×目标档配对中，双通道独有相对单通道独有的实测风险均值差为 `-1.847`，双通道更高 `4` 组、单通道更高 `5` 组；两侧碰撞场景均为 `3/9`，没有碰撞结果不一致的配对。因此本轮不支持“双通道提高碰撞发现率”的结论，双通道暂保留为候选研究分支而非默认工程策略。
- 双通道外部排序整体指标为 MAE `16.372`、RMSE `16.813`、稳健排序 Spearman `0.575`、Top-9 重合 `6/9`、Jaccard `0.500`；这些结果来自旧代理主动筛选的 `18` 个场景，不能外推到原始生成器总体。
- 风险反馈 V3 已将 V2 的 `63` 个独立场景与本轮新增 `18` 个场景合并为 `81` 个独立场景，碰撞场景 `24` 个。随机森林基线 MAE `11.846`、RMSE `14.403`、Spearman `0.745`；50 次重复 OOF 为 MAE `11.769 ± 0.374`、RMSE `14.319 ± 0.500`、Spearman `0.743`，碰撞场景 MAE `18.376`。V3 支持继续作为候选预排序器，但不代表双通道已经优于单通道。
- V3 候选重评分已完成：沿用 `1536` 个候选、5 轮重复和每轮 30 个 Bootstrap 模型，单通道与双通道各选 `27` 个，交集 `19` 个，Jaccard `0.543`；双通道候选平均碰撞倾向 `0.609`，单通道碰撞相关通道候选为 `0.568`。相较 V2，Jaccard 从 `0.500` 小幅升至 `0.543`，但双通道碰撞倾向从 `0.784` 降至 `0.609`，不能据此启动新一轮大规模 CARLA 验证。
- 碰撞边界主动补样 V1 已完成：从 V3 候选池按 `3` 个生成器 × `high/critical` 两档 × 每格 `3` 个选择 `18` 个独立场景；每个单元包含 `2` 个 `collision_boundary` 和 `1` 个 `high_uncertainty` 候选，三个 Traffic Manager 种子共 `54/54` 次运行。四类传感器配置均启用，RGB、Depth、Semantic 各 `100` 帧，传感器、路线和 CARLA 服务严格验收均为 `54/54`；最大路线偏差不超过 `1.000 m`。
- 主动补样 V1 的 `18` 个独立场景中，`13` 个为实测 high/critical，`5` 个发生碰撞，共 `2185` 个碰撞事件；外部 MAE `12.029`、RMSE `13.051`、预测均值 Spearman `0.542`、稳健分 Spearman `0.534`，Top-9 重合 `6/9`、Jaccard `0.500`。`collision_boundary` 通道为 `12` 个场景、`4` 个碰撞场景；`high_uncertainty` 通道为 `6` 个场景、`1` 个碰撞场景。由于通道配额不同，该结果只作主动补样描述性证据，不作通道因果比较。
- 主动补样结果和 `feedback_dataset_addition.csv` 已回收至 `F:\Carla\project-transfer\server-results\collision_boundary_multisensor_v1_20260816_220532\plan`；下一轮将把 `18` 个独立场景合并入风险反馈 V4，重新训练代理并进行重复 OOF 校准。
- 风险反馈 V4 已将 V3 的 `81` 个独立场景与主动补样新增的 `18` 个场景合并为 `99` 个独立场景，三个生成器各 `33` 个，碰撞场景 `29` 个。随机森林 50 次重复分层三折 OOF 的 MAE 为 `11.617 ± 0.368`、RMSE `14.149 ± 0.468`、Spearman `0.706`，目标档预测均值严格递增率为 `100%`。
- V3/V4 同口径 Top-9 对比中，V4 相对 V3 的 MAE 改善 `0.152`、RMSE 改善 `0.171`，但 Spearman 从 `0.743` 降至 `0.706`、Top-9 两两 Jaccard 从 `0.375` 降至 `0.296`，碰撞场景 MAE 从 `18.376` 升至 `18.946`。V4 可作为包含更多反馈的粗筛数据池，但不能直接替代 V3 作为唯一精细排序依据。
- 风险分数拆解校准 V1 已完成：在 99 个场景上分别预测连续风险分量与碰撞运行率，再按 `heuristic_v2` 原权重合成。单模型与拆解模型 MAE 分别为 `11.588` 和 `11.567`，Spearman 为 `0.708` 和 `0.710`，Top-9 两两 Jaccard 为 `0.310` 和 `0.316`；拆解模型碰撞场景 MAE 反而由 `18.903` 升至 `19.006`，不具备替换价值。
- 使用真实碰撞运行率的诊断上限模型 MAE 为 `3.298`、Spearman `0.943`、碰撞场景 MAE `5.222`，说明当前主要瓶颈不是 `heuristic_v2` 的碰撞权重，而是 15 维静态参数对碰撞边界的预测能力。V4 独立碰撞分类器 50 次 OOF 的 AP 为 `0.508 ± 0.064`、ROC-AUC `0.733 ± 0.038`、Recall `0.605 ± 0.112`，较 V2 未改善；碰撞通道继续仅用于主动补样和研究诊断，不作为连续风险概率声明。
- 物理交互派生特征增强 V1 已完成：在 V4 的 `99` 个独立场景、`29` 个碰撞场景上执行 50 次重复分层三折 OOF。相较原始 15 维参数，加入 12 个生成前可计算的物理特征后，MAE 从 `11.594 ± 0.379` 降至 `10.727 ± 0.379`，Spearman 从 `0.707` 升至 `0.780`，Top-9 两两 Jaccard 从 `0.284` 升至 `0.325`，碰撞场景 MAE 从 `18.912` 降至 `17.714`；碰撞分类 AP 从 `0.499` 升至 `0.668`，ROC-AUC 从 `0.729` 升至 `0.810`。
- 物理增强同时改善总体误差、碰撞子集误差和 Top-K 稳定性，达到候选重评分入口条件。当前不修改 `heuristic_v2` 权重，也不立即追加 CARLA 大批次；下一步先在现有 LHS/GMM/CVAE 候选池上做同口径增强代理重评分，并保留不确定性、多样性和碰撞边界配额。正式结果已回收到 `F:\Carla\project-transfer\server-results\20260817_100941_20260817_102220`。
- 物理增强候选重评分 V1 已完成：LHS/GMM/CVAE 在 high/critical 两档各生成 `256` 个，共 `1536` 个候选；原始 15 维与物理增强 27 维均执行 `5` 次评分重复、每次风险回归和碰撞分类各 `30` 个 Bootstrap 随机森林。两套候选风险排序 Spearman 为 `0.960`，候选风险均值绝对变化 `1.781`；增强评分提高 `485` 个候选、降低 `1051` 个候选。
- 原始与增强短名单变化明显：单通道和双通道的 27 场景交集分别为 `12` 和 `11`，Jaccard 分别为 `0.286` 和 `0.256`。增强双通道短名单的平均碰撞倾向由 `0.619` 升至 `0.652`，平均选择多样性距离由 `0.0841` 升至 `0.0906`，5 次重复选择 Jaccard 均值由 `0.397` 升至 `0.469`；增强特征提供了原始 15 维之外的有效候选边界信息。
- 候选重评分仍是离线预排序证据，不能直接解释为 CARLA 实测风险改善。下一轮采用小规模平衡配对：从 `3` 个生成器 × `3` 个选择通道的差异槽位中各取 `1` 对原始/增强候选，共 `9` 对、`18` 个独立场景、`3` 个 Traffic Manager 种子，计划 `54` 次严格验收运行；先生成计划和执行单场景冒烟，再决定是否运行完整批次。正式重评分结果已回收到 `F:\Carla\project-transfer\server-results\20260817_114055_20260817_115539`。
- 候选重评分仍是离线预排序证据，不能直接解释为 CARLA 实测风险改善。正式配对验证已完成：`54/54` 次严格验收、`18/18` 个独立场景完整、`9/9` 对原始/增强候选成功匹配。物理增强侧实测均值 `73.568`，原始 15 维侧 `65.531`，配对平均差 `+8.037`；物理增强侧外部 MAE `12.797`，原始侧 `15.503`，碰撞场景 `6/9` 对 `4/9`。但仅 `5/9` 对中物理增强实测更高，当前结论是“支持物理增强作为优先实验评分分支”，不支持移除原始基线或宣称普遍优势。结果归档于 `data/scenarios/physical_feature_validation_v1/`，完整轻量报告回收于 `F:\Carla\project-transfer\server-results\plan_20260817_134902`。
- 风险反馈 V5 已完成：V4 的 `99` 个独立场景与物理增强配对验证的 `18` 个场景合并为 `117` 个，LHS/GMM/CVAE 各 `39` 个，碰撞场景 `39` 个。50 次重复三折 OOF 中，27 维物理增强相对原始 15 维将 MAE 从 `12.012` 降至 `10.986`、Spearman 从 `0.686` 提升至 `0.781`、碰撞场景 MAE 从 `17.527` 降至 `16.169`、碰撞 AP 从 `0.535` 提升至 `0.686`；随机森林物理增强代理已冻结为优先评分分支，模型权重保存在服务器且不进入 Git。
- 场景库 V1 已完成 V5 扩库：构建器读取三生成器对照与风险反馈 V5 共 `153` 条输入，按 15 维物理参数内容哈希去除 `36` 条重复，最终保留 `117` 个独立场景、`351` 次严格验收运行证据，排除 `0`；LHS/GMM/CVAE 各 `39` 个，实测 high/critical `72` 个，碰撞场景 `39` 个。历史首批 `36` 个条目保留逐次运行证据并评为 `silver`，V5 新增 `81` 个条目仅保留场景级聚合血缘并评为 `bronze`；全部真实性仍为 `not_assessed`，CARLA 版本字段保持 `unknown`，不伪造缺失的逐次运行路径或版本记录。
- 场景库受控查询已完成：`core/scenario_query.py` 统一 CLI 与 `GET /api/scenarios/search` 的结构化字段、范围校验和白名单关键词匹配；定向回归 14 项通过。查询只读索引，不解析自然语言、不启动 CARLA、不产生新的风险证据。
- 场景库质量分析基线已完成：`117` 个场景中实测 high/critical `72` 个、碰撞 `39` 个；目标档与实测档完全命中 `50/117`，目标序号与实测分数 Spearman `0.708`；GMM/LHS/CVAE 平均风险分为 `59.647/56.947/56.461`，碰撞场景率为 `38.5%/30.8%/30.8%`。这些是当前压力测试库的描述性统计，不构成生成器总体优劣结论。
- 质量分析同时确认：`36` 个条目为逐次证据/silver，`81` 个为聚合证据/bronze；全部条目场景级 CARLA 版本仍为 `unknown`，真实性均为 `not_assessed`，`30` 个条目被标记为低相对多样性。完整报告位于 `data/scenarios/scenario_library_v1/quality_analysis_v1/quality_analysis_report.md`。
- 场景库接口回归测试已完成：14 项标准库 `unittest` 全部通过，覆盖构建器与质量分析校验、117 条快照、5 组查询契约、CSV 文件导出、Dashboard 数据/HTTP 接口、严格验收负例和直接/继承证据分层；质量门配置位于 `configs/scenario_library_quality_gate_v1.json`。
- 首批场景的可执行性、证据完整性、重复性、危险性和库内参数多样性已评估，真实性因缺少同口径真实世界参考分布保持 `not_assessed`。历史三生成器对照未记录 CARLA 客户端/服务端版本字段，因此 `36` 个条目均为 `partial/silver`，不能将原批次严格验收通过误写成真实性或证据完整性满分。
- 多传感器低频冒烟已通过：RGB、Depth、Semantic 各写盘 `100` 帧，队列无失败，CARLA 服务健康；`heuristic_v2` 风险分为 `29.708/medium`。同为 `100` 帧时，RGB-only 传感器目录约 `21.3 MB`，RGB+Depth+SemSeg 约 `55.5 MB`，约为 `2.6` 倍。当前风险评分不读取图像像素，因此多传感器主要提供视觉证据、深度几何和未来感知模型输入，不直接提高现有启发式风险分析。
- 传感器策略已冻结为两档：大批量生成与风险代理训练使用 `RGB + Collision` 性能基线；主动补样、论文/软著展示和后续视觉风险模型使用 `RGB + Depth + Semantic + Collision` 低频证据配置，不把多传感器强行加入全部批次。
- 服务器生成的本轮结果目录使用 `20260816` 时间戳，与项目当前日期 2026-08-16 一致。
- 本轮唯一的初次路线失败在相同配置重跑后恢复为双车全程在途、路线偏差小于 `1.01 m`；当前按偶发运行状态处理，但后续批次仍保留路线严格验收，不能删除该质量门槛。
- 截至 2026 年 8 月 18 日，阶段二和阶段三已形成可复现工程基线：三生成器 108/108 严格实测对照、反馈短名单 81/81、双通道配对 54/54、碰撞边界主动补样 54/54、物理增强配对 54/54 均通过严格验收；风险反馈 V5、50 次重复 OOF、27 维物理增强代理、场景库质量门、当时的 M01–M07 接口规格和 Dashboard 页面级回归均已完成。随后阶段四完成硬质量门和当前证据收口，阶段五已把材料口径扩展至 M01–M08；项目不再无边界扩展阶段二实验。
- 实验室双 RTX 4090 服务器 `factory22-srv` 已完成 CARLA 0.9.16、Python 3.12.13、完整模型依赖、三生成器推理、风险代理复训和 15 次项目批次验证。后续完整模型训练和 CARLA 批量实验默认迁移到服务器 GPU 1，本地 RTX 4060 仅保留代码开发、快速静态校验和故障回退；GPU 0 继续保留给现有 vLLM 服务。
- GPU 1 还存在一个由 root 管理的 TensorRT 推理服务，当前显存占用约 `896 MiB`，项目不得终止或修改该服务。项目工作流使用 `/home/zhaozirong/software/output/carla-0.9.16/.workflow_gpu1.lock` 防止自身的模型任务与 CARLA 相互并发，但该锁无法约束外部服务；重型实验前必须先运行服务器状态检查并确认剩余显存。
- 长时间多传感器运行仍可能产生硬件压力，但帧完整性和服务健康检查已作为批次验收条件。
- 0.9.15 历史清单中的 `metadata_path`、`run_dir` 和 CMD 仍保留实验发生时的原始绝对路径，仅用于来源追溯；当前活动工具默认使用项目仓库场景运行器和 `F:\Carla\output-0.9.16`，不得直接执行旧脚本污染历史结果。
- CARLA 0.9.16 三种子迁移回归已严格验收 `3/3`：每次 RGB `100` 帧，传感器、服务健康和路线验收全部通过，双车同时在途率均为 `1.0`，最大路线偏差不超过 `1.000 m`，无碰撞，风险档均为 `medium`。同配置平均风险分由 0.9.15 的 `27.760` 变为 `27.491`（`-0.97%`）；0.9.16 风险分样本标准差为 `0.587`、极差为 `1.137`，相对波动增大但未影响工程验收。当前样本仅一个场景、三个种子，不作统计显著性结论。
- 2026-08-24 `seed_v1_high_0165` 已完成 ScenarioRunner 关联完整验收：RGB/Depth/Semantic 各 `200` 帧、Collision 独立状态门通过且事件 `0`，waypoint 路线双车在途率 `1.0`、最大偏差 `0.992/0.995 m`，`heuristic_v2` 风险 `40.843/medium`，统一 `13/13` 检查通过；原始帧仅保留服务器，轻量证据回收到 `F:\Carla\project-transfer\scenario_runner_v1_full_acceptance_20260824_145339`。
- 项目代码统一由本地 `main` 管理；完成实质且已验证的任务后自动提交，形成阶段性进展且远端可用时自动推送 GitHub `origin`，随后通过内网 `lab` 同步服务器运行工作区。`项目进度文档.md` 已由用户主动删除，后续以 `PROJECT.md` 维护项目当前状态。

## 笔记本—服务器工作流
当前内网裸仓库、服务器运行工作区和本地 `lab` 远端已经建立；服务器工作区由同步脚本保持与当前已提交版本一致。代码同步底层流程、Python 后台任务、轻量结果回收、CARLA 启停、GPU 互斥锁和 CARLA Python API 地图连接均已实测通过。

1. **笔记本开发与校验**：只在 `D:\Xx\竞赛\大创实施ing` 修改代码、配置和测试；先完成静态检查或轻量测试，再创建 Git 提交。PowerShell 执行策略由 `.cmd` 入口以单进程 `Bypass` 处理，不修改系统全局策略；`.gitattributes` 强制服务器 Bash 脚本使用 LF 行尾。
2. **内网同步代码**：在工作区干净且位于 `main` 分支时运行 `tools\server_sync.cmd`。脚本把当前提交推送到服务器裸仓库 `lab`，随后对服务器运行工作区执行 `git merge --ff-only`；服务器仓库固定 `core.autocrlf=false`，并在前置脏工作树检查通过后以当前提交重建工作树，确保 `.sh` 保持 LF；不会自动推送 GitHub，也不会覆盖服务器未提交改动。
3. **管理 CARLA**：运行 `tools\server_carla.cmd -Action Start|Status|Stop`。CARLA 固定使用 GPU 1、RPC 端口 `2000`、`-RenderOffScreen` 和 `-graphicsadapter=1`；启动和停止均已在服务器实测通过。
4. **提交后台任务**：简单命令运行 `tools\server_run.cmd -Name <job-name> -Command "<Linux command>" [-RequiresCarla] [-Wait]`；包含 Python `-c`、多层引号或多行逻辑时，优先写入本地 UTF-8 命令文件并使用 `-CommandFile <path>`，避免 Windows CMD 引号破坏。脚本默认先同步代码，再在服务器 `tmux` 中执行；非 CARLA GPU 任务持有项目 GPU 锁，CARLA 客户端任务用 `-RequiresCarla` 检查 RPC 服务后运行。任务目录固定为 `/home/zhaozirong/software/output/carla-0.9.16/remote_jobs/<job-id>`，并保存提交哈希、起止时间、日志和退出码。
5. **查询与回收结果**：使用 `tools\server_job_status.cmd [-JobId <job-id>]` 查看任务；使用 `tools\server_fetch_results.cmd -RemotePath <server-output-directory>` 将轻量汇总回收到 `F:\Carla\project-transfer\server-results`。默认不下载模型权重、NPY 和原始传感器帧；只有明确指定 `-IncludeSampleImages` 时才回收小于阈值的示例图。
6. **版本与数据边界**：服务器运行结果必须能够追溯到 Git 提交、配置、随机种子和输出目录。服务器工作区不直接编辑；发现问题后回笔记本修改、提交并重新同步。GitHub `origin` 用于阶段备份和对外同步，内网 `lab` 用于高频开发部署；两者均只接收已验证且不含大文件或敏感信息的提交。

## 下一步
1. 下一项进入阶段五核心质量收口：完成 Web 产品流程的真实演示取证并复核软著材料；`S5-WEB-03` 仍等待功能冻结后执行。计划书指标 baseline 已补齐，但原始目标的实车路测/人工计时/行业覆盖分母仍需单独证据，不能用当前代理替代。
2. 保持阶段四实验口径和结论冻结，以 `docs/stage4_quality_gate_and_experiment_closure_v1.md` 作为论文、软著与结题材料的证据边界入口。
3. Web 生成/校验/风险页面已经完成首期产品化，不再重复建设同一层原型；后续只补真实演示证据、权限/部署等明确需求。在线 RL 泛化和 PyBullet/MJX 研究闭环单独排期；当前 MJX 前向默认按规模选择服务器 CPU/GPU1，GPU1 优先用于 batch 自定义 VJP 等受益场景并受显存上限约束；双刚体稳定区与相向运动接触边界已完成 CPU 证据，但接触真实性仍有失败区间，GPU1 复核待 CARLA 释放项目锁后执行，`iterations=1` 不作为默认物理求解方案，自定义 VJP 暂不接入高维长时序训练。ScenarioRunner 已完成一条原生直执行和一条关联样本的 Scene 04 完整多传感器/路线/风险验收，跨地图与批量泛化仍不宣称。
4. 维护 `docs/stage5_material_index_v1.md` 中的一键演示 `demo_manifest.json` 路径、SHA-256、关键计数和重建命令；不把历史风险证据写成新 CARLA 实测。
5. 本次完整验收结束后 CARLA 应保持停止；GPU1 仅保留 root 管理的 TensorRT 服务，GPU0 的 vLLM 不修改。后续 GPU/CARLA 任务启动前重新检查服务和显存状态。
