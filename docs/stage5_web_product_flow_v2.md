# 阶段五 Web 产品化流程 V2

## 定位

本版本把原型占位页升级为本机优先的工作流：场景生成、场景校验、风险分析和 CARLA 单场景运行。离线处理统一由 `TaskManager` 的 CPU worker 执行，CARLA 运行由本机 worker 调用 Scene 04 客户端，任务状态和结果持久化到 `F:\Carla\output-0.9.16\web_tasks`（可用 `CARLA_WEB_TASK_DIR` 覆盖）。CARLA 服务仍需用户提前启动在本机 `localhost:2000`，Web 不隐式启动 CARLA 服务、在线训练或 GPU 调度。连续流程已将生成、校验、本机仿真和风险分析串联。

## 三条用户流程

| 页面 | 输入 | 后端任务 | 结果 |
|---|---|---|---|
| `/generation` | 生成器、目标风险、天气标签、数量、种子、可选模型产物 | `generation` | JSONL 场景记录、汇总、接受数量和耗时 |
| `/validation` | JSON/JSONL 路径或单条 JSON、基础 CARLA 配置、是否编译 | `validation` | Schema/语义校验、参数级物理约束、逐条错误/警告、可选 `.carla.json` |
| `/risk` | 运行目录，或 telemetry/metadata/config 路径 | `risk_analysis` | `observed_risk`、风险分解、诊断、碰撞计数和证据来源 |

页面统一行为：提交后立即显示任务 ID，轮询 `GET /api/tasks/{task_id}`，终态显示通俗摘要和结构化 JSON；失败显示错误信息；任务历史可在 `/tasks` 查看。CARLA 服务需先由用户在本机启动，Web 只调用客户端，不隐式启动服务、在线训练或 GPU 调度。

## 连续流程第一批

当前可直接完成：

```text
选择生成参数（单场景数量设为 1）
→ 查看生成摘要
→ 点击“校验并准备 CARLA”
→ 查看逐条 Schema/语义/物理约束结果
→ 点击“启动本机 CARLA 实测”
→ 查看风险分析任务、运行状态图、传感器回放和相对车距示意
→ 查看任务时间线、输入快照、产物路径和 SHA-256
```

每个新任务包含 `workflow_id`、`workflow_step`、`parent_task_id`、`evidence_level` 和 `artifacts`。从生成结果创建的校验任务继承原 `workflow_id`，并把生成任务登记为父任务。产物条目统一记录类型、用途、绝对路径、字节数、SHA-256 和来源任务；旧任务文件可兼容加载，但不会补造历史产物哈希。

`/tasks/{task_id}` 是正式任务详情页，按任务类型展示结果摘要或逐条校验表，同时保留完整 JSON 折叠视图。`/tasks` 列表只显示可读摘要，不再用压缩后的整块 JSON 作为主要结果展示。

## P0 验收结果

- 页面访问：`/dashboard`、`/scenarios`、`/generation`、`/validation`、`/risk`、`/tasks` 均已完成真实 HTTP `200` 冒烟。
- 任务终态：生成、校验、风险分析真实提交均进入 `completed`；失败任务保留结构化 `error`；运行中任务取消后不会被 worker 覆盖为 `completed/failed`。
- CARLA 边界：Web 页面创建 CARLA 任务时默认使用 `execution_target=local`，任务经过 `queued/running` 后自动分析本机结果；本机没有 CARLA 时可显式使用 `execution_target=remote`，保留 `awaiting_confirmation → confirmed_manual` 的远端兼容路径。
- 移动端：任务表容器启用横向滚动，避免窄视口下任务 ID、结果和操作列溢出。
- 浏览器执行：任务页内联脚本已通过 Edge 无界面浏览器实际加载；已有任务能从 `/api/tasks` 渲染到表格，提交和“刷新状态”均使用同一加载函数。
- 任务表展示：结果列使用固定布局和单行省略号，完整 JSON 保留在单元格悬浮提示中；任务 ID、时间和操作列不会被长结果挤压成竖排。
- 验证命令：`D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest discover -s tests -p "test_*.py" -v`；测试数量以当前冻结提交的实际输出为准，另行记录可选依赖跳过项；`compileall` 和 `git diff --check` 通过。

## API 契约

- `POST /api/tasks`：提交任务，返回 `202` 和任务快照。
- `GET /api/tasks/{task_id}`：读取状态、输入和结果摘要。
- `GET /api/tasks/{task_id}/result`：仅在 `completed` 时返回结果，否则 `409`。
- `GET /api/tasks`：按创建时间倒序列出任务。
- `GET /api/workflows/{workflow_id}`：返回工作流阶段、任务时间线和聚合产物。
- `POST /api/tasks/{task_id}/validate`：从已完成的生成任务创建同一工作流下的校验任务。
- `POST /api/tasks/{task_id}/compile`：对已通过且只有一条记录的历史校验任务补编译 CARLA 配置。
- `POST /api/tasks/{task_id}/carla`：从已完成且带编译配置的校验任务创建本机 CARLA 任务。
- `POST /api/tasks/{task_id}/cancel`：取消尚未结束的任务。
- `POST /api/tasks/{task_id}/confirm`：仅 CARLA 外部任务使用；确认只登记 `confirmed_manual`，不启动 CARLA。
- `POST /api/tasks/{task_id}/run-local`：把等待确认的 CARLA 任务切换为本机运行；Web 只调用本机客户端。
- `GET /api/tasks/{task_id}/export`：下载包含任务快照、配置、日志、风险图、传感器和原始 JSON/CSV 的完整 ZIP 数据包。

