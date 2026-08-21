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
- **最后更新**：2026-08-21

## 当前阶段
**大创总体已完成阶段三“极端场景库与质量评估”的收口条件，当前进入阶段四“仿真平台与对抗性测试代理”。风险反馈 V5 已合并为 `117` 个独立场景，其中 `39` 个碰撞场景；27 维物理增强代理在 50 次重复 OOF 中取得 MAE `10.986`、Spearman `0.781`、Top-9 Jaccard `0.304`，并冻结为后续候选评分的优先实验分支，原始 15 维继续作为可复现实验基线。场景库 V1 已完成 V5 扩库：统一条目 Schema、来源追踪、内容哈希去重、质量分层、CSV 索引、离线查询接口、软著模块映射、M01–M07 接口规格和 Dashboard 页面级回归均已建立，共收录 `117` 个独立场景与 `351` 次来源批次严格验收运行；其中 `36` 个条目为直接逐次证据，`81` 个条目为批次继承证据。**

当前完成的是一套 **CARLA 极端场景仿真 Demo**，它是后续生成式 AI 场景生成、物理校验和自动化测试的仿真底座，不是项目终点，也不是最终软件封版。风险指标 V2 已完成离线分析和 CARLA 实机回归。

CARLA 0.9.16 独立环境 `Carla666-0916` 已安装 Python API 0.9.16；客户端/服务端版本、`Town10HD_Opt` 地图加载、项目配置静态校验和同一冻结场景三个交通种子的完整严格回归均已通过。从 2026-08-15 起，后续新增实验统一使用 0.9.16。CARLA 实机任务遵循“服务器优先、连接或健康检查失败后回退本机”的规则；服务器使用配置中的 `Carla666-0916`，本机固定使用 `D:\ANACONDA\envs\Carla666-0916`。CARLA 0.9.15 程序、旧运行副本、安装包、旧 Conda 环境和本机残留 Python 包均已删除；历史 JSON、CSV、日志和说明文件仅作为证据保留，历史原始传感器帧不再保留。
服务器已部署并实测导入 `AdditionalMaps_0.9.16.tar.gz`，可用地图数为 `21`，`Town06` 与 `Town07` 已成功加载验证。

阶段一中的 CARLA 环境、场景参数化、多传感器采集和批量验证已完成；生成式 AI 相关文献已完成第一轮收集和模型选型调研（56 篇索引、46 篇本地 PDF），公开数据集调研仍需补齐。阶段二已完成 15 维统一表示、种子数据集、条件 GMM、轻量条件表格 CVAE、多随机种子训练、离线评估、受控重复性验证、三生成器 108 次严格验收、风险反馈 V1—V5、碰撞边界主动补样、物理交互派生特征增强、候选重评分和配对实机验证；冻结的 27 维随机森林代理保留服务器模型权重与本地轻量结论。阶段三从统一场景库 V1 的数据契约和质量评估入口开始。

## 整体阶段顺序
1. ✅/▶ **基础调研与环境搭建**：CARLA、Python、Git/GitHub 和仿真底座已完成；生成式 AI 文献第一轮收集和模型选型已完成，公开数据集收集与预处理仍需补齐。
2. ✅ **生成式 AI 模型与物理约束**：场景 Schema、独立校验器、种子数据集、LHS/GMM/CVAE、确定性控制器、严格验收、风险反馈 V1—V5、物理增强代理与配对实机验证均已形成可复现工程基线；潜空间条件 Flow 延后评估，不作为阶段二完成条件。
3. ✅ **极端场景库与质量评估**：统一条目、来源追踪、哈希去重、真实性/多样性/危险性/可执行性指标、结构化检索索引、质量分析基线、接口回归门槛、软著模块映射、接口规格和 Dashboard 页面级回归均已完成；软著演示截图后置到正式申请准备阶段。
4. ▶ **仿真平台与对抗性测试代理**：当前阶段。OpenSCENARIO/CARLA 最小适配、对抗性测试代理 V1 契约、单步/多步闭环、异常路径编排测试、Gymnasium 外壳、服务器 `check_env`、环境级 CARLA 冒烟、场景库分层采样、四类非学习离线基线、约束感知重采样、60 项 CARLA 静态对照计划和首个 pair 的 5 次实机冒烟已完成；下一步先校准相对基线奖励诊断，再执行剩余 55 次对照，当前尚未训练 RL 模型。
5. ⏳ **系统集成与成果产出**：整合“生成—管理—测试—评估”平台，完成对比实验、论文/软著和结题材料。

