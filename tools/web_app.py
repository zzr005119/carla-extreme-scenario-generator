"""阶段五 Web 统一入口和本地任务编排 API。

场景库仍是只读数据源；离线任务写入独立任务目录。CARLA 任务默认调用
本机客户端，服务本身仍需用户显式启动；远端执行和 GPU 训练不会被隐式触发。
"""

import argparse
import html
import json
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.scenario_dashboard import (  # noqa: E402
    DEFAULT_LIBRARY_DIR,
    DashboardHandler,
    HTML_PAGE,
    load_dashboard_data,
)
from core.web_task_orchestrator import (  # noqa: E402
    DEFAULT_TASK_DIR,
    TaskError,
    TaskManager,
)
from core.web_visualization import build_replay_manifest, resolve_replay_frame  # noqa: E402


NAVIGATION = """
<nav class="app-nav" aria-label="主导航">
  <a href="/dashboard">总览</a>
  <a href="/scenarios">场景库</a>
  <a href="/generation">生成</a>
  <a href="/validation">校验</a>
  <a href="/tasks">运行任务</a>
  <a href="/risk">风险分析</a>
</nav>
"""

BASE_STYLE = """
<style>
  :root { color-scheme: light; --ink: #172033; --muted: #61708a; --line: #dbe3ef; --canvas: #f4f7fb; --primary: #2563eb; --accent: #0f766e; --warn: #b45309; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--canvas); color: var(--ink); font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
  header { background: #132243; color: #fff; padding: 24px clamp(18px, 5vw, 72px); }
  header h1 { margin: 0 0 6px; font-size: clamp(24px, 4vw, 36px); }
  header p { margin: 0; color: #dbeafe; }
  .runtime-banner { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .runtime-banner span { display: inline-flex; align-items: center; min-height: 28px; padding: 4px 9px; border: 1px solid #6d8fc7; border-radius: 6px; color: #eff6ff; font-size: 12px; }
  .runtime-banner .primary { background: #0f766e; border-color: #5eead4; }
  .app-nav { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .app-nav a { color: #dbeafe; border: 1px solid #6d8fc7; border-radius: 7px; padding: 7px 11px; text-decoration: none; font-size: 13px; }
  .app-nav a:hover, .app-nav a:focus { background: #2563eb; color: #fff; }
  main { max-width: 1100px; margin: 0 auto; padding: 26px clamp(16px, 5vw, 56px) 48px; }
  .panel { min-width: 0; background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 20px; }
  .panel h2 { margin: 0 0 12px; font-size: 20px; }
  .muted { color: var(--muted); line-height: 1.7; }
  .facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
  .fact { border: 1px solid var(--line); border-radius: 7px; padding: 14px; background: #f8fafc; }
  .fact-label { color: var(--muted); font-size: 12px; }
  .fact-value { margin-top: 5px; font-size: 24px; font-weight: 700; }
  .links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
  .links a { color: var(--primary); border: 1px solid var(--line); border-radius: 7px; padding: 12px; text-decoration: none; background: #fff; }
  .links a:hover { border-color: var(--primary); background: #eff6ff; }
  form { display: grid; gap: 8px; }
  label { color: var(--muted); font-size: 13px; font-weight: 600; }
  input, select, textarea, button { font: inherit; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; min-height: 38px; }
  input, select, textarea { width: 100%; background: #fff; color: var(--ink); }
  textarea { resize: vertical; min-height: 120px; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
  button { width: fit-content; cursor: pointer; background: var(--primary); color: #fff; border-color: var(--primary); font-weight: 700; }
  button.secondary { background: #fff; color: var(--primary); }
  .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .field { display: grid; gap: 5px; min-width: 0; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--ink); font-size: 13px; }
  .check input { width: auto; min-height: auto; }
  .visualization { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
  .run-chart { display: block; width: 100%; max-width: 1020px; height: auto; border: 1px solid var(--line); background: #f8fafc; }
  .sensor-preview { display: block; width: min(100%, 480px); max-height: 360px; object-fit: contain; border: 1px solid var(--line); background: #0f172a; }
  .result { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 16px; }
  .result pre { margin: 0; padding: 12px; max-height: 420px; overflow: auto; background: #0f172a; color: #e2e8f0; border-radius: 6px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .panel > pre { max-width: 100%; margin: 0; padding: 12px; overflow: auto; background: #0f172a; color: #e2e8f0; border-radius: 6px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .result details { margin-top: 14px; }
  .result summary { cursor: pointer; color: var(--primary); }
  .status-line { min-height: 24px; color: var(--muted); }
  .status-line.error { color: #b91c1c; }
  .status-line.success { color: #15803d; }
  .workflow-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
  .workflow-actions a, .button-link { display: inline-flex; align-items: center; min-height: 38px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; color: var(--primary); background: #fff; text-decoration: none; font-weight: 700; }
  .badge { display: inline-block; padding: 3px 7px; border-radius: 6px; background: #eef2ff; color: #3730a3; font-size: 12px; font-weight: 700; }
  .badge.success { background: #dcfce7; color: #166534; }
  .badge.error { background: #fee2e2; color: #991b1b; }
  .badge.warn { background: #fef3c7; color: #92400e; }
  .plain-summary { padding: 12px 14px; border-left: 4px solid var(--accent); background: #ecfdf5; color: #14532d; line-height: 1.7; }
  .export-link { background: #0f766e !important; border-color: #0f766e !important; color: #fff !important; }
  .detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }
  .detail-item { min-width: 0; padding: 12px; border: 1px solid var(--line); border-radius: 7px; background: #f8fafc; }
  .detail-item strong, .detail-item code { display: block; margin-top: 5px; overflow-wrap: anywhere; }
  .stack { display: grid; min-width: 0; gap: 18px; }
  .issue-list { margin: 0; padding-left: 18px; }
  .issue-list li { margin: 3px 0; }
  .artifact-path, .hash { max-width: 420px; overflow-wrap: anywhere; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; }
  .table-wrap { overflow-x: auto; width: 100%; max-width: 100%; }
  .task-table { table-layout: fixed; min-width: 780px; }
  .task-table th:nth-child(1), .task-table td:nth-child(1) { width: 22%; }
  .task-table th:nth-child(2), .task-table td:nth-child(2) { width: 12%; }
  .task-table th:nth-child(3), .task-table td:nth-child(3) { width: 12%; }
  .task-table th:nth-child(4), .task-table td:nth-child(4) { width: 19%; }
  .task-table th:nth-child(5), .task-table td:nth-child(5) { width: 19%; }
  .task-table th:nth-child(6), .task-table td:nth-child(6) { width: 16%; }
  .task-table .task-id, .task-table .task-created, .task-table .task-result { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .task-table .task-result { cursor: help; }
  th, td { padding: 9px 7px; border-bottom: 1px solid #edf1f7; text-align: left; vertical-align: top; }
  th { color: var(--muted); width: 30%; font-weight: 500; }
  code { overflow-wrap: anywhere; }
  @media (max-width: 700px) { .facts, .links, .form-grid, .detail-grid { grid-template-columns: 1fr; } .workflow-actions { align-items: stretch; flex-direction: column; } .workflow-actions button, .workflow-actions a { width: 100%; justify-content: center; } }
</style>
"""


def _page(title, content, *, subtitle="阶段五 Web 管理系统"):
    return (
        "<!doctype html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>{BASE_STYLE}</head><body>"
        f"<header><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p><div class=\"runtime-banner\"><span class=\"primary\">本机优先运行</span><span>不依赖远端服务器</span><span>CARLA 运行前请启动本机 0.9.16（端口 2000）</span></div>{NAVIGATION}</header>"
        f"<main>{content}</main></body></html>"
    )


def _detail_page(record):
    risk = record.get("observed_risk", {})
    evidence = record.get("execution_evidence", {})
    quality = record.get("quality", {})
    labels = record.get("labels", {})
    rows = [
        ("样本 ID", record.get("canonical_sample_id")),
        ("库 ID", record.get("library_id")),
        ("生成器", ", ".join(labels.get("generators", []))),
        ("实测风险", f"{risk.get('modal_level', '—')} / {risk.get('score_mean', '—')}"),
        ("碰撞", "是" if risk.get("collision_observed") else "否"),
        ("质量层级", quality.get("tier", "—")),
        ("严格验收", f"{evidence.get('accepted_run_count', '—')} / {evidence.get('expected_run_count', '—')}"),
        ("证据粒度", evidence.get("evidence_granularity", "—")),
    ]
    table = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in rows
    )
    parameters = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td><code>{html.escape(json.dumps(value, ensure_ascii=False))}</code></td></tr>"
        for key, value in (record.get("parameters") or {}).items()
    )
    content = (
        '<section class="panel"><h2>场景详情</h2>'
        '<p class="muted">此页面展示场景库快照中的参数、实测风险和运行证据；数据为只读。</p>'
        f"<table>{table}</table><h2 style=\"margin-top:24px\">场景参数</h2><table>{parameters}</table>"
        f"<p style=\"margin-top:20px\"><a href=\"/scenarios\">返回场景库</a></p></section>"
    )
    return _page("场景详情", content, subtitle="场景库 V1 · 只读证据视图")


def _json_block(payload):
    return html.escape(json.dumps(payload, ensure_ascii=False, indent=2))


KIND_LABELS = {
    "generation": "场景生成",
    "validation": "场景校验",
    "risk_analysis": "风险分析",
    "carla": "CARLA 仿真",
}
STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "awaiting_confirmation": "等待选择运行方式",
    "confirmed_manual": "等待远端结果",
}
EVIDENCE_LABELS = {
    "offline": "离线可复核",
    "external_unverified": "仿真结果待核验",
    "external_verified": "已连接仿真证据",
}


def _kind_label(kind):
    return KIND_LABELS.get(str(kind), str(kind or "—"))


def _status_label(status):
    return STATUS_LABELS.get(str(status), str(status or "—"))


def _evidence_label(level):
    return EVIDENCE_LABELS.get(str(level), str(level or "—"))


def _task_status_badge(status):
    tone = " success" if status in {"completed", "通过"} else " error" if status in {"failed", "cancelled", "未通过"} else " warn" if status in {"awaiting_confirmation", "confirmed_manual"} else ""
    return f'<span class="badge{tone}">{html.escape(_status_label(status) if status not in {"通过", "未通过"} else str(status))}</span>'


def _issue_text(issue):
    if isinstance(issue, dict):
        return str(issue.get("message") or issue.get("code") or json.dumps(issue, ensure_ascii=False))
    return str(issue)


