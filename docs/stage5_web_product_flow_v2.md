# 阶段五 Web 产品化流程 V2

## 定位

本版本把原型占位页升级为三个可操作的本地工作流：场景生成、场景校验、风险分析。页面只负责提交参数和展示任务状态；实际处理统一由 `TaskManager` 的 CPU worker 执行，任务状态和结果持久化到 `F:\Carla\output-0.9.16\web_tasks`（可用 `CARLA_WEB_TASK_DIR` 覆盖）。

## 三条用户流程

| 页面 | 输入 | 后端任务 | 结果 |
|---|---|---|---|
| `/generation` | 生成器、目标风险、天气标签、数量、种子、可选模型产物 | `generation` | JSONL 场景记录、汇总、接受数量和耗时 |
| `/validation` | JSON/JSONL 路径或单条 JSON、基础 CARLA 配置、是否编译 | `validation` | Schema/语义校验、参数级物理约束、逐条错误/警告、可选 `.carla.json` |
| `/risk` | 运行目录，或 telemetry/metadata/config 路径 | `risk_analysis` | `observed_risk`、风险分解、诊断、碰撞计数和证据来源 |

页面统一行为：提交后立即显示任务 ID，轮询 `GET /api/tasks/{task_id}`，终态显示结构化 JSON；失败显示错误信息；任务历史可在 `/tasks` 查看。页面没有隐式 CARLA 启动、在线训练或 GPU 调度。

## P0 验收结果

- 页面访问：`/dashboard`、`/scenarios`、`/generation`、`/validation`、`/risk`、`/tasks` 均已完成真实 HTTP `200` 冒烟。
- 任务终态：生成、校验、风险分析真实提交均进入 `completed`；失败任务保留结构化 `error`；运行中任务取消后不会被 worker 覆盖为 `completed/failed`。
- CARLA 边界：CARLA 任务提交后为 `awaiting_confirmation`；确认只登记 `confirmed_manual`，取消为 `cancelled`，两者均明确 `execution_started=false`、`carla_connected=false`，Web 进程不启动 CARLA。
- 移动端：任务表容器启用横向滚动，避免窄视口下任务 ID、结果和操作列溢出。
- 浏览器执行：任务页内联脚本已通过 Edge 无界面浏览器实际加载；已有任务能从 `/api/tasks` 渲染到表格，提交和“刷新状态”均使用同一加载函数。
- 验证命令：`D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest discover -s tests -p "test_*.py" -v`，结果 `126 passed / 1 skipped`；`compileall` 和 `git diff --check` 通过。

## API 契约

- `POST /api/tasks`：提交任务，返回 `202` 和任务快照。
- `GET /api/tasks/{task_id}`：读取状态、输入和结果摘要。
- `GET /api/tasks/{task_id}/result`：仅在 `completed` 时返回结果，否则 `409`。
- `GET /api/tasks`：按创建时间倒序列出任务。
- `POST /api/tasks/{task_id}/cancel`：取消尚未结束的任务。
- `POST /api/tasks/{task_id}/confirm`：仅 CARLA 外部任务使用；确认只登记 `confirmed_manual`，不启动 CARLA。

校验任务支持单条 JSON 和 JSONL。JSONL 结果包含 `record_count`、`items[line,result]` 和聚合的物理约束报告；单条记录在 `compile=true` 且通过全部质量门时输出编译配置。

## 证据边界

- 生成、校验和风险分析是离线 CPU 证据；页面结果不会自动变成 CARLA 实测。
- `observed_risk` 只有在输入遥测来自真实 CARLA 运行时才具有实测含义；`target_risk_level` 始终是设计条件。
- CARLA 任务保留显式确认和外部服务器入口，避免 Web 服务卡死或与 GPU/CARLA 资源并发。

## 研究能力入口

- `tools/train_carla_rl.py`：在线 RL 预检/训练入口。默认 `--dry-run`，只有 `--allow-online-carla` 才可能启动环境；PPO rollout 长度受 `--steps` 显式预算约束，不会因为算法默认值偷偷扩展 CARLA episode；缺少 Gymnasium 或 SB3 时保持阻塞状态。
- `tools/run_scenario_runner.py`：XOSC 解析、ScenarioRunner 路径预检和显式 `--execute` 入口。默认只生成 dry-run manifest。
- `core/differentiable_closed_loop.py`：Torch 可微运动学闭环和损失梯度；服务器已完成 PyBullet DIRECT 离散校验，但仍不能称为可微 PyBullet 训练，边界见 `docs/differentiable_closed_loop_v1.md`。

这些入口建立了可审计的接口，不代表 CARLA 在线 RL、ScenarioRunner 完整直执行或 PyBullet 可微物理闭环已经完成。真实结论仍需服务器 CARLA 0.9.16 运行和独立证据。

## 验证

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest tests.test_web_app tests.test_web_task_orchestration tests.test_runtime_adapters -v
```

当前覆盖 Web 页面表单、任务轮询契约、JSONL 校验、可微梯度、PyBullet 可选边界和 ScenarioRunner dry-run。结题报告和最终软著截图继续后置到核心证据收口后。