## 当前 Demo 子阶段
1. ✅ 极端天气、多危险叠加和行人突发场景。
2. ✅ RGB、Depth、SemSeg 和碰撞传感器集成。
3. ✅ JSON 参数化、同步步进、批次运行和重复统计。
4. ✅ 风险指标 V2、结果图表与离线分析报告。
5. ✅ V2 实机回归；✅ 第一版生成模型离线基线；✅ 两轮 CVAE 生成样本抽样验证；✅ 第一轮 36 次多种子问题诊断；✅ 路线失败诊断；✅ 确定性 waypoint 控制器；✅ V3 九次实机严格验收；✅ V4 三十六次实机严格验收；✅ 三生成器 108 次仿真、严格验收与阶段结论冻结；✅ 风险反馈数据集 V1 与代理基线；✅ 代理误差和排序稳定性诊断 V1；✅ 反馈候选 81 次外部验证；✅ 风险反馈数据集、风险代理和碰撞通道诊断 V2；✅ 双通道离线评分与 54 次配对计划；✅ 双通道 54 次配对实机验证；✅ 风险反馈 V3 合并与复训；✅ V3 候选池重评分；✅ 碰撞边界主动补样 V1 的 54 次多传感器实机验证；✅ 风险反馈 V4、V3/V4 对比和风险分数拆解校准 V1；✅ 物理交互派生特征增强 V1；✅ 1536 候选增强代理重评分；✅ 物理增强配对验证 54/54 严格验收与 9/9 配对分析；✅ 风险反馈 V5 复训与 27 维代理冻结；✅ 场景库 V1 数据契约、117 场景扩库与离线查询入口；✅ 场景库质量分析基线；✅ 构建与查询接口回归测试及质量门冻结；✅ 软著系统模块映射与接口规格；✅ M07 Dashboard 页面级回归；✅ OpenSCENARIO/CARLA 适配器 4.1；✅ 对抗性测试代理 V1 契约；✅ 闭环编排 V1 单步真实冒烟；✅ 闭环编排 V1 多步真实冒烟；✅ 编排失败中止、无效候选恢复与重复场景截断测试；✅ Gymnasium 外壳、服务器 `check_env` 与环境级 CARLA 冒烟；✅ 分层场景采样与四类非学习离线基线；✅ 约束感知重采样与 60 项 CARLA 静态计划；✅ 单 pair 五次 CARLA 严格冒烟；▶ 相对基线 reward 诊断与剩余 55 次对照。

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
- 整理 CARLA Demo 作为仿真底座的接口和验证证据，不把它包装成最终系统。
- 已完成软著系统模块映射 V1：将场景生成、约束校验、场景库、仿真采集、风险分析和实验编排映射到代码入口与运行证据，并明确可视化界面、强化学习代理和完整 OpenSCENARIO 适配仍未完成；文档见 `docs/software_copyright_module_mapping_v1.md`。
- 阶段四 4.1 已形成 `custom_json_to_openscenario_carla_v1`：输入复用 `generated_scenario` Schema，输出 OpenSCENARIO XML 1.0 最小交换子集、Scene 04 CARLA JSON 和哈希清单；天气、传感器、风险算法、Traffic Manager、路线控制器等 CARLA 专属字段保持在旁路配置中。适配器单元回归和 `seed_v1` 全部 `256` 条记录静态转换均已通过，适配器生成的 CARLA JSON 已完成一次运行时冒烟；尚未声称 ScenarioRunner 直接执行兼容。边界见 `docs/openscenario_carla_adapter_v1.md`。
- 对抗性测试代理 V1 契约已完成：采用场景间迭代模式，动作是 15 维归一化参数增量，观测是 34 维参数/条件/实测反馈向量；奖励分离风险增量、碰撞/事件奖励、无效候选、重复和运行失败惩罚，并固化 Schema/语义失败、严格验收失败、CARLA 服务异常、连续重复和最大步数终止条件。核心实现、配置、Schema、CLI 和文档分别位于 `core/adversarial_agent.py`、`configs/adversarial_agent_v1.json`、`schemas/adversarial_agent_v1.schema.json`、`tools/adversarial_agent_v1.py` 和 `docs/adversarial_test_agent_v1.md`。当前未安装训练依赖、未训练 SAC/PPO；已完成单步和多步 CARLA 执行链路验证，但不构成策略效果或 RL 有效性结论。
- 闭环编排 V1 已完成：`core/adversarial_loop.py` 和 `tools/run_adversarial_episode.py` 先执行严格基线，再执行固定动作候选，并将 metadata 解析为代理 EpisodeResult；`validate`、`mock`、`carla` 三种模式和服务器冒烟入口已建立。2026-08-19 服务器 CARLA `0.9.16` 单 episode 真实冒烟完成 `2/2` 次严格验收：基线风险 `26.536/medium`，候选风险 `28.939/medium`，实测增量 `+2.403`；两次均无碰撞、RGB 各 `100` 帧、路线双车在途率 `1.0`、最大路线偏差不超过 `1.000 m`、服务健康、客户端/服务端版本一致。证据已回收至 `F:\Carla\project-transfer\server-results\adversarial_loop_smoke_v1_20260819_123339`。该结果只证明执行链路和结果回填可用，不构成策略效果或 RL 有效性结论。
- 多步闭环真实冒烟已完成：配置 `configs/adversarial_loop_multistep_v1.json` 将 `max_agent_steps` 设为 `3`，服务器任务 `adversarial-loop-multistep-v1_20260820_132752` 执行基线加 3 个连续候选，共 `4/4` 次严格验收通过。风险序列为 `27.774 → 28.942 → 30.375 → 31.651`，基线到最终候选实测增量 `+3.877`；3 个 transition 的风险增量奖励项为 `0.01168`、`0.01433`、`0.01276`。四次均无碰撞、RGB 各 `100` 帧，路线和 CARLA 服务健康验收通过，客户端/服务端均为 `0.9.16`。证据已回收至 `F:\Carla\project-transfer\server-results\adversarial_loop_multistep_v1_20260820_132752`。本轮使用固定 15 维动作，结果只证明连续反馈、样本递进和风险回填链路可用，不代表 RL 策略已学习。
- 闭环异常路径编排测试已完成：`tests/test_adversarial_loop.py` 新增候选运行失败立即中止、可配置的无效候选跳过执行并在下一步恢复、连续重复候选达到阈值后截断三类用例；验证执行器调用序列、失败原因、奖励项、最终记录和终止状态。全仓库 `36/36` 单元测试、`compileall`、多步 `mock` CLI 和 `git diff --check` 均通过。该结果是纯 Python/mock 编排证据，不新增 CARLA 实机结论；默认配置仍保持无效候选立即终止。
- Gymnasium 接口评估 V1 已完成：确认 15 维归一化连续动作、34 维 `[0,1]` 观测、`reset/step` 返回契约以及 `terminated/truncated` 语义均可映射；可选外壳位于 `core/adversarial_gym_env.py`，依赖无关契约测试已通过。服务器项目环境已安装 Gymnasium `1.3.0`，任务 `check-adversarial-gymnasium_20260820_214522` 已通过标准 `check_env`；Stable-Baselines3 暂不安装，当前仍未启动训练。服务器全量测试另因既有 `matplotlib` 缺失失败，本机当前全量 `54/54` 通过。基线执行属于 `reset()` 外部副作用，固定单场景不能直接训练。评估文档见 `docs/adversarial_gymnasium_evaluation_v1.md`。
- Gymnasium 环境级 CARLA 冒烟已完成：服务器任务 `adversarial-gymnasium-smoke-v1_20260820_215156` 使用 Gymnasium `1.3.0` 执行一次 `reset()` 基线和两次 `step()` 候选，`3/3` 次严格验收通过。风险序列为 `27.764 → 28.899 → 30.353`，两次 Gymnasium transition 的 reward 为 `0.21135`、`0.21454`；三次均无碰撞、RGB 各 `100` 帧、路线双车在途率 `1.0`、CARLA 服务健康、客户端/服务端 `0.9.16` 一致，`terminated=false`、`truncated=false`。证据已回收至 `F:\Carla\project-transfer\server-results\20260820_215156_20260820_215411`。该结果证明 Gymnasium 外壳与真实 executor 的状态回填链路可用，不代表策略学习或 RL 训练有效。
- 分层场景采样与非学习离线基线 V1 已完成：`core/adversarial_sampling.py` 从场景库 `117` 条独立场景按 LHS/GMM/CVAE × low/medium/high/critical 的 12 个分层轮转，并在分层内平衡天气/危险标签和 Traffic Manager 种子；相同随机种子可复现样本与交通种子序列，采样元数据写入 Gymnasium `reset info.sampling`。首轮配置抽取 `24` 个独立场景，三个生成器各 `8` 条、四档各 `6` 条、三个交通种子各 `8` 次。fixed/random/LHS/rule-guided LHS 的原始首轮有效数分别为 `24/21/21/22`；独立有限重试流额外使用 `0/3/3/2` 次动作后全部补齐为 `24/24`，有效候选唯一率均为 `100%`，没有预算耗尽。最终离线结果位于 `F:\Carla\output-0.9.16\adversarial_baselines_v1\20260821_132033`，来源提交 `ab78246`，候选未运行 CARLA，不能据此评价风险收益或 RL 有效性。
- 四策略 CARLA 静态对照计划 V1 已完成：从一个完整 `12` 分层周期为每个场景准备 1 个共享基线和 fixed/random/LHS/rule-guided LHS 各 1 个候选，共 `12 + 48 = 60` 个计划运行；60 个场景记录、CARLA 配置和 Scene 04 `--validate-only` 全部通过，重试预算耗尽为 `0`。计划位于 `F:\Carla\output-0.9.16\adversarial_baseline_carla_plan_v1\20260821_132000`，来源提交 `ab78246`。该目录只保留静态计划证据；实机结果单独记录并继续按覆盖数量区分。
- 四策略 CARLA 首个 pair 实机冒烟已完成：服务器任务 `adversarial-baseline-carla-smoke-v1_20260821_134010` 执行共享基线加 fixed/random/LHS/rule-guided LHS 共 `5/5` 次严格验收；客户端/服务端均为 `0.9.16`，风险方法均为 `heuristic_v2`，RGB 各 `100` 帧，路线双车在途率均为 `1.0`，最大路线偏差不超过 `0.999 m`，服务健康。共享基线风险为 `94.081`，四候选风险为 `87.612/85.842/84.703/88.943`，相对增量均为负；但四候选的碰撞和事件奖励项全部达到上限，reward 仍为正，说明当前单 pair reward 不能直接解释策略优劣。轻量证据回收至 `F:\Carla\project-transfer\server-results\20260821_134011_20260821_134314`。
- 2026-08-18 已完成适配器生成 CARLA JSON 的单场景实机冒烟：CARLA 客户端/服务端均为 `0.9.16`，20 秒同步仿真完成，RGB/Depth/Semantic 各保存 `200` 帧，服务健康，事件和 `heuristic_v2` 风险结果均写入 `metadata.json`，无碰撞。该配置未启用路线锁定，因此只计为运行时冒烟，不计为路线严格验收；证据目录为 `F:\Carla\output-0.9.16\adapter_smoke\seed_v1_high_0165\20260818_222032`。
- 适配器冒烟期间曾发现本机默认 `python` 加载 CARLA `0.9.15`；该残留包已卸除，后续本机连接 CARLA 0.9.16 必须显式使用 `Carla666-0916` 环境。
- 运行环境规则已收口：服务器优先，SSH/RPC/健康检查失败才回退本机；本机固定使用 `D:\ANACONDA\envs\Carla666-0916`，运行前检查客户端/服务端均为 `0.9.16`。本机 Python 0.9.15 残留包已卸除。
- OpenSCENARIO XML 1.4 已登记为未来标准交换适配方向：后续单独建立 1.4 映射、Schema 校验和工具链运行证据，不替换当前 1.0 运行目标。
- 已完成 M01–M07 接口规格 V1：固化命令入口、核心函数、输入输出、运行可信条件、异常边界和验收矩阵；文档见 `docs/software_copyright_interface_spec_v1.md`。
- M07 只读可视化原型已完成：`tools/scenario_dashboard.py` 通过 Python 标准库读取场景库，提供本地页面、筛选、场景详情和只读 JSON 接口；数据契约回归与本地 HTTP 端点验证通过。
- 阶段三已完成收口并进入阶段四；软著演示截图暂缓，待正式准备申请软著时基于冻结版本统一采集，不作为阶段四启动条件。
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
- `core/scenario_library.py`：场景内容哈希去重、运行证据聚合和质量评估核心逻辑。
- `core/scenario_features.py`：15 维特征、条件编码和生成记录构建接口。
- `tools/generate_seed_dataset.py`：平衡风险分层与 Latin Hypercube 种子数据生成器。
- `tools/generate_with_model.py`：LHS、条件 GMM 和 CVAE 的统一生成入口。
- `tools/prepare_carla_validation.py`：生成模型样本抽样与 CARLA 配置编译。
- `tools/collect_carla_validation.py`：读取 CARLA 元数据并回填 `observed_risk`。
- `tools/build_scenario_library.py`：从严格验收实验构建场景库 JSONL、CSV 索引、汇总和哈希清单。
- `tools/query_scenario_library.py`：按生成器、风险、碰撞、证据粒度、质量等级和标签组合筛选场景库，支持表格、CSV 和 JSONL 输出。
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
- **服务器模型依赖**：NumPy 2.5.0、PyTorch `2.12.1+cu126`、TorchVision `0.27.1+cu126`、Pandas 3.0.3、SciPy 1.18.0、Scikit-learn 1.9.0 和 Joblib 1.5.3 已安装，`pip check` 无冲突；LHS、GMM、CVAE 各生成 `32/32` 条高风险候选并完成统一离线评估，风险代理复训结果为 MAE `5.515`、RMSE `10.138`。
- **服务器批次验收**：`rainy_night_variants` 的 5 个变体 × 3 个交通种子已完成 `15/15`，传感器完整率和 CARLA 服务健康率均为 `100%`，RGB/Depth/SemSeg 共记录 `9000` 帧且无碰撞。`batch_runner.py` 支持 `--output-root` 和 `--traffic-manager-port`；服务器批次使用 TM 端口 `8100`，避开现有服务占用的 `8000/8001`。
- **双端开发基线**：笔记本作为代码、配置、测试和 Git 提交端；服务器作为模型训练、候选生成、风险分析、CARLA 仿真和批量实验执行端。日常代码通过内网 `lab` 远端同步，形成实质且已验证的阶段进展时同步推送 GitHub `origin`；服务器运行工作区禁止直接修改代码。
- **历史结果保留**：CARLA 0.9.15 的配置、清单、聚合结果和 `834` 个结构化运行文件仍保留；0.9.15 程序、Python 环境、压缩包和约 `14.24 GiB` 原始 PNG/NPY 帧已删除，不再作为可直接运行的复现环境。
- **总体研究核心**：PyTorch、GAN/VAE/扩散模型、物理约束或 PyBullet、强化学习、OpenSCENARIO/CARLA 适配。
- **平台工程计划**：结构化场景数据库、Matplotlib/Plotly；Streamlit 可作为 Demo 展示层，但不是当前优先级。

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
- 场景库离线查询入口已建立：`tools/query_scenario_library.py` 支持按生成器、目标/实测风险、碰撞、证据粒度、CARLA 版本、质量等级、天气/危险标签、风险分数和多样性筛选，并输出表格、CSV 或 JSONL。
- 场景库质量分析基线已完成：`117` 个场景中实测 high/critical `72` 个、碰撞 `39` 个；目标档与实测档完全命中 `50/117`，目标序号与实测分数 Spearman `0.708`；GMM/LHS/CVAE 平均风险分为 `59.647/56.947/56.461`，碰撞场景率为 `38.5%/30.8%/30.8%`。这些是当前压力测试库的描述性统计，不构成生成器总体优劣结论。
- 质量分析同时确认：`36` 个条目为逐次证据/silver，`81` 个为聚合证据/bronze；全部条目场景级 CARLA 版本仍为 `unknown`，真实性均为 `not_assessed`，`30` 个条目被标记为低相对多样性。完整报告位于 `data/scenarios/scenario_library_v1/quality_analysis_v1/quality_analysis_report.md`。
- 场景库接口回归测试已完成：14 项标准库 `unittest` 全部通过，覆盖构建器与质量分析校验、117 条快照、5 组查询契约、CSV 文件导出、Dashboard 数据/HTTP 接口、严格验收负例和直接/继承证据分层；质量门配置位于 `configs/scenario_library_quality_gate_v1.json`。
- 首批场景的可执行性、证据完整性、重复性、危险性和库内参数多样性已评估，真实性因缺少同口径真实世界参考分布保持 `not_assessed`。历史三生成器对照未记录 CARLA 客户端/服务端版本字段，因此 `36` 个条目均为 `partial/silver`，不能将原批次严格验收通过误写成真实性或证据完整性满分。
- 多传感器低频冒烟已通过：RGB、Depth、Semantic 各写盘 `100` 帧，队列无失败，CARLA 服务健康；`heuristic_v2` 风险分为 `29.708/medium`。同为 `100` 帧时，RGB-only 传感器目录约 `21.3 MB`，RGB+Depth+SemSeg 约 `55.5 MB`，约为 `2.6` 倍。当前风险评分不读取图像像素，因此多传感器主要提供视觉证据、深度几何和未来感知模型输入，不直接提高现有启发式风险分析。
- 传感器策略已冻结为两档：大批量生成与风险代理训练使用 `RGB + Collision` 性能基线；主动补样、论文/软著展示和后续视觉风险模型使用 `RGB + Depth + Semantic + Collision` 低频证据配置，不把多传感器强行加入全部批次。
- 服务器生成的本轮结果目录使用 `20260816` 时间戳，与项目当前日期 2026-08-16 一致。
- 本轮唯一的初次路线失败在相同配置重跑后恢复为双车全程在途、路线偏差小于 `1.01 m`；当前按偶发运行状态处理，但后续批次仍保留路线严格验收，不能删除该质量门槛。
- 截至 2026 年 8 月 18 日，阶段二和阶段三已形成可复现工程基线：三生成器 108/108 严格实测对照、反馈短名单 81/81、双通道配对 54/54、碰撞边界主动补样 54/54、物理增强配对 54/54 均通过严格验收；风险反馈 V5、50 次重复 OOF、27 维物理增强代理、场景库质量门、软著模块映射、M01–M07 接口规格和 Dashboard 页面级回归均已完成。当前进入阶段四，不再继续无边界扩展阶段二实验。
- 实验室双 RTX 4090 服务器 `factory22-srv` 已完成 CARLA 0.9.16、Python 3.12.13、完整模型依赖、三生成器推理、风险代理复训和 15 次项目批次验证。后续完整模型训练和 CARLA 批量实验默认迁移到服务器 GPU 1，本地 RTX 4060 仅保留代码开发、快速静态校验和故障回退；GPU 0 继续保留给现有 vLLM 服务。
- GPU 1 还存在一个由 root 管理的 TensorRT 推理服务，当前显存占用约 `896 MiB`，项目不得终止或修改该服务。项目工作流使用 `/home/zhaozirong/software/output/carla-0.9.16/.workflow_gpu1.lock` 防止自身的模型任务与 CARLA 相互并发，但该锁无法约束外部服务；重型实验前必须先运行服务器状态检查并确认剩余显存。
- 长时间多传感器运行仍可能产生硬件压力，但帧完整性和服务健康检查已作为批次验收条件。
- 0.9.15 历史清单中的 `metadata_path`、`run_dir` 和 CMD 仍保留实验发生时的原始绝对路径，仅用于来源追溯；当前活动工具默认使用项目仓库场景运行器和 `F:\Carla\output-0.9.16`，不得直接执行旧脚本污染历史结果。
- CARLA 0.9.16 三种子迁移回归已严格验收 `3/3`：每次 RGB `100` 帧，传感器、服务健康和路线验收全部通过，双车同时在途率均为 `1.0`，最大路线偏差不超过 `1.000 m`，无碰撞，风险档均为 `medium`。同配置平均风险分由 0.9.15 的 `27.760` 变为 `27.491`（`-0.97%`）；0.9.16 风险分样本标准差为 `0.587`、极差为 `1.137`，相对波动增大但未影响工程验收。当前样本仅一个场景、三个种子，不作统计显著性结论。
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
1. 基于首个 pair 补充相对共享基线的 reward 诊断口径，明确碰撞已发生时的奖励语义，并避免把连续接触帧数直接解释为独立碰撞次数。
2. 复用服务器计划和可恢复执行器，跳过已完成的 5 次，执行剩余 11 个 pair、55 次 CARLA 对照；按 12 个生成器×目标风险分层汇总真实风险、碰撞发生、严格验收和运行成本。
3. 单独处理服务器既有 `matplotlib` 依赖缺口；完成真实非学习基线后，再评估安装 Stable-Baselines3，当前仍不启动训练。
4. 继续维护场景库质量门和 Dashboard 回归；软著演示截图后置到正式申请准备阶段，真实性研究继续等待同口径真实世界参数分布。