def _validation_result_table(result):
    physical_by_line = {
        item.get("line_number"): item
        for item in (result.get("physical_constraints") or {}).get("results", [])
    }
    rows = []
    for item in result.get("items", []):
        line = item.get("line")
        schema = item.get("result") or {}
        physical = physical_by_line.get(line, {})
        errors = list(schema.get("errors") or []) + list(physical.get("errors") or [])
        warnings = list(schema.get("warnings") or []) + list(physical.get("warnings") or [])
        valid = bool(schema.get("valid") and physical.get("valid"))
        issue_items = errors or warnings
        issues = "<ul class=\"issue-list\">" + "".join(
            f"<li>{html.escape(_issue_text(issue))}</li>" for issue in issue_items
        ) + "</ul>" if issue_items else "无"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(line))}</td>"
            f"<td><code>{html.escape(str(item.get('sample_id') or '未命名'))}</code></td>"
            f"<td>{_task_status_badge('通过' if valid else '未通过')}</td>"
            f"<td>{len(errors)}</td><td>{len(warnings)}</td><td>{issues}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="muted">任务尚未产生逐条校验结果。</p>'
    return (
        '<h3>逐条校验结果</h3><div class="table-wrap"><table class="validation-table"><thead><tr><th>行</th><th>场景 ID</th><th>结果</th>'
        '<th>错误</th><th>警告</th><th>说明</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _artifact_table(artifacts):
    if not artifacts:
        return '<p class="muted">当前任务没有登记产物。</p>'
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('type', '—')))}</td>"
        f"<td>{html.escape(str(item.get('role', '—')))}</td>"
        f"<td>{html.escape(str(item.get('size_bytes', '—')))}</td>"
        f"<td class=\"artifact-path\">{html.escape(str(item.get('path', '—')))}</td>"
        f"<td class=\"hash\">{html.escape(str(item.get('sha256', '—')))}</td>"
        "</tr>"
        for item in artifacts
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>类型</th><th>用途</th><th>字节</th>'
        f'<th>路径</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


def _replay_panel(task_id):
    return f'''
    <div class="visualization replay-section" id="replay-player" data-task-id="{html.escape(task_id)}">
      <div class="replay-heading"><div><h3>传感器画面回放</h3><p class="muted">画面与遥测按帧序近似对齐；原始帧不含逐帧时间戳。</p></div><span id="replay-status" role="status">正在读取帧</span></div>
      <div class="replay-grid">
        <div class="replay-media"><img id="replay-image" alt="CARLA 传感器画面" /><div class="replay-toolbar"><button type="button" id="replay-toggle" disabled>播放</button><div class="replay-option"><label for="replay-channel">画面</label><select id="replay-channel" disabled></select></div><div class="replay-option"><label for="replay-speed">速度</label><select id="replay-speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></div></div><div class="replay-timeline"><input type="range" id="replay-scrubber" min="0" max="0" value="0" disabled aria-label="拖动回放进度" /><div id="replay-event-track" class="replay-event-track" aria-label="运行事件"></div><div class="replay-time"><span id="replay-time">0.0 s</span><span id="replay-duration">0.0 s</span></div></div></div>
        <div class="relative-view"><h3>相对位置示意</h3><p class="muted">按 0–50 m 净间距映射，超出封顶；不代表真实地图坐标。</p><div id="relative-road" class="relative-road" role="img" aria-label="主车和前车的相对距离示意"><div class="road-lane"><div id="lead-car" class="schematic-car lead-car">前车</div><div class="schematic-car ego-car">主车</div></div></div><div class="replay-readouts"><div><span>主车速度</span><strong id="replay-speed-value">—</strong></div><div><span>前车净间距</span><strong id="replay-gap">—</strong></div><div><span title="预计碰撞时间：净间距除以接近速度；没有接近时不计算">TTC（预计碰撞时间）</span><strong id="replay-ttc">—</strong></div><div><span>主车刹车</span><strong id="replay-brake">—</strong></div></div><p id="replay-event" class="replay-event">—</p></div>
      </div>
    </div><script src="/static/replay.js" defer></script>
    '''