校验任务支持单条 JSON 和 JSONL。JSONL 结果包含 `record_count`、`items[line,result]` 和聚合的物理约束报告；从单场景生成任务继续校验时默认 `compile=true`，单条记录通过全部质量门时输出编译配置；历史单条校验可通过 `/compile` 补齐该产物。批量 JSONL 仍只做校验，不直接生成单个 CARLA 配置。

## 证据边界

- 生成、校验和风险分析是离线 CPU 证据；页面结果不会自动变成 CARLA 实测。
- `observed_risk` 只有在输入遥测来自真实 CARLA 运行时才具有实测含义；`target_risk_level` 始终是设计条件。
- CARLA 本机连接失败会进入 `failed` 并保留标准输出/错误日志，不伪造成功结果；远端服务器入口仍作为可选兼容模式。

## 研究能力入口

- `tools/train_carla_rl.py`：在线 RL 预检/训练入口。默认 `--dry-run`，只有 `--allow-online-carla` 才可能启动环境；PPO rollout 长度受 `--steps` 显式预算约束，不会因为算法默认值偷偷扩展 CARLA episode；缺少 Gymnasium 或 SB3 时保持阻塞状态。
- `tools/run_scenario_runner.py`：XOSC 解析、ScenarioRunner 路径预检和显式 `--execute` 入口。默认只生成 dry-run manifest。
- `core/differentiable_closed_loop.py`：Torch 可微运动学闭环和损失梯度；服务器已完成 P4 gap 几何回放与统一 manifest，contact probe 仍只代表离散盒体接触，不得称为可微 PyBullet 训练，边界见 `docs/differentiable_closed_loop_v1.md` 和 `docs/p4_server_validation_v1.md`。

这些入口建立了可审计的接口，不代表 CARLA 在线 RL、ScenarioRunner 完整直执行或 PyBullet 可微物理闭环已经完成。真实结论仍需服务器 CARLA 0.9.16 运行和独立证据。

## 验证

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest tests.test_web_app tests.test_web_task_orchestration tests.test_runtime_adapters -v
```

当前覆盖 Web 页面表单、任务轮询契约、JSONL 校验、生成到校验的工作流继承、任务恢复、产物哈希、可微梯度、PyBullet 可选边界和 ScenarioRunner dry-run。浏览器已实测一键校验、任务详情和窄屏布局；历史截图仍只作为界面底稿，正式软著截图需在最终冻结提交上重新采集。

## 本机运行、结果可视化与远端回链

Web 现在支持一条可审计的“设计→校验→本机执行→风险分析→结果展示/导出”路径，远端回链作为兼容分支：

1. 在生成页提交场景参数，生成任务在本机 CPU worker 执行；
2. 在任务详情页创建校验任务，校验通过且生成 CARLA 配置后，点击“在本机运行 CARLA”；本机客户端结束后自动发现运行目录并创建风险分析任务；
3. 风险任务会生成 `risk_result.json`、`run_visualization.svg` 和可选的 `sensor_preview.png`，并为每个产物记录 SHA-256。页面用运行是否完成、CARLA 是否连接、传感器是否完整、路线是否正常和风险等级解释结果；
4. 点击“下载完整数据包”可导出 ZIP，普通用户查看摘要，专业人员可从原始 JSON/CSV/日志复核；
5. 若选择远端模式，使用现有 `tools\server_run.cmd` 或专用服务器入口提交任务，完成后用 `tools\server_fetch_results.cmd` 回收目录，再在 CARLA 任务详情页导入。目录必须包含 `metadata.json` 和 `telemetry.csv`，导入后同样自动创建风险分析任务。

新增接口：

- `POST /api/tasks/{validation_task_id}/carla`：从已完成且有编译配置的校验任务登记 CARLA 外部任务；
- `POST /api/tasks/{carla_task_id}/attach-result`：导入本机结果目录，自动串联风险分析；
- `POST /api/tasks/{carla_task_id}/run-local`：切换到本机 CARLA 运行并自动回链结果；
- `GET /api/tasks/{task_id}/artifact/{file_name}`：只允许访问任务已登记的产物，支持 SVG/PNG 预览。
- `GET /api/tasks/{task_id}/export`：下载完整诊断数据包。

可视化口径：运行状态图使用遥测的 `elapsed_seconds` 作为横轴，绘制主车/前车速度、TTC、前车净间距和行人距离；它不是真实地图轨迹。若运行目录保留原始传感器帧，结果页可按需回放 RGB/Depth/SemSeg，历史帧与遥测按帧序近似对齐；俯视图仅用估算净间距表示前后车相对位置。这些展示不替代 `metadata.json`、严格验收或 `heuristic_v2` 原始结果。远端结果导入后，证据等级从 `external_unverified` 提升为 `external_verified` 的条件是 metadata 中 CARLA 服务健康状态为 `healthy`；Web 不根据页面图片自行推断仿真成功。
