# Web 管理系统 MVP V1

## 定位

Web MVP 是阶段五的首个交付增量。当前版本把现有 M07 只读 Dashboard 统一成一个可访问的本地 Web 入口，并已接入生成、校验、任务编排和风险分析工作流。当前版本不启动 CARLA、不写入场景库、不占用 GPU。

## 技术选择

- Python 标准库 `http.server`，避免首期新增依赖和部署复杂度。
- 复用 `tools/scenario_dashboard.py` 的 `load_dashboard_data`、`/api/summary`、`/api/scenarios` 和 `/api/scenarios/{library_id}` 契约。
- 页面使用原生 HTML/CSS/JavaScript；场景库继续以 JSONL/CSV/JSON 快照为数据源。
- 后续出现写入、任务队列、权限和并发需求时，再评估 FastAPI、SQLite 和独立前端工程。

## 已提供路由

| 路由 | 状态 | 说明 |
|---|---|---|
| `/` | 已实现 | Dashboard 首页，保留现有筛选和详情交互 |
| `/dashboard` | 已实现 | Dashboard 首页别名 |
| `/scenarios` | 已实现 | 场景库列表入口 |
| `/scenarios/{library_id}` | 已实现 | 独立场景详情页 |
| `/api/summary` | 已实现 | 场景库汇总和质量摘要 |
| `/api/scenarios` | 已实现 | 场景索引列表 |
| `/api/scenarios/{library_id}` | 已实现 | 完整场景条目 |
| `/healthz` | 已实现 | 服务健康与数据计数 |
| `/generation` | 已产品化首期 | 提交 CPU 生成任务、轮询状态并展示 JSONL 产物 |
| `/validation` | 已产品化首期 | 支持 JSON/JSONL 校验、物理约束、可选 CARLA 配置编译 |
| `/tasks` | 已实现 | 查看任务历史、取消任务、确认 CARLA 外部任务 |
| `/risk` | 已产品化首期 | 读取运行目录/遥测并展示 `observed_risk` 与诊断 |

## 验收口径

Web MVP 必须通过 `tests/test_web_app.py` 和既有 Dashboard 回归，且接口计数保持 `117` 个独立场景、`351` 条来源批次严格验收证据。页面展示的 `observed_risk` 来自已有运行证据；`target_risk_level` 不得在页面或材料中写成实测风险。

当前验收已完成桌面截图和 Playwright `390×844` 移动视口检查；移动视口下页面文档宽度等于 `390`，导航分为两行，117 条场景数据加载完整，无横向页面溢出。产品化流程回归覆盖页面表单、任务轮询、JSONL 校验和结构化错误；完整命令见 `docs/stage5_web_product_flow_v2.md`。

## 启动

```powershell
tools\web_app.cmd
```

默认地址为 `http://127.0.0.1:8765/`。仅校验数据加载时运行：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\web_app.py --validate-only
```