def _task_detail_page(task, workflow):
    task_id = str(task["task_id"])
    result = task.get("result") or {}
    cards = [
        ("状态", _task_status_badge(task.get("status"))),
        ("类型", html.escape(_kind_label(task.get("kind")))),
        ("运行方式", html.escape({"local_carla": "本机 CARLA", "manual_external": "远端手动导入", "offline_cpu": "本机 CPU"}.get(task.get("execution_mode"), str(task.get("execution_mode", "—"))))),
        ("证据等级", html.escape(_evidence_label(task.get("evidence_level", "—")))),
        ("工作流", f'<code>{html.escape(str(task.get("workflow_id", "—")))}</code>'),
    ]
    overview = "".join(
        f'<div class="detail-item"><span class="fact-label">{label}</span><strong>{value}</strong></div>'
        for label, value in cards
    )
    actions = [f'<a class="button-link" href="/tasks">返回任务列表</a>']
    next_step_section = ""
    if task.get("status") not in {"queued", "running"}:
        actions.insert(0, f'<a class="button-link export-link" href="/api/tasks/{html.escape(task_id)}/export">下载完整数据包</a>')
    if task.get("kind") == "generation" and task.get("status") == "completed":
        accepted_count = ((result.get("summary") or {}).get("accepted_count"))
        compile_ready = accepted_count == 1
        action_label = "校验并准备 CARLA" if compile_ready else "校验本批次"
        compile_flag = "true" if compile_ready else "false"
        actions.insert(0, f'<button class="primary-action" id="validate-generated" data-compile="{compile_flag}" data-task="{html.escape(task_id)}">{action_label}</button>')
        next_step_section = (
            '<section class="next-step-panel"><span class="section-kicker">NEXT STEP</span>'
            '<h2>下一步：校验配置并进入实机运行</h2>'
            f'<p>{"当前只有 1 个候选，点击上方按钮后会自动编译 CARLA 配置；校验通过后，下一页会出现“启动本机 CARLA 实测”。" if compile_ready else "当前批次包含多个候选，先完成批量校验；要进入 CARLA 实测，请重新生成数量为 1 的单场景候选。"}</p></section>'
        )
    if task.get("kind") == "validation" and task.get("status") == "completed" and result.get("compiled_config_path"):
        actions.insert(0, f'<button class="primary-action" id="register-carla" data-task="{html.escape(task_id)}">启动本机 CARLA 实测</button>')
        next_step_section = (
            '<section class="next-step-panel"><span class="section-kicker">NEXT STEP</span>'
            '<h2>配置已准备好，可以开始实机测试</h2>'
            '<p>请先确认本机 CARLA 0.9.16 已启动并监听端口 2000，再点击“启动本机 CARLA 实测”。运行结束后会自动生成风险分析任务。</p></section>'
        )
    if task.get("kind") == "carla" and task.get("status") == "failed" and task.get("execution_mode") == "local_carla":
        actions.insert(0, f'<button class="primary-action" id="retry-local-carla" data-task="{html.escape(task_id)}">重试本机 CARLA</button>')
        next_step_section = (
            '<section class="next-step-panel"><span class="section-kicker">RETRY</span>'
            '<h2>本次运行没有连上 CARLA</h2>'
            '<p>请先启动本机 CARLA 0.9.16，并确认 localhost:2000 正在监听；确认后点击“重试本机 CARLA”。本次失败记录会保留，重试会创建新的任务记录。</p></section>'
        )
    elif task.get("kind") == "validation" and task.get("status") == "completed" and result.get("valid"):
        actions.insert(0, f'<button class="primary-action" id="compile-validation" data-task="{html.escape(task_id)}">重新编译 CARLA 配置</button>')
        next_step_section = (
            '<section class="next-step-panel"><span class="section-kicker">NEXT STEP</span>'
            '<h2>校验已通过，正在补齐 CARLA 配置</h2>'
            f'<p>{"这是单场景校验，点击上方按钮即可生成 CARLA 配置；完成后本页会出现“启动本机 CARLA 实测”。" if result.get("record_count") == 1 else "当前批次包含多个场景，不能直接编译成一个 CARLA 配置；请回到“设计场景”把数量设为 1。"}</p>'
            f'{"" if result.get("record_count") == 1 else "<div class=\"workflow-actions\"><a class=\"primary-link\" href=\"/generation\">重新生成单个场景</a></div>"}</section>'
        )
    if task.get("parent_task_id"):
        parent = html.escape(str(task["parent_task_id"]))
        actions.append(f'<a class="button-link" href="/tasks/{parent}">查看上一步</a>')

    external_section = ""
    if task.get("kind") == "carla" and task.get("status") in {"awaiting_confirmation", "confirmed_manual"}:
        external_section = f"""
        <section class="panel"><h2>选择运行方式</h2>
          <p class="plain-summary">推荐本机运行：Web 会调用本机 CARLA 客户端，运行结束后自动生成风险图和可下载的数据包。若本机没有 CARLA，再选择远端任务并导入结果。</p>
          <div class="workflow-actions"><button id="run-local-carla" data-task="{html.escape(task_id)}">本机运行 CARLA</button><button class="secondary" id="confirm-remote-carla" data-task="{html.escape(task_id)}">改用远端任务</button><span id="local-message" class="status-line" role="status"></span></div>
        </section>
        <script>
          document.getElementById("run-local-carla").addEventListener("click", async event => {{
            const button = event.currentTarget;
            button.disabled = true;
            button.textContent = "正在启动本机运行...";
            const response = await fetch("/api/tasks/{html.escape(task_id)}/run-local", {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: "{{}}"}});
            const payload = await response.json();
            if (!response.ok) {{ button.disabled = false; button.textContent = payload.error || "启动失败"; return; }}
            location.reload();
          }});
          document.getElementById("confirm-remote-carla").addEventListener("click", async event => {{
            const button = event.currentTarget;
            button.disabled = true;
            button.textContent = "正在登记远端任务...";
            const response = await fetch("/api/tasks/{html.escape(task_id)}/confirm", {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{confirmed: true}})}});
            const payload = await response.json();
            if (!response.ok) {{ button.disabled = false; button.textContent = payload.error || "登记失败"; return; }}
            location.reload();
          }});
        </script>
        """
    if task.get("kind") == "carla" and task.get("status") in {"confirmed_manual"}:
        external_section += f"""
        <section class="panel"><h2>导入远端 CARLA 结果</h2>
          <p class="muted">服务器任务完成后，将结果目录复制到本机输出盘。目录必须包含 <code>metadata.json</code> 和 <code>telemetry.csv</code>。</p>
          <form id="attach-result-form">
            <div class="field"><label for="run-dir">本机结果目录</label><input id="run-dir" required placeholder="F:\\Carla\\project-transfer\\server-results\\job_xxx"></div>
            <div class="form-grid"><div class="field"><label for="remote-job-id">远端 Job ID</label><input id="remote-job-id" placeholder="可选"></div><div class="field"><label for="remote-path">远端路径</label><input id="remote-path" placeholder="可选"></div></div>
            <div class="workflow-actions"><button type="submit">导入并分析</button><span id="attach-message" class="status-line" role="status"></span></div>
          </form>
        </section>
        <script>
          document.getElementById("attach-result-form").addEventListener("submit", async event => {{
            event.preventDefault();
            const message = document.getElementById("attach-message");
            message.textContent = "正在导入...";
            const response = await fetch("/api/tasks/{html.escape(task_id)}/attach-result", {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{run_dir: document.getElementById("run-dir").value, remote_job_id: document.getElementById("remote-job-id").value, remote_path: document.getElementById("remote-path").value}})}});
            const payload = await response.json();
            if (!response.ok) {{ message.textContent = payload.error || "导入失败"; message.className = "status-line error"; return; }}
            location.href = `/tasks/${{encodeURIComponent(payload.risk_task.task_id)}}`;
          }});
        </script>
        """
    result_section = '<p class="muted">任务尚未产生结果。</p>'
    if task.get("error"):
        error = task["error"]
        result_section = (
            f'<p class="status-line error"><strong>{html.escape(str(error.get("type", "Error")))}</strong>：'
            f'{html.escape(str(error.get("message", "任务失败")))}</p>'
        )
    elif result:
        if task.get("kind") == "validation":
            result_section = _validation_result_table(result)
        elif task.get("kind") == "generation":
            summary = result.get("summary") or {}
            result_section = (
                '<div class="facts">'
                f'<div class="fact"><div class="fact-label">接受数量</div><div class="fact-value">{html.escape(str(summary.get("accepted_count", "—")))}</div></div>'
                f'<div class="fact"><div class="fact-label">请求数量</div><div class="fact-value">{html.escape(str(task.get("payload", {}).get("count", "—")))}</div></div>'
                f'<div class="fact"><div class="fact-label">执行模式</div><div class="fact-value" style="font-size:16px">offline CPU</div></div>'
                '</div>'
            )
        elif task.get("kind") == "risk_analysis":
            risk = result.get("observed_risk") or {}
            risk_level = {"low": "低风险", "medium": "中风险", "high": "高风险", "critical": "极高风险"}.get(str(risk.get("level")), risk.get("level", "—"))
            result_section = (
                f'<p class="plain-summary">这次运行的风险等级是 <strong>{html.escape(str(risk_level))}</strong>，分数越高表示越需要优先检查。下面的运行状态图可以帮助普通用户快速定位风险时刻；完整 CSV 和 JSON 请下载数据包交给专业人员。</p>'
                '<div class="facts">'
                f'<div class="fact"><div class="fact-label">风险等级</div><div class="fact-value">{html.escape(str(risk_level))}</div></div>'
                f'<div class="fact"><div class="fact-label">风险分数</div><div class="fact-value">{html.escape(str(risk.get("score", "—")))}</div></div>'
                f'<div class="fact"><div class="fact-label">遥测行数</div><div class="fact-value">{html.escape(str(result.get("source_row_count", "—")))}</div></div>'
                '</div>'
            )
            visualization = result.get("visualization") or {}
            chart_name = visualization.get("chart_name")
            preview_name = visualization.get("sensor_preview_name")
            has_replay = bool((task.get("payload") or {}).get("run_dir"))
            if has_replay:
                result_section += _replay_panel(task_id)
            if chart_name:
                result_section += (
                    f'<div class="visualization"><h3>运行状态与风险时间线</h3><img class="run-chart" src="/api/tasks/{html.escape(task_id)}/artifact/{html.escape(chart_name)}" alt="CARLA 运行状态与风险时间线"></div>'
                )
            if preview_name and not has_replay:
                result_section += (
                    f'<div class="visualization"><h3>传感器首帧预览</h3><img class="sensor-preview" src="/api/tasks/{html.escape(task_id)}/artifact/{html.escape(preview_name)}" alt="传感器首帧"></div>'
                )
        elif task.get("kind") == "carla":
            connected = "已连接" if result.get("carla_connected") else "未确认"
            acceptance = {"completed": "运行完成", "failed": "运行失败", "interrupted": "被中断"}.get(str(result.get("acceptance_status")), result.get("acceptance_status", "—"))
            sensor_status = {"completed": "传感器完整", "failed": "传感器不完整"}.get(str(result.get("sensor_status")), result.get("sensor_status", "—"))
            route_status = {"completed": "路线正常", "deviated": "路线有偏差", "disabled": "未启用路线锁定"}.get(str(result.get("route_status")), result.get("route_status", "—"))
            result_section = (
                '<p class="plain-summary">本机 CARLA 已完成一次真实仿真。普通用户先看下面四项结论；专业人员可下载完整数据包，里面包含原始遥测、元数据、配置快照、日志和风险图。</p>'
                '<div class="facts">'
                f'<div class="fact"><div class="fact-label">CARLA 连接</div><div class="fact-value" style="font-size:18px">{html.escape(connected)}</div></div>'
                f'<div class="fact"><div class="fact-label">运行结果</div><div class="fact-value" style="font-size:18px">{html.escape(str(acceptance))}</div></div>'
                f'<div class="fact"><div class="fact-label">传感器</div><div class="fact-value" style="font-size:18px">{html.escape(str(sensor_status))}</div></div>'
                f'<div class="fact"><div class="fact-label">路线</div><div class="fact-value" style="font-size:18px">{html.escape(str(route_status))}</div></div>'
                '</div>'
            )
            if result.get("risk_task_id"):
                result_section += f'<p class="muted">风险分析任务已自动创建：<a href="/tasks/{html.escape(str(result["risk_task_id"]))}">{html.escape(str(result["risk_task_id"]))}</a></p>'
        else:
            result_section = f'<pre>{_json_block(result)}</pre>'
        result_section += f'<details><summary>查看完整结构化结果</summary><pre>{_json_block(result)}</pre></details>'

    workflow_rows = "".join(
        "<tr>"
        f'<td><a href="/tasks/{html.escape(str(item["task_id"]))}"><code>{html.escape(str(item["task_id"]))}</code></a></td>'
        f'<td>{html.escape(str(item.get("kind")))}</td><td>{_task_status_badge(item.get("status"))}</td>'
        f'<td>{html.escape(str(item.get("created_at")))}</td>'
        "</tr>"
        for item in (workflow or {}).get("tasks", [])
    )
    workflow_section = (
        '<div class="table-wrap"><table><thead><tr><th>任务</th><th>阶段</th><th>状态</th><th>创建时间</th></tr></thead>'
        f'<tbody>{workflow_rows}</tbody></table></div>'
    )
    poll_script = ""
    if task.get("status") not in {"completed", "failed", "cancelled", "confirmed_manual"}:
        poll_script = f"""
        <script>
          setTimeout(async () => {{
            const response = await fetch("/api/tasks/{html.escape(task_id)}");
            if (response.ok) {{
              const latest = await response.json();
              if (latest.status !== {json.dumps(task.get('status'))}) location.reload();
              else location.reload();
            }}
          }}, 900);
        </script>
        """
    # Keep this script as a normal string.  It is emitted into HTML directly,
    # so f-string brace escaping would produce invalid JavaScript (for example
    # ``async () => {{``) and prevent all action handlers from binding.
    action_script = """
    <script>
      const taskId = __TASK_ID__;
      const taskPath = "/api/tasks/" + encodeURIComponent(taskId);
      const registerCarlaButton = document.getElementById("register-carla");
      if (registerCarlaButton) registerCarlaButton.addEventListener("click", async () => {
        registerCarlaButton.disabled = true;
        registerCarlaButton.textContent = "正在启动本机 CARLA...";
        const response = await fetch(taskPath + "/carla", {
          method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({requested_by: "web", execution_target: "local"})
        });
        const payload = await response.json();
        if (!response.ok) { registerCarlaButton.disabled = false; registerCarlaButton.textContent = payload.error || "登记失败"; return; }
        location.href = "/tasks/" + encodeURIComponent(payload.task_id);
      });
      const validateButton = document.getElementById("validate-generated");
      if (validateButton) validateButton.addEventListener("click", async () => {
        validateButton.disabled = true;
        validateButton.textContent = "正在创建校验任务...";
        const response = await fetch(taskPath + "/validate", {
          method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({compile: validateButton.dataset.compile === "true"})
        });
        const payload = await response.json();
        if (!response.ok) { validateButton.disabled = false; validateButton.textContent = payload.error || "创建失败"; return; }
        location.href = "/tasks/" + encodeURIComponent(payload.task_id);
      });
      const compileButton = document.getElementById("compile-validation");
      if (compileButton) compileButton.addEventListener("click", async () => {
        compileButton.disabled = true;
        compileButton.textContent = "正在编译 CARLA 配置...";
        const response = await fetch(taskPath + "/compile", {
          method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
        });
        const payload = await response.json();
        if (!response.ok) { compileButton.disabled = false; compileButton.textContent = payload.error || "编译失败"; return; }
        location.reload();
      });
      const retryCarlaButton = document.getElementById("retry-local-carla");
      if (retryCarlaButton) retryCarlaButton.addEventListener("click", async () => {
        retryCarlaButton.disabled = true;
        retryCarlaButton.textContent = "正在创建重试任务...";
        const response = await fetch(taskPath + "/retry", {
          method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
        });
        const payload = await response.json();
        if (!response.ok) { retryCarlaButton.disabled = false; retryCarlaButton.textContent = payload.error || "重试失败"; return; }
        location.href = "/tasks/" + encodeURIComponent(payload.task_id);
      });
    </script>
    """.replace("__TASK_ID__", json.dumps(task_id, ensure_ascii=False))
    content = f"""
    <div class="stack">
      <section class="panel"><h2>任务概览</h2><div class="detail-grid">{overview}</div><div class="workflow-actions">{''.join(actions)}</div></section>
      {next_step_section}
      {external_section}
      <section class="panel"><h2>结果</h2><div class="result">{result_section}</div></section>
      <section class="panel"><h2>产物与哈希</h2>{_artifact_table(task.get('artifacts', []))}</section>
      <section class="panel"><h2>工作流</h2>{workflow_section}</section>
      <section class="panel"><h2>输入快照</h2><pre>{_json_block(task.get('payload', {}))}</pre></section>
    </div>
    {action_script}{poll_script}
    """
    return _page("任务详情", content, subtitle=f"{task_id} · 可追溯任务与证据")


def _workflow_page(kind):
    """Render one complete submit -> poll -> result workflow."""
    configs = {
        "generation": {
            "title": "场景生成",
            "subtitle": "M01 · CPU 离线生成任务",
            "fields": """
              <div class="form-grid">
                <div class="field"><label for="model">生成器</label><select id="model"><option value="lhs">LHS</option><option value="gmm">GMM</option><option value="cvae">CVAE</option><option value="diffusion">Diffusion</option></select></div>
                <div class="field"><label for="risk">目标风险档</label><select id="risk"><option>low</option><option selected>medium</option><option>high</option><option>critical</option></select></div>
                <div class="field"><label for="weather_tags">天气标签</label><input id="weather_tags" placeholder="night,heavy_rain"></div>
                <div class="field"><label for="count">生成数量</label><input id="count" type="number" min="1" max="64" value="1"></div>
                <div class="field"><label for="seed">随机种子</label><input id="seed" type="number" value="20260823"></div>
                <div class="field"><label for="artifact">模型产物路径（GMM/CVAE/Diffusion）</label><input id="artifact" placeholder="F:\\Carla\\models\\checkpoint.pt"></div>
              </div>
            """,
        },
        "validation": {
            "title": "场景校验",
            "subtitle": "M02 · Schema、语义和物理约束",
            "fields": f"""
              <div class="field"><label for="record_path">记录路径（JSON/JSONL）</label><input id="record_path" value="{html.escape(str(PROJECT_ROOT / 'data' / 'scenarios' / 'seed_v1' / 'example_record.json'))}"></div>
              <div class="field"><label for="record_json">或粘贴单条 JSON 记录</label><textarea id="record_json" placeholder="与记录路径二选一"></textarea></div>
              <div class="field"><label for="base_config_path">基础 CARLA 配置</label><input id="base_config_path" value="{html.escape(str(PROJECT_ROOT / 'configs' / 'multi_hazard_rainy_night.json'))}"></div>
              <label class="check"><input id="compile" type="checkbox" checked> 校验通过后编译 CARLA 配置</label>
            """,
        },
        "risk_analysis": {
            "title": "风险分析",
            "subtitle": "M05 · 遥测风险与可追溯诊断",
            "fields": """
              <div class="field"><label for="run_dir">运行目录（含 telemetry.csv / metadata.json）</label><input id="run_dir" placeholder="F:\\Carla\\output-0.9.16\\...\\run"></div>
              <div class="form-grid">
                <div class="field"><label for="telemetry_path">遥测 CSV（可选）</label><input id="telemetry_path"></div>
                <div class="field"><label for="metadata_path">metadata.json（可选）</label><input id="metadata_path"></div>
                <div class="field"><label for="config_path">场景配置（可选）</label><input id="config_path"></div>
                <div class="field"><label for="collision_count">碰撞事件数（可选）</label><input id="collision_count" type="number" min="0" placeholder="优先读取 metadata"></div>
              </div>
            """,
        },
    }
    config = configs[kind]
    script = f"""
    <script>
      const kind = {json.dumps(kind)};
      const esc = value => String(value ?? "").replace(/[&<>'"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\\\"":"&quot;"}}[c]));
      const statusLabels = {{queued:"排队中", running:"运行中", completed:"已完成", failed:"失败", cancelled:"已取消", awaiting_confirmation:"等待选择运行方式", confirmed_manual:"等待远端结果"}};
      const riskLabels = {{low:"低风险", medium:"中风险", high:"高风险", critical:"极高风险"}};
      const message = (text, tone="") => {{ const node = document.getElementById("status"); node.textContent = text; node.className = `status-line ${{tone}}`; }};
      let pollTimer = null;
      function readPayload() {{
        if (kind === "generation") return {{model: model.value, risk: risk.value, weather_tags: weather_tags.value, count: Number(count.value), seed: Number(seed.value), artifact: artifact.value || undefined}};
        if (kind === "validation") {{
          const payload = {{compile: compile.checked, base_config_path: base_config_path.value}};
          if (record_json.value.trim()) payload.record = JSON.parse(record_json.value);
          else payload.record_path = record_path.value;
          return payload;
        }}
        const payload = {{run_dir: run_dir.value, telemetry_path: telemetry_path.value, metadata_path: metadata_path.value, config_path: config_path.value}};
        if (collision_count.value !== "") payload.collision_count = Number(collision_count.value);
        return payload;
      }}
      function resultHeadline(task) {{
        if (!task.result) return "";
        if (kind === "generation") return `已生成 ${{task.result.summary?.accepted_count ?? "—"}} 条，产物：${{task.result.output_path || "—"}}`;
        if (kind === "validation") return `校验 ${{task.result.valid ? "通过" : "未通过"}}，记录 ${{task.result.record_count ?? 1}} 条`;
        const risk = task.result.observed_risk || {{}};
        return `实测风险：${{riskLabels[risk.level] || risk.level || "—"}} / ${{risk.score ?? "—"}}，方法：${{risk.method || "—"}}`;
      }}
      function issueText(issue) {{
        if (issue && typeof issue === "object") return issue.message || issue.code || JSON.stringify(issue);
        return String(issue);
      }}
      function validationTable(result) {{
        const physical = new Map((result.physical_constraints?.results || []).map(item => [item.line_number, item]));
        const rows = (result.items || []).map(item => {{
          const schema = item.result || {{}};
          const physics = physical.get(item.line) || {{}};
          const errors = [...(schema.errors || []), ...(physics.errors || [])];
          const warnings = [...(schema.warnings || []), ...(physics.warnings || [])];
          const valid = Boolean(schema.valid && physics.valid);
          const issues = [...errors, ...warnings].map(issue => `<li>${{esc(issueText(issue))}}</li>`).join("") || "<li>无</li>";
          return `<tr><td>${{esc(item.line)}}</td><td><code>${{esc(item.sample_id || "未命名")}}</code></td><td><span class="badge ${{valid ? "success" : "error"}}">${{valid ? "通过" : "未通过"}}</span></td><td>${{errors.length}}</td><td>${{warnings.length}}</td><td><ul class="issue-list">${{issues}}</ul></td></tr>`;
        }}).join("");
        return `<div class="table-wrap"><table class="validation-table"><thead><tr><th>行</th><th>场景 ID</th><th>结果</th><th>错误</th><th>警告</th><th>说明</th></tr></thead><tbody>${{rows}}</tbody></table></div>`;
      }}
      async function validateGenerated(taskId, compile) {{
        message("正在创建校验任务...");
        const response = await fetch(`/api/tasks/${{encodeURIComponent(taskId)}}/validate`, {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{compile}})}});
        const task = await response.json();
        if (!response.ok) throw new Error(task.error || "校验任务创建失败");
        location.href = `/tasks/${{encodeURIComponent(task.task_id)}}`;
      }}
      function renderResult(task) {{
        const box = document.getElementById("result");
        if (!task.result && !task.error) {{ box.innerHTML = ""; return; }}
        const payload = task.result || {{error: task.error}};
        const validation = kind === "validation" && task.result ? validationTable(task.result) : "";
        const compileReady = kind === "generation" && Number(task.result?.summary?.accepted_count ?? 0) === 1;
        const continueAction = kind === "generation" && task.status === "completed"
          ? `<button type="button" class="primary-action" id="validate-batch" data-compile="${{compileReady}}">${{compileReady ? "校验并准备 CARLA" : "校验本批次"}}</button>` : "";
        const carlaReady = kind === "validation" && task.status === "completed" && task.result?.valid && task.result?.compiled_config_path;
        const recompileReady = kind === "validation" && task.status === "completed" && task.result?.valid && !task.result?.compiled_config_path && Number(task.result?.record_count ?? 0) === 1;
        const carlaAction = carlaReady ? `<button type="button" class="primary-action" id="run-carla-now">启动本机 CARLA 实测</button>` : recompileReady ? `<button type="button" class="primary-action" id="compile-now">重新编译 CARLA 配置</button>` : "";
        box.innerHTML = `<div class="result"><h3>任务结果</h3><p class="muted">${{esc(resultHeadline(task))}}</p>${{validation}}<div class="workflow-actions">${{continueAction}}${{carlaAction}}<a href="/tasks/${{encodeURIComponent(task.task_id)}}">查看任务详情与证据</a></div><details><summary>查看完整结构化结果</summary><pre>${{esc(JSON.stringify(payload, null, 2))}}</pre></details></div>`;
        const validateButton = document.getElementById("validate-batch");
        if (validateButton) validateButton.addEventListener("click", () => validateGenerated(task.task_id, validateButton.dataset.compile === "true").catch(error => message(error.message, "error")));
        const runCarlaButton = document.getElementById("run-carla-now");
        if (runCarlaButton) runCarlaButton.addEventListener("click", async () => {{
          runCarlaButton.disabled = true;
          runCarlaButton.textContent = "正在准备本机 CARLA...";
          const response = await fetch(`/api/tasks/${{encodeURIComponent(task.task_id)}}/carla`, {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{requested_by:"web", execution_target:"local"}})}});
          const nextTask = await response.json();
          if (!response.ok) {{ runCarlaButton.disabled = false; runCarlaButton.textContent = nextTask.error || "启动失败"; return; }}
          location.href = `/tasks/${{encodeURIComponent(nextTask.task_id)}}`;
        }});
        const compileButton = document.getElementById("compile-now");
        if (compileButton) compileButton.addEventListener("click", async () => {{
          compileButton.disabled = true;
          compileButton.textContent = "正在编译 CARLA 配置...";
          const response = await fetch(`/api/tasks/${{encodeURIComponent(task.task_id)}}/compile`, {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:"{{}}"}});
          const rebuilt = await response.json();
          if (!response.ok) {{ compileButton.disabled = false; compileButton.textContent = rebuilt.error || "编译失败"; return; }}
          location.href = `/tasks/${{encodeURIComponent(task.task_id)}}`;
        }});
      }}
      async function getTask(taskId) {{
        const response = await fetch(`/api/tasks/${{encodeURIComponent(taskId)}}`);
        const task = await response.json();
        if (!response.ok) throw new Error(task.error || "任务状态读取失败");
        message(`任务 ${{task.task_id}}：${{statusLabels[task.status] || task.status}}`);
        renderResult(task);
        if (["completed","failed","cancelled","confirmed_manual"].includes(task.status)) {{ clearInterval(pollTimer); pollTimer = null; message(`任务 ${{task.task_id}}：${{statusLabels[task.status] || task.status}}`, ["completed","confirmed_manual"].includes(task.status) ? "success" : "error"); }}
      }}
      document.getElementById("workflow-form").addEventListener("submit", async event => {{
        event.preventDefault();
        try {{
          message("正在提交任务...");
          const response = await fetch("/api/tasks", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{kind, payload:readPayload()}})}});
          const task = await response.json();
          if (!response.ok) throw new Error(task.error || "任务提交失败");
          if (pollTimer) clearInterval(pollTimer);
          await getTask(task.task_id);
          pollTimer = setInterval(() => getTask(task.task_id).catch(error => message(error.message, "error")), 700);
        }} catch (error) {{ message(error.message, "error"); }}
      }});
    </script>
    """
    content = f"""
    <section class="panel">
      <h2>{html.escape(config['title'])}</h2>
      <form id="workflow-form">{config['fields']}<div class="workflow-actions"><button type="submit">提交任务</button><button type="reset" class="secondary">清空</button><a href="/tasks" style="padding:9px 0">查看全部任务</a></div></form>
      <p id="status" class="status-line" role="status">等待提交</p>
      <div id="result"></div>
    </section>
    {script}
    """
    return _page(config["title"], content, subtitle=config["subtitle"])


def _tasks_page():
    content = """
    <section class="panel">
      <h2>任务编排</h2>
      <p class="plain-summary">默认使用本机执行：生成、校验和风险分析使用本机 CPU；CARLA 使用本机已启动的 CARLA 0.9.16。没有本机 CARLA 时，仍可保留远端登记并导入结果。</p>
      <form id="task-form">
        <label for="task-kind">任务类型</label>
        <select id="task-kind">
          <option value="generation">场景生成</option>
          <option value="validation">场景校验</option>
          <option value="risk_analysis">风险分析</option>
          <option value="carla">CARLA 仿真（本机优先）</option>
        </select>
        <label for="task-payload">JSON 参数</label>
        <textarea id="task-payload" rows="8" spellcheck="false">{"model":"lhs","risk":"medium","count":1,"seed":20260823}</textarea>
        <button type="submit">提交任务</button>
        <button type="button" class="secondary" id="refresh-tasks">刷新状态</button>
      </form>
      <p id="task-message" class="muted" role="status"></p>
    </section>
    <section class="panel" style="margin-top:18px">
      <h2>任务状态</h2>
      <div class="table-wrap"><table class="task-table"><colgroup><col><col><col><col><col><col></colgroup><thead><tr><th>任务 ID</th><th>类型</th><th>状态</th><th>创建时间</th><th>结果</th><th>操作</th></tr></thead><tbody id="task-rows"></tbody></table></div>
    </section>
    <script>
      const esc = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
      const message = text => document.getElementById("task-message").textContent = text;
      const kindLabels = {generation:"场景生成", validation:"场景校验", risk_analysis:"风险分析", carla:"CARLA 仿真"};
      const statusLabels = {queued:"排队中", running:"运行中", completed:"已完成", failed:"失败", cancelled:"已取消", awaiting_confirmation:"等待选择运行方式", confirmed_manual:"等待远端结果"};
      function resultSummary(task) {
        if (task.error) return `${task.error.type || "Error"}: ${task.error.message || "任务失败"}`;
        if (!task.result) return "等待结果";
        if (task.kind === "generation") return `生成 ${task.result.summary?.accepted_count ?? "—"} 条候选`;
        if (task.kind === "validation") return `校验 ${task.result.valid ? "通过" : "未通过"}，共 ${task.result.record_count ?? "—"} 条`;
        if (task.kind === "risk_analysis") return `风险 ${task.result.observed_risk?.level || "—"} / ${task.result.observed_risk?.score ?? "—"}`;
        return task.result.message || statusLabels[task.status] || task.status;
      }
      function renderTasks(items) {
        document.getElementById("task-rows").innerHTML = items.map(task => {
          const result = resultSummary(task);
          const action = task.status === "awaiting_confirmation"
            ? `<button data-local="${esc(task.task_id)}">本机运行</button><button class="secondary" data-cancel="${esc(task.task_id)}">取消</button>` : "";
          const detail = `<a href="/tasks/${encodeURIComponent(task.task_id)}">详情</a>`;
          return `<tr><td><a href="/tasks/${encodeURIComponent(task.task_id)}"><code class="task-id" title="${esc(task.task_id)}">${esc(task.task_id)}</code></a></td><td>${esc(kindLabels[task.kind] || task.kind)}</td><td>${esc(statusLabels[task.status] || task.status)}</td><td><span class="task-created" title="${esc(task.created_at)}">${esc(task.created_at)}</span></td><td><code class="task-result" title="${esc(result)}">${esc(result)}</code></td><td><div class="workflow-actions">${action}${detail}</div></td></tr>`;
        }).join("");
        document.querySelectorAll("[data-local]").forEach(button => button.addEventListener("click", () => transition(button.dataset.local, "run-local")));
        document.querySelectorAll("[data-cancel]").forEach(button => button.addEventListener("click", () => transition(button.dataset.cancel, "cancel")));
      }
      async function loadTasks() {
        const response = await fetch("/api/tasks");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "任务读取失败");
        renderTasks(payload.items || []);
      }
      async function transition(taskId, action, confirmed) {
        const options = {method:"POST", headers:{"Content-Type":"application/json"}};
        if (action === "confirm") options.body = JSON.stringify({confirmed: Boolean(confirmed)});
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/${action}`, options);
        const payload = await response.json();
          message(response.ok ? `任务 ${taskId} 已更新为 ${statusLabels[payload.status] || payload.status || "已更新"}` : (payload.error || "任务更新失败"));
        await loadTasks();
      }
      document.getElementById("task-form").addEventListener("submit", async event => {
        event.preventDefault();
        try {
          const kind = document.getElementById("task-kind").value;
          const payload = JSON.parse(document.getElementById("task-payload").value || "{}");
          if (kind === "carla" && !payload.execution_target) payload.execution_target = "local";
          const response = await fetch("/api/tasks", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({kind, payload})});
          const result = await response.json();
          message(response.ok ? `任务已提交：${result.task_id}（${result.status}）` : (result.error || "提交失败"));
          await loadTasks();
        } catch (error) { message(error.message); }
      });
      document.getElementById("refresh-tasks").addEventListener("click", () => loadTasks().catch(error => message(error.message)));
      loadTasks().catch(error => message(error.message));
    </script>
    """
    return _page("任务编排", content, subtitle="阶段五 Web 管理系统 · M06 任务状态与结果")


MODERN_NAVIGATION = """
<nav class="app-nav" aria-label="主导航">
  <a href="/dashboard"><span class="nav-index">00</span>工作台</a>
  <a href="/scenarios"><span class="nav-index">01</span>场景库</a>
  <a href="/generation"><span class="nav-index">02</span>设计场景</a>
  <a href="/validation"><span class="nav-index">03</span>校验配置</a>
  <a href="/tasks"><span class="nav-index">04</span>运行记录</a>
  <a href="/risk"><span class="nav-index">05</span>风险分析</a>
</nav>
"""

WORKFLOW_STEPS = (
    ("generation", "/generation", "01", "设计场景", "生成候选驾驶场景"),
    ("validation", "/validation", "02", "校验配置", "检查并编译 CARLA 配置"),
    ("tasks", "/tasks", "03", "运行仿真", "启动本机 CARLA 实测"),
    ("risk", "/risk", "04", "看懂风险", "查看运行状态与风险证据"),
)


def _workflow_sidebar(active):
    links = []
    for key, href, number, label, description in WORKFLOW_STEPS:
        class_name = "workflow-nav-step active" if key == active else "workflow-nav-step"
        links.append(
            f'<a class="{class_name}" href="{href}"><span class="workflow-nav-number">{number}</span>'
            f'<span><strong>{label}</strong><small>{description}</small></span></a>'
        )
    return (
        '<aside class="workflow-sidebar" aria-label="测试流程总控">'
        '<div class="sidebar-heading"><span class="section-kicker">CONTROL</span><strong>测试流程总控</strong>'
        '<small>当前步骤会高亮显示</small></div>'
        '<a class="sidebar-overview" href="/dashboard">返回工作台总览</a>'
        '<div class="workflow-nav-list">'
        + "".join(links)
        + '</div><div class="sidebar-help"><strong>实机测试入口</strong>'
        '<p>单场景校验通过后，进入“运行仿真”即可启动本机 CARLA。没有运行证据时，不会显示真实风险结论。</p>'
        '<a href="/tasks">查看运行记录</a></div></aside>'
    )

MODERN_BASE_STYLE = """
<style>
  :root { color-scheme: light; --navy: #102a43; --navy-2: #163b5c; --ink: #172b4d; --muted: #62748a; --line: #d6e1ec; --canvas: #eef3f7; --panel: #fff; --blue: #1769aa; --blue-soft: #e8f1f8; --teal: #0f766e; --teal-soft: #e5f5f2; --orange: #c56a12; --orange-soft: #fff3df; --red: #b42318; --shadow: 0 12px 30px rgba(16,42,67,.08); }
  * { box-sizing: border-box; }
  html { background: var(--canvas); }
  body { margin: 0; background: var(--canvas); color: var(--ink); font-family: "Microsoft YaHei", "Segoe UI", sans-serif; line-height: 1.55; }
  a { color: var(--blue); }
  .site-header { background: var(--navy); color: #fff; border-bottom: 4px solid var(--orange); }
  .header-inner { max-width: 1180px; margin: 0 auto; padding: 18px clamp(16px, 4vw, 48px) 0; }
  .brand-row { display: flex; justify-content: space-between; align-items: center; gap: 18px; }
  .brand { display: inline-flex; align-items: center; gap: 10px; color: #fff; text-decoration: none; }
  .brand-mark { display: grid; place-items: center; width: 34px; height: 34px; border: 2px solid #78c2c0; color: #b6f0eb; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
  .brand-name { display: block; font-size: 15px; font-weight: 800; letter-spacing: .04em; }
  .brand-sub { display: block; margin-top: 1px; color: #a9c0d5; font: 10px/1.2 Consolas, monospace; letter-spacing: .12em; text-transform: uppercase; }
  .header-state { color: #b8cce0; font-size: 12px; text-align: right; }
  .header-copy { padding: 26px 0 20px; max-width: 740px; }
  .eyebrow, .section-kicker { color: #7fd1ca; font: 11px/1.2 Consolas, monospace; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
  .header-copy h1 { margin: 7px 0 4px; font-size: clamp(25px, 4vw, 38px); line-height: 1.2; letter-spacing: 0; }
  .header-copy p { margin: 0; color: #cfdeeb; font-size: 14px; }
  .runtime-banner { display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 17px; }
  .runtime-banner span { display: inline-flex; align-items: center; min-height: 27px; padding: 4px 9px; border: 1px solid #527491; border-radius: 5px; color: #dceaf5; font-size: 12px; }
  .runtime-banner .primary { background: #155e63; border-color: #64c7bf; color: #e6fffb; }
  .app-nav { display: flex; flex-wrap: wrap; gap: 2px; margin: 0 -5px; }
  .app-nav a { display: inline-flex; align-items: center; gap: 7px; padding: 10px 12px 12px; border-bottom: 3px solid transparent; color: #c8d9e8; text-decoration: none; font-size: 13px; }
  .app-nav a:hover, .app-nav a:focus { color: #fff; border-bottom-color: #78c2c0; background: #163b5c; }
  .nav-index { color: #7fd1ca; font: 10px Consolas, monospace; }
  .app-layout { display: grid; grid-template-columns: 224px minmax(0, 1fr); gap: 24px; max-width: 1440px; margin: 0 auto; align-items: start; }
  .workflow-sidebar { position: sticky; top: 18px; min-width: 0; min-height: calc(100vh - 36px); padding: 23px 14px 18px; background: #f8fbfd; border-right: 1px solid var(--line); }
  .sidebar-heading { display: grid; gap: 4px; padding: 0 10px 16px; border-bottom: 1px solid var(--line); }
  .sidebar-heading strong { font-size: 17px; }
  .sidebar-heading small { color: var(--muted); font-size: 12px; }
  .sidebar-overview { display: block; margin: 14px 4px 11px; padding: 9px 10px; border: 1px solid var(--line); border-radius: 5px; color: var(--blue); background: #fff; text-decoration: none; font-size: 13px; font-weight: 700; }
  .sidebar-overview:hover { border-color: var(--blue); background: var(--blue-soft); }
  .workflow-nav-list { display: grid; gap: 5px; }
  .workflow-nav-step { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 8px; align-items: start; padding: 11px 9px; border-left: 3px solid transparent; color: var(--ink); text-decoration: none; }
  .workflow-nav-step:hover { background: var(--blue-soft); }
  .workflow-nav-step.active { border-left-color: var(--teal); background: var(--teal-soft); color: #155e59; }
  .workflow-nav-number { color: var(--muted); font: 12px Consolas, monospace; padding-top: 1px; }
  .workflow-nav-step strong, .workflow-nav-step small { display: block; }
  .workflow-nav-step strong { font-size: 14px; }
  .workflow-nav-step small { margin-top: 2px; color: var(--muted); font-size: 11px; line-height: 1.45; }
  .sidebar-help { margin: 20px 4px 0; padding: 12px 10px; border-top: 3px solid var(--orange); background: var(--orange-soft); color: #70400b; font-size: 12px; line-height: 1.65; }
  .sidebar-help p { margin: 6px 0; }
  .sidebar-help a { color: #854d0e; font-weight: 700; }
  main { min-width: 0; padding: 28px clamp(0px, 2vw, 24px) 56px 0; }
  .panel { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 22px; box-shadow: var(--shadow); }
  .panel h2 { margin: 0 0 11px; font-size: 20px; line-height: 1.3; }
  .panel h3 { margin: 22px 0 8px; font-size: 16px; }
  .muted { color: var(--muted); line-height: 1.75; }
  .facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px; margin: 18px 0; }
  .fact { border: 1px solid var(--line); border-radius: 6px; padding: 14px; background: #f8fafc; }
  .fact-label { color: var(--muted); font-size: 12px; }
  .fact-value { margin-top: 5px; font-size: 24px; font-weight: 800; line-height: 1.25; }
  .links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
  .links a { color: var(--blue); border: 1px solid var(--line); border-radius: 6px; padding: 12px; text-decoration: none; background: #fff; }
  .links a:hover { border-color: var(--blue); background: var(--blue-soft); }
  .hero-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .65fr); gap: 18px; align-items: stretch; }
  .hero-panel { background: var(--navy); color: #fff; border: 0; }
  .hero-panel h2 { max-width: 620px; margin-top: 8px; font-size: clamp(24px, 3.5vw, 34px); }
  .hero-panel p { max-width: 650px; color: #c8d9e8; }
  .hero-panel .eyebrow { color: #8edbd4; }
  .readout-panel { border-left: 4px solid var(--teal); }
  .readout-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 14px; }
  .readout-title { color: var(--muted); font: 11px Consolas, monospace; font-weight: 700; letter-spacing: .12em; }
  .readout-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
  .readout-row:last-child { border-bottom: 0; }
  .readout-row span { color: var(--muted); }
  .section-block { margin-top: 28px; }
  .section-heading { margin-bottom: 13px; }
  .section-heading h2 { margin: 5px 0 4px; font-size: 22px; }
  .section-heading p { margin: 0; color: var(--muted); }
  .process-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .process-step { display: block; min-height: 160px; padding: 16px; border: 1px solid var(--line); border-top: 4px solid var(--blue); border-radius: 7px; background: #fff; color: var(--ink); text-decoration: none; box-shadow: 0 5px 16px rgba(16,42,67,.05); }
  .process-step:hover { border-color: var(--blue); background: var(--blue-soft); }
  .process-step:nth-child(2) { border-top-color: var(--teal); }
  .process-step:nth-child(3) { border-top-color: var(--orange); }
  .process-step:nth-child(4) { border-top-color: #7c3aed; }
  .step-number { color: var(--muted); font: 12px Consolas, monospace; }
  .process-step h3 { margin: 17px 0 5px; font-size: 16px; }
  .process-step p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65; }
  .beginner-note { margin-top: 18px; border-left: 4px solid var(--orange); background: var(--orange-soft); box-shadow: none; }
  .beginner-note strong { color: #854d0e; }
  form { display: grid; gap: 8px; }
  label { color: var(--muted); font-size: 13px; font-weight: 700; }
  input, select, textarea, button { font: inherit; border: 1px solid var(--line); border-radius: 5px; padding: 9px 10px; min-height: 40px; }
  input, select, textarea { width: 100%; background: #fff; color: var(--ink); }
  input:focus, select:focus, textarea:focus, button:focus, a:focus { outline: 3px solid rgba(23,105,170,.22); outline-offset: 1px; }
  textarea { resize: vertical; min-height: 120px; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
  button { width: fit-content; cursor: pointer; background: var(--blue); color: #fff; border-color: var(--blue); font-weight: 700; }
  button:hover { background: #12558a; }
  button.secondary { background: #fff; color: var(--blue); }
  .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .field { display: grid; gap: 5px; min-width: 0; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--ink); font-size: 13px; }
  .check input { width: auto; min-height: auto; }
  .visualization { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
  .run-chart { display: block; width: 100%; max-width: 1020px; height: auto; border: 1px solid var(--line); background: #f8fafc; }
  .sensor-preview { display: block; width: min(100%, 480px); max-height: 360px; object-fit: contain; border: 1px solid var(--line); background: #0f172a; }
  .result { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 16px; }
  .result pre, .panel > pre { margin: 0; max-width: 100%; padding: 12px; overflow: auto; background: #102a43; color: #e2edf5; border-radius: 5px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .result pre { max-height: 420px; }
  .result details { margin-top: 14px; }
  .result summary { cursor: pointer; color: var(--blue); font-weight: 700; }
  .status-line { min-height: 24px; color: var(--muted); }
  .status-line.error { color: var(--red); }
  .status-line.success { color: #147a6b; }
  .workflow-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .workflow-actions a, .button-link { display: inline-flex; align-items: center; min-height: 40px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 5px; color: var(--blue); background: #fff; text-decoration: none; font-weight: 700; }
  .workflow-actions a:hover, .button-link:hover { border-color: var(--blue); background: var(--blue-soft); }
  .workflow-actions .primary-link, .primary-link { background: var(--teal); border-color: var(--teal); color: #fff; }
  .workflow-actions .primary-link:hover, .primary-link:hover { background: #0b5b55; }
  .badge { display: inline-block; padding: 3px 7px; border-radius: 4px; background: #e8eef5; color: #36506a; font-size: 12px; font-weight: 700; }
  .badge.low { background: #d9f3ed; color: #12685d; }
  .badge.medium { background: #fff0d2; color: #8a500d; }
  .badge.high { background: #ffe7d1; color: #9a4512; }
  .badge.critical { background: #fbe4e1; color: #9f2419; }
  .badge.success { background: #d9f3ed; color: #12685d; }
  .badge.error { background: #fbe4e1; color: #9f2419; }
  .badge.warn { background: #fff0d2; color: #8a500d; }
  .plain-summary { padding: 13px 15px; border-left: 4px solid var(--teal); background: var(--teal-soft); color: #155e59; line-height: 1.75; }
  .next-step-panel { border: 1px solid #b9dcd7; border-left: 5px solid var(--teal); border-radius: 7px; padding: 17px 19px; background: #f1fbf9; box-shadow: var(--shadow); }
  .next-step-panel h2 { margin: 4px 0 5px; color: #155e59; }
  .next-step-panel p { margin: 0; color: #376661; }
  .next-step-panel .workflow-actions { margin-top: 13px; }
  .primary-action { background: var(--teal) !important; border-color: var(--teal) !important; color: #fff !important; }
  .export-link { background: var(--teal) !important; border-color: var(--teal) !important; color: #fff !important; }
  .detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }
  .detail-item { min-width: 0; padding: 12px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }
  .detail-item strong, .detail-item code { display: block; margin-top: 5px; overflow-wrap: anywhere; }
  .stack { display: grid; min-width: 0; gap: 18px; }
  .issue-list { margin: 0; padding-left: 18px; }
  .issue-list li { margin: 3px 0; }
  .artifact-path, .hash { max-width: 420px; overflow-wrap: anywhere; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; }
  .table-wrap { overflow-x: auto; width: 100%; max-width: 100%; }
  .task-table { table-layout: fixed; min-width: 780px; }
  .task-table th:nth-child(1), .task-table td:nth-child(1) { width: 22%; }
  .task-table th:nth-child(2), .task-table td:nth-child(2) { width: 12%; }
  .task-table th:nth-child(3), .task-table td:nth-child(3) { width: 12%; }
  .task-table th:nth-child(4), .task-table td:nth-child(4) { width: 19%; }
  .task-table th:nth-child(5), .task-table td:nth-child(5) { width: 19%; }
  .task-table th:nth-child(6), .task-table td:nth-child(6) { width: 16%; }
  .task-table .task-id, .task-table .task-created, .task-table .task-result { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .task-table .task-result { cursor: help; }
  .validation-table { table-layout: fixed; min-width: 920px; }
  .validation-table th { width: auto; }
  .validation-table th:nth-child(1), .validation-table td:nth-child(1) { width: 7%; }
  .validation-table th:nth-child(2), .validation-table td:nth-child(2) { width: 22%; }
  .validation-table th:nth-child(3), .validation-table td:nth-child(3) { width: 11%; }
  .validation-table th:nth-child(4), .validation-table td:nth-child(4) { width: 8%; }
  .validation-table th:nth-child(5), .validation-table td:nth-child(5) { width: 8%; }
  .validation-table th:nth-child(6), .validation-table td:nth-child(6) { width: 44%; }
  .validation-table td:last-child { overflow-wrap: anywhere; }
  th, td { padding: 9px 7px; border-bottom: 1px solid #edf1f7; text-align: left; vertical-align: top; }
  th { color: var(--muted); width: 30%; font-weight: 700; }
  code { overflow-wrap: anywhere; }
  @media (max-width: 900px) { .app-layout { grid-template-columns: 188px minmax(0, 1fr); gap: 14px; } .workflow-sidebar { padding-left: 7px; padding-right: 7px; } .workflow-nav-step { grid-template-columns: 26px minmax(0, 1fr); padding-left: 6px; padding-right: 6px; } }
  @media (max-width: 780px) { .brand-row { align-items: flex-start; flex-direction: column; } .header-state { text-align: left; } .app-layout { display: block; } .workflow-sidebar { position: static; min-height: 0; padding: 12px 16px; border-right: 0; border-bottom: 1px solid var(--line); } .sidebar-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; padding: 0 0 8px; } .workflow-nav-list { grid-template-columns: repeat(4, minmax(0, 1fr)); } .workflow-nav-step { grid-template-columns: 1fr; gap: 2px; padding: 8px; border-left: 0; border-bottom: 3px solid transparent; } .workflow-nav-step.active { border-left: 0; border-bottom-color: var(--teal); } .workflow-nav-step small { display: none; } .sidebar-help { display: none; } main { padding: 20px 16px 40px; } .hero-grid, .replay-grid { grid-template-columns: 1fr; } .process-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .facts, .links, .form-grid, .detail-grid { grid-template-columns: 1fr; } }
  @media (max-width: 520px) { .app-nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; } .app-nav a { padding-left: 4px; } .process-grid { grid-template-columns: 1fr; } .workflow-actions { align-items: stretch; flex-direction: column; } .workflow-actions button, .workflow-actions a { width: 100%; justify-content: center; } }
  .replay-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .replay-heading h3, .relative-view h3 { margin: 0 0 3px; font-size: 17px; }
  .replay-heading p, .relative-view p { margin: 0 0 12px; font-size: 12px; }
  #replay-status { flex: 0 0 auto; color: var(--muted); font-size: 12px; }
  .replay-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(250px, 1fr); gap: 18px; align-items: start; }
  .replay-media, .relative-view { min-width: 0; }
  #replay-image { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #172033; border: 1px solid var(--line); }
  .replay-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 11px 0; }
  .replay-toolbar button { min-width: 72px; }
  .replay-option { display: inline-flex; align-items: center; gap: 6px; }
  .replay-toolbar label { color: var(--muted); font-size: 12px; }
  .replay-toolbar select { width: auto; min-width: 90px; padding: 7px 8px; }
  .replay-timeline { position: relative; padding: 0 3px; }
  #replay-scrubber { display: block; width: 100%; accent-color: var(--teal); cursor: pointer; }
  .replay-event-track { position: relative; height: 11px; margin: 0 8px; }
  .replay-event-tick { position: absolute; top: 1px; width: 3px; height: 9px; background: var(--orange); }
  .replay-time { display: flex; justify-content: space-between; color: var(--muted); font-size: 12px; }
  .relative-road { display: grid; place-items: center; height: 320px; overflow: hidden; background: #e9eef0; border: 1px solid var(--line); }
  .road-lane { position: relative; width: min(100%, 180px); height: 100%; background: #6a737a; border-left: 5px solid #f7f9fa; border-right: 5px solid #f7f9fa; }
  .road-lane::before { content: ""; position: absolute; top: 0; bottom: 0; left: calc(50% - 1px); border-left: 2px dashed #dfe6e8; }
  .schematic-car { position: absolute; left: calc(50% - 28px); display: grid; place-items: center; width: 56px; height: 55px; border: 2px solid #fff; border-radius: 6px; color: #fff; font-size: 12px; font-weight: 700; box-shadow: 0 2px 5px #0003; }
  .schematic-car::before { content: ""; position: absolute; top: 4px; width: 29px; height: 5px; background: #fff9; }
  .ego-car { bottom: 22px; background: #1769aa; }
  .lead-car { bottom: 160px; background: #0f766e; transition: bottom 80ms linear; }
  .replay-readouts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
  .replay-readouts div { min-width: 0; padding: 8px 10px; border: 1px solid var(--line); background: #f7fafb; }
  .replay-readouts span { display: block; color: var(--muted); font-size: 11px; }
  .replay-readouts strong { display: block; margin-top: 2px; font-size: 16px; }
  .replay-event { margin: 10px 0 0 !important; min-height: 20px; font-size: 12px; color: #8a500d; }
  .replay-unavailable .replay-grid { display: none; }
  @media (max-width: 780px) { .replay-grid { grid-template-columns: 1fr; } }
</style>
"""


def _page(title, content, *, subtitle="面向 CARLA 的极端场景仿真测试台"):
    active = {
        "场景生成": "generation",
        "场景校验": "validation",
        "风险分析": "risk",
        "任务编排": "tasks",
        "任务详情": "tasks",
        "场景库": None,
        "工作台": None,
    }.get(title, "tasks")
    return (
        "<!doctype html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)} · 极端场景测试台</title>{MODERN_BASE_STYLE}</head><body>"
        f"<header class=\"site-header\"><div class=\"header-inner\"><div class=\"brand-row\"><a class=\"brand\" href=\"/dashboard\"><span class=\"brand-mark\">ES</span><span><span class=\"brand-name\">极端场景测试台</span><span class=\"brand-sub\">CARLA SCENARIO LAB</span></span></a><span class=\"header-state\">本机工作区 · CPU 离线分析 · CARLA 显式运行</span></div><div class=\"header-copy\"><span class=\"eyebrow\">SCENARIO TEST WORKBENCH</span><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div><div class=\"runtime-banner\"><span class=\"primary\">本机优先运行</span><span>生成、校验、分析默认不占用 GPU</span><span>真实 CARLA 运行前启动本机 0.9.16 / 2000</span></div>{MODERN_NAVIGATION}</div></header>"
        f"<div class=\"app-layout\">{_workflow_sidebar(active)}<main>{content}</main></div></body></html>"
    )


def _home_page(summary):
    summary = summary or {}
    content = f"""
    <section class="hero-grid">
      <section class="panel hero-panel">
        <span class="eyebrow">WHAT THIS TOOL DOES</span>
        <h2>把驾驶参数变成看得懂、查得清的仿真证据</h2>
        <p>这是一个面向自动驾驶测试的场景工作台：你可以设计极端天气和交通条件，先做安全校验，再运行 CARLA，最后查看风险图和完整原始数据。</p>
        <div class="workflow-actions"><a class="primary-link" href="/generation">开始设计一个场景</a><a href="/scenarios">先浏览已有场景</a></div>
      </section>
      <aside class="panel readout-panel">
        <div class="readout-head"><span class="readout-title">WORKSPACE STATUS</span><span class="badge success">可用</span></div>
        <div class="readout-row"><span>场景库</span><strong>{html.escape(str(summary.get('entry_count', '—')))} 个可检索场景</strong></div>
        <div class="readout-row"><span>严格验收证据</span><strong>{html.escape(str(summary.get('accepted_run_evidence_count', '—')))} 条</strong></div>
        <div class="readout-row"><span>运行位置</span><strong>本机优先</strong></div>
        <div class="readout-row"><span>专业出口</span><strong>ZIP 原始数据包</strong></div>
      </aside>
    </section>
    <section class="section-block">
      <div class="section-heading"><span class="section-kicker">THE WORKFLOW</span><h2>一条清晰的测试路径</h2><p>新手只需沿着四个步骤走；每一步都会保存结果，专业人员可以继续查看原始证据。</p></div>
      <div class="process-grid">
        <a class="process-step" href="/generation"><span class="step-number">01 / DESIGN</span><h3>设计场景</h3><p>选择生成方式、风险档位、天气和数量，得到候选驾驶场景。</p></a>
        <a class="process-step" href="/validation"><span class="step-number">02 / CHECK</span><h3>校验配置</h3><p>检查字段、物理约束，并生成 CARLA 可以读取的配置。</p></a>
        <a class="process-step" href="/tasks"><span class="step-number">03 / RUN</span><h3>运行仿真</h3><p>在任务详情中启动本机 CARLA，或登记远端结果。</p></a>
        <a class="process-step" href="/risk"><span class="step-number">04 / EXPLAIN</span><h3>看懂风险</h3><p>查看风险等级、运行状态图、传感器画面，并导出完整数据包。</p></a>
      </div>
    </section>
    <section class="panel beginner-note"><strong>第一次使用？</strong> 从“设计场景”开始即可。页面里的“风险档位”是设计条件，不等于真实危险程度；只有完成 CARLA 运行后，才会出现实测风险证据。</section>
    """
    return _page("工作台", content, subtitle="从场景设计到风险证据的一站式本机工作流")


def _scenario_library_page():
    content = """
    <section class="panel">
      <div class="section-heading"><span class="section-kicker">SCENARIO LIBRARY</span><h2>已有场景库</h2><p>这里的每一行都是一个可追溯的驾驶测试场景。先按风险和标签筛选，再打开详情查看参数与证据。</p></div>
      <div class="facts" id="library-summary"><div class="fact"><div class="fact-label">正在读取</div><div class="fact-value">—</div></div></div>
      <div class="form-grid" style="margin-bottom:14px"><div class="field"><label for="library-search">搜索场景编号或库 ID</label><input id="library-search" type="search" placeholder="例如 high、rain、cvae"></div><div class="field"><label for="library-risk">实测风险</label><select id="library-risk"><option value="">全部风险档位</option><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option><option value="critical">极高风险</option></select></div></div>
      <div class="workflow-actions"><button type="button" class="secondary" id="library-reset">清除筛选</button><span id="library-count" class="status-line" role="status">正在读取场景库…</span></div>
      <div class="table-wrap"><table class="task-table" style="min-width:700px"><thead><tr><th>场景编号</th><th>生成方式</th><th>设计风险</th><th>实测风险</th><th>分数</th><th>碰撞</th><th>操作</th></tr></thead><tbody id="library-rows"></tbody></table></div>
    </section>
    <section class="panel" style="margin-top:18px"><span class="section-kicker">HOW TO READ IT</span><h2>普通用户先看什么</h2><p class="muted">先看“实测风险”和“碰撞”，再看“证据”是否完整。设计风险只是输入条件，不能代替 CARLA 实测结果。打开某个场景后，页面会把专业字段和原始参数放在详情中。</p></section>
    <script>
      const escLibrary = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
      const riskLabel = value => ({low:"低", medium:"中", high:"高", critical:"极高"}[value] || value || "未知");
      const riskBadge = value => `<span class="badge ${escLibrary(value)}">${riskLabel(value)}</span>`;
      let libraryRows = [];
      function renderLibrary() {
        const search = document.getElementById("library-search").value.trim().toLowerCase();
        const risk = document.getElementById("library-risk").value;
        const rows = libraryRows.filter(row => {
          const text = `${row.sample_id} ${row.library_id} ${row.generators} ${row.weather_tags || ""}`.toLowerCase();
          return (!search || text.includes(search)) && (!risk || row.observed_risk_level === risk);
        });
        document.getElementById("library-count").textContent = `显示 ${rows.length} / ${libraryRows.length} 个场景`;
        document.getElementById("library-rows").innerHTML = rows.map(row => `<tr><td><code>${escLibrary(row.sample_id)}</code></td><td>${escLibrary(row.generators)}</td><td>${riskBadge(row.target_risk_levels)}</td><td>${riskBadge(row.observed_risk_level)}</td><td>${row.risk_score_mean == null ? "—" : Number(row.risk_score_mean).toFixed(2)}</td><td>${row.collision_observed ? "有" : "无"}</td><td><a class="button-link" href="/scenarios/${encodeURIComponent(row.library_id)}">查看详情</a></td></tr>`).join("");
      }
      async function fetchJson(url) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
          const response = await fetch(url, {headers: {"Accept": "application/json"}, signal: controller.signal});
          if (!response.ok) throw new Error(`${url} 返回 HTTP ${response.status}`);
          return await response.json();
        } catch (error) {
          if (error.name === "AbortError") throw new Error(`${url} 请求超时，请确认 Web 服务仍在运行`);
          throw error;
        } finally {
          clearTimeout(timeout);
        }
      }
      async function loadLibrary() {
        const [summary, scenarios] = await Promise.all([fetchJson("/api/summary"), fetchJson("/api/scenarios")]);
        libraryRows = scenarios.items || [];
        document.getElementById("library-summary").innerHTML = `<div class="fact"><div class="fact-label">独立场景</div><div class="fact-value">${escLibrary(summary.entry_count)}</div></div><div class="fact"><div class="fact-label">严格验收证据</div><div class="fact-value">${escLibrary(summary.accepted_run_evidence_count)}</div></div><div class="fact"><div class="fact-label">高/极高风险场景</div><div class="fact-value">${escLibrary(summary.high_or_critical_scene_count)}</div></div>`;
        renderLibrary();
      }
      ["library-search", "library-risk"].forEach(id => document.getElementById(id).addEventListener("input", renderLibrary));
      document.getElementById("library-reset").addEventListener("click", () => { document.getElementById("library-search").value = ""; document.getElementById("library-risk").value = ""; renderLibrary(); });
      loadLibrary().catch(error => {
        libraryRows = [];
        document.getElementById("library-summary").innerHTML = `<div class="fact"><div class="fact-label">读取失败</div><div class="fact-value">请检查服务</div></div>`;
        document.getElementById("library-rows").innerHTML = `<tr><td colspan="7" class="muted">${escLibrary(error.message)}。刷新页面后可重试。</td></tr>`;
        document.getElementById("library-count").textContent = "场景库暂时不可用";
      });
    </script>
    """
    return _page("场景库", content, subtitle="117 个可检索场景与历史实测证据")


class WebAppHandler(DashboardHandler):
    """在 M07 只读 API 上增加本机优先的任务与证据接口。"""

    task_manager = None

    def _get_task_manager(self):
        manager = getattr(type(self), "task_manager", None)
        if manager is None:
            manager = TaskManager(DEFAULT_TASK_DIR)
            type(self).task_manager = manager
        return manager

    def _send_page(self, payload):
        self._send(200, "text/html; charset=utf-8", payload)

    def _send_no_content(self):
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_download(self, path, filename):
        body = Path(path).read_bytes()
        encoded_filename = quote(filename)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="download.zip"; filename*=UTF-8\'\'{encoded_filename}',
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request_path = urlsplit(self.path).path
        if request_path == "/static/replay.js":
            self._send(200, "application/javascript; charset=utf-8", (PROJECT_ROOT / "tools" / "web_replay.js").read_bytes())
            return
        if request_path == "/hybridaction/zybTrackerStatisticsAction":
            # A browser-side tracker may probe this path on localhost. It is
            # unrelated to the application and should not look like a fault.
            self._send_no_content()
            return
        manager = self._get_task_manager()
        if request_path == "/api/tasks":
            items = manager.list_tasks()
            self._send_json(200, {"count": len(items), "items": items})
            return
        if request_path.startswith("/api/tasks/"):
            replay_parts = unquote(request_path[len("/api/tasks/"):]).split("/")
            if len(replay_parts) >= 2 and replay_parts[1] == "replay":
                task = manager.get(replay_parts[0])
                if task is None or task.get("kind") != "risk_analysis" or task.get("status") != "completed":
                    self._send_json(404, {"error": "未找到已完成的风险分析任务"})
                    return
                run_dir = (task.get("payload") or {}).get("run_dir")
                if not run_dir:
                    self._send_json(404, {"error": "该任务没有传感器运行目录"})
                    return
                if len(replay_parts) == 2:
                    manifest = build_replay_manifest(run_dir)
                    if manifest is None:
                        self._send_json(404, {"error": "该运行没有可回放的传感器帧"})
                    else:
                        self._send_json(200, manifest)
                    return
                if len(replay_parts) == 5 and replay_parts[2] == "frame":
                    try:
                        frame = resolve_replay_frame(run_dir, replay_parts[3], replay_parts[4])
                    except ValueError as error:
                        self._send_json(400, {"error": str(error)})
                        return
                    content_type = "image/png" if frame.suffix.lower() == ".png" else "image/jpeg"
                    self._send(200, content_type, frame.read_bytes())
                    return
                self._send_json(404, {"error": "回放路径无效"})
                return
        if request_path.startswith("/api/tasks/") and "/artifact/" in request_path:
            prefix, artifact_name = request_path.split("/artifact/", 1)
            task_id = unquote(prefix[len("/api/tasks/"):])
            task = manager.get(task_id)
            if task is None:
                self._send_json(404, {"error": "未找到任务"})
                return
            artifact_name = unquote(artifact_name).replace("\\", "/")
            if "/" in artifact_name or artifact_name in {"", ".", ".."}:
                self._send_json(400, {"error": "产物名称无效"})
                return
            allowed = {Path(item.get("path", "")).name: item for item in task.get("artifacts", [])}
            artifact = allowed.get(artifact_name)
            if artifact is None:
                self._send_json(404, {"error": "未登记该产物"})
                return
            path = Path(artifact["path"]).resolve()
            if not path.is_file():
                self._send_json(404, {"error": "产物文件不存在"})
                return
            content_type = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
            self._send(200, content_type, path.read_bytes())
            return
        if request_path.startswith("/api/tasks/"):
            task_path = unquote(request_path[len("/api/tasks/"):])
            if task_path.endswith("/export"):
                task_id = task_path[:-len("/export")].rstrip("/")
                task = manager.get(task_id)
                if task is None:
                    self._send_json(404, {"error": "未找到任务"})
                    return
                try:
                    archive = manager.export_task(task_id)
                except TaskError as error:
                    self._send_json(409, {"error": str(error), "status": task.get("status")})
                    return
                self._send_download(archive, f"{task_id}_完整数据包.zip")
                return
            if task_path.endswith("/result"):
                task_id = task_path[:-len("/result")].rstrip("/")
                task = manager.get(task_id)
                if task is None:
                    self._send_json(404, {"error": "未找到任务"})
                elif task["status"] != "completed":
                    self._send_json(409, {"error": "任务尚未完成", "status": task["status"], "task": task})
                else:
                    self._send_json(200, task["result"])
                return
            task = manager.get(task_path)
            if task is None:
                self._send_json(404, {"error": "未找到任务"})
            else:
                self._send_json(200, task)
            return
        if request_path.startswith("/api/workflows/"):
            workflow_id = unquote(request_path[len("/api/workflows/"):])
            workflow = manager.get_workflow(workflow_id)
            if workflow is None:
                self._send_json(404, {"error": "未找到工作流"})
            else:
                self._send_json(200, workflow)
            return
        if request_path.startswith("/api/"):
            return super().do_GET()
        if request_path == "/healthz":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "scenario-web",
                    "carla_connected": False,
                    "execution_default": "local",
                    "carla_requirement": "本机需提前启动 CARLA 0.9.16，RPC 端口 2000",
                    "entry_count": len(self.dashboard_data["rows"]),
                    "accepted_run_evidence_count": self.dashboard_data["summary"].get(
                        "accepted_run_evidence_count"
                    ),
                },
            )
            return
        if request_path in {"/", "/dashboard"}:
            self._send_page(_home_page(self.dashboard_data["summary"]))
            return
        if request_path == "/scenarios":
            self._send_page(_scenario_library_page())
            return
        if request_path.startswith("/scenarios/"):
            library_id = unquote(request_path[len("/scenarios/"):])
            record = self.dashboard_data["entries"].get(library_id)
            if record is None:
                self._send_json(404, {"error": "未找到场景"})
                return
            self._send_page(_detail_page(record))
            return
        pages = {
            "/generation": "generation",
            "/validation": "validation",
            "/risk": "risk_analysis",
        }
        if request_path == "/tasks":
            self._send_page(_tasks_page())
            return
        if request_path.startswith("/tasks/"):
            task_id = unquote(request_path[len("/tasks/"):])
            task = manager.get(task_id)
            if task is None:
                self._send_json(404, {"error": "未找到任务"})
                return
            self._send_page(_task_detail_page(task, manager.get_workflow(task["workflow_id"])))
            return
        if request_path in pages:
            self._send_page(_workflow_page(pages[request_path]))
            return
        self._send_json(404, {"error": "未找到页面"})

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise TaskError("Content-Length 无效") from error
        if length < 0 or length > 2 * 1024 * 1024:
            raise TaskError("请求体超过 2 MiB 限制")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaskError("请求体必须是 UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise TaskError("请求体必须是 JSON 对象")
        return payload

    def do_POST(self):
        request_path = urlsplit(self.path).path
        manager = self._get_task_manager()
        try:
            payload = self._read_json_body()
            if request_path == "/api/tasks":
                task = manager.submit(
                    payload.get("kind"),
                    payload.get("payload", {}),
                    confirm_carla=bool(payload.get("confirm_carla", False)),
                )
                self._send_json(202, task)
                return
            if request_path.startswith("/api/tasks/"):
                task_id, action = request_path[len("/api/tasks/"):].rsplit("/", 1)
                task_id = unquote(task_id)
                response_status = 200
                if action == "confirm":
                    task = manager.confirm(task_id, confirmed=bool(payload.get("confirmed", False)))
                elif action == "run-local":
                    task = manager.run_local_carla(task_id)
                    response_status = 202
                elif action == "compile":
                    task = manager.recompile_validation(task_id)
                    response_status = 202
                elif action == "retry":
                    task = manager.retry_local_carla(task_id)
                    response_status = 202
                elif action == "carla":
                    payload.setdefault("execution_target", "local")
                    task = manager.submit_carla_from_validation(task_id, payload)
                    response_status = 202
                elif action == "attach-result":
                    result = manager.attach_carla_result(task_id, payload)
                    self._send_json(202, result)
                    return
                elif action == "cancel":
                    task = manager.cancel(task_id)
                elif action == "validate":
                    task = manager.submit_validation_from_generation(task_id, payload)
                    response_status = 202
                else:
                    self._send_json(404, {"error": "未找到任务操作"})
                    return
                self._send_json(response_status, task)
                return
            self._send_json(404, {"error": "未找到接口"})
        except KeyError:
            self._send_json(404, {"error": "未找到任务"})
        except TaskError as error:
            self._send_json(400, {"error": str(error)})
        except (TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})

    def log_message(self, format_string, *arguments):
        sys.stdout.write(f"[WEB] {format_string % arguments}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="启动阶段五 Web 管理系统")
    parser.add_argument("--library-dir", default=str(DEFAULT_LIBRARY_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--task-dir", default=str(DEFAULT_TASK_DIR))
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        dashboard_data = load_dashboard_data(args.library_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"[WEB] 数据加载失败: {error}", file=sys.stderr)
        return 1

    print(f"[WEB] 场景数: {len(dashboard_data['rows'])}")
    print(f"[WEB] 严格验收来源证据: {dashboard_data['summary'].get('accepted_run_evidence_count')}")
    if args.validate_only:
        print("[WEB] validate-only 完成")
        return 0

    WebAppHandler.dashboard_data = dashboard_data
    WebAppHandler.task_manager = TaskManager(args.task_dir)
    server = ThreadingHTTPServer((args.host, args.port), WebAppHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"[WEB] 访问地址: {url}")
    print("[WEB] 默认只读模式，按 Ctrl+C 停止")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WEB] 已停止")
    finally:
        server.server_close()
        WebAppHandler.task_manager.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
