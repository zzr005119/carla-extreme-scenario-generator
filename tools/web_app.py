"""阶段五 Web 统一入口和本地任务编排 API。

场景库仍是只读数据源；离线任务写入独立任务目录。CARLA 任务只登记并
等待显式确认，不从 Web 进程启动 CARLA 或 GPU 训练。
"""

import argparse
import html
import json
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


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


NAVIGATION = """
<nav class="app-nav" aria-label="主导航">
  <a href="/dashboard">Dashboard</a>
  <a href="/scenarios">场景库</a>
  <a href="/generation">生成</a>
  <a href="/validation">校验</a>
  <a href="/tasks">任务</a>
  <a href="/risk">风险分析</a>
</nav>
"""

BASE_STYLE = """
<style>
  :root { color-scheme: light; --ink: #172033; --muted: #61708a; --line: #dbe3ef; --canvas: #f4f7fb; --primary: #2563eb; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--canvas); color: var(--ink); font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
  header { background: #132243; color: #fff; padding: 24px clamp(18px, 5vw, 72px); }
  header h1 { margin: 0 0 6px; font-size: clamp(24px, 4vw, 36px); }
  header p { margin: 0; color: #dbeafe; }
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
  @media (max-width: 700px) { .facts, .links, .form-grid, .detail-grid { grid-template-columns: 1fr; } }
</style>
"""


def _page(title, content, *, subtitle="阶段五 Web 管理系统"):
    return (
        "<!doctype html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>{BASE_STYLE}</head><body>"
        f"<header><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>{NAVIGATION}</header>"
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


def _task_status_badge(status):
    tone = " success" if status in {"completed", "confirmed_manual", "通过"} else " error" if status in {"failed", "cancelled", "未通过"} else ""
    return f'<span class="badge{tone}">{html.escape(str(status))}</span>'


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
        '<h3>逐条校验结果</h3><div class="table-wrap"><table><thead><tr><th>行</th><th>场景 ID</th><th>结果</th>'
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


def _task_detail_page(task, workflow):
    task_id = str(task["task_id"])
    result = task.get("result") or {}
    cards = [
        ("状态", _task_status_badge(task.get("status"))),
        ("类型", html.escape(str(task.get("kind")))),
        ("证据等级", html.escape(str(task.get("evidence_level", "—")))),
        ("工作流", f'<code>{html.escape(str(task.get("workflow_id", "—")))}</code>'),
    ]
    overview = "".join(
        f'<div class="detail-item"><span class="fact-label">{label}</span><strong>{value}</strong></div>'
        for label, value in cards
    )
    actions = [f'<a class="button-link" href="/tasks">返回任务列表</a>']
    if task.get("kind") == "generation" and task.get("status") == "completed":
        actions.insert(0, f'<button id="validate-generated" data-task="{html.escape(task_id)}">校验本批次</button>')
    if task.get("parent_task_id"):
        parent = html.escape(str(task["parent_task_id"]))
        actions.append(f'<a class="button-link" href="/tasks/{parent}">查看上一步</a>')

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
            result_section = (
                '<div class="facts">'
                f'<div class="fact"><div class="fact-label">风险等级</div><div class="fact-value">{html.escape(str(risk.get("level", "—")))}</div></div>'
                f'<div class="fact"><div class="fact-label">风险分数</div><div class="fact-value">{html.escape(str(risk.get("score", "—")))}</div></div>'
                f'<div class="fact"><div class="fact-label">遥测行数</div><div class="fact-value">{html.escape(str(result.get("source_row_count", "—")))}</div></div>'
                '</div>'
            )
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
    action_script = f"""
    <script>
      const validateButton = document.getElementById("validate-generated");
      if (validateButton) validateButton.addEventListener("click", async () => {{
        validateButton.disabled = true;
        validateButton.textContent = "正在创建校验任务...";
        const response = await fetch(`/api/tasks/${{encodeURIComponent(validateButton.dataset.task)}}/validate`, {{
          method: "POST", headers: {{"Content-Type": "application/json"}}, body: "{{}}"
        }});
        const payload = await response.json();
        if (!response.ok) {{ validateButton.disabled = false; validateButton.textContent = payload.error || "创建失败"; return; }}
        location.href = `/tasks/${{encodeURIComponent(payload.task_id)}}`;
      }});
    </script>
    """
    content = f"""
    <div class="stack">
      <section class="panel"><h2>任务概览</h2><div class="detail-grid">{overview}</div><div class="workflow-actions">{''.join(actions)}</div></section>
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
        return `实测风险：${{risk.level || "—"}} / ${{risk.score ?? "—"}}，方法：${{risk.method || "—"}}`;
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
        return `<div class="table-wrap"><table><thead><tr><th>行</th><th>场景 ID</th><th>结果</th><th>错误</th><th>警告</th><th>说明</th></tr></thead><tbody>${{rows}}</tbody></table></div>`;
      }}
      async function validateGenerated(taskId) {{
        message("正在创建校验任务...");
        const response = await fetch(`/api/tasks/${{encodeURIComponent(taskId)}}/validate`, {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:"{{}}"}});
        const task = await response.json();
        if (!response.ok) throw new Error(task.error || "校验任务创建失败");
        location.href = `/tasks/${{encodeURIComponent(task.task_id)}}`;
      }}
      function renderResult(task) {{
        const box = document.getElementById("result");
        if (!task.result && !task.error) {{ box.innerHTML = ""; return; }}
        const payload = task.result || {{error: task.error}};
        const validation = kind === "validation" && task.result ? validationTable(task.result) : "";
        const continueAction = kind === "generation" && task.status === "completed"
          ? `<button type="button" id="validate-batch">校验本批次</button>` : "";
        box.innerHTML = `<div class="result"><h3>任务结果</h3><p class="muted">${{esc(resultHeadline(task))}}</p>${{validation}}<div class="workflow-actions">${{continueAction}}<a href="/tasks/${{encodeURIComponent(task.task_id)}}">查看任务详情与证据</a></div><details><summary>查看完整结构化结果</summary><pre>${{esc(JSON.stringify(payload, null, 2))}}</pre></details></div>`;
        const validateButton = document.getElementById("validate-batch");
        if (validateButton) validateButton.addEventListener("click", () => validateGenerated(task.task_id).catch(error => message(error.message, "error")));
      }}
      async function getTask(taskId) {{
        const response = await fetch(`/api/tasks/${{encodeURIComponent(taskId)}}`);
        const task = await response.json();
        if (!response.ok) throw new Error(task.error || "任务状态读取失败");
        message(`任务 ${{task.task_id}}：${{task.status}}`);
        renderResult(task);
        if (["completed","failed","cancelled","confirmed_manual"].includes(task.status)) {{ clearInterval(pollTimer); pollTimer = null; message(`任务 ${{task.task_id}}：${{task.status}}`, ["completed","confirmed_manual"].includes(task.status) ? "success" : "error"); }}
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
      <p class="muted">离线任务在本机 CPU worker 中执行并保存状态。CARLA 任务只登记为待确认的外部任务，确认后仍需使用服务器任务入口执行。</p>
      <form id="task-form">
        <label for="task-kind">任务类型</label>
        <select id="task-kind">
          <option value="generation">场景生成</option>
          <option value="validation">场景校验</option>
          <option value="risk_analysis">风险分析</option>
          <option value="carla">CARLA 外部任务登记</option>
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
      function resultSummary(task) {
        if (task.error) return `${task.error.type || "Error"}: ${task.error.message || "任务失败"}`;
        if (!task.result) return "等待结果";
        if (task.kind === "generation") return `生成 ${task.result.summary?.accepted_count ?? "—"} 条候选`;
        if (task.kind === "validation") return `校验 ${task.result.valid ? "通过" : "未通过"}，共 ${task.result.record_count ?? "—"} 条`;
        if (task.kind === "risk_analysis") return `风险 ${task.result.observed_risk?.level || "—"} / ${task.result.observed_risk?.score ?? "—"}`;
        return task.result.message || task.status;
      }
      function renderTasks(items) {
        document.getElementById("task-rows").innerHTML = items.map(task => {
          const result = resultSummary(task);
          const action = task.status === "awaiting_confirmation"
            ? `<button data-confirm="${esc(task.task_id)}">确认外部任务</button><button class="secondary" data-cancel="${esc(task.task_id)}">取消</button>` : "";
          const detail = `<a href="/tasks/${encodeURIComponent(task.task_id)}">详情</a>`;
          return `<tr><td><a href="/tasks/${encodeURIComponent(task.task_id)}"><code class="task-id" title="${esc(task.task_id)}">${esc(task.task_id)}</code></a></td><td>${esc(task.kind)}</td><td>${esc(task.status)}</td><td><span class="task-created" title="${esc(task.created_at)}">${esc(task.created_at)}</span></td><td><code class="task-result" title="${esc(result)}">${esc(result)}</code></td><td><div class="workflow-actions">${action}${detail}</div></td></tr>`;
        }).join("");
        document.querySelectorAll("[data-confirm]").forEach(button => button.addEventListener("click", () => transition(button.dataset.confirm, "confirm", true)));
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
        message(response.ok ? `任务 ${taskId} 已更新为 ${payload.status}` : (payload.error || "任务更新失败"));
        await loadTasks();
      }
      document.getElementById("task-form").addEventListener("submit", async event => {
        event.preventDefault();
        try {
          const payload = JSON.parse(document.getElementById("task-payload").value || "{}");
          const response = await fetch("/api/tasks", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({kind:document.getElementById("task-kind").value, payload})});
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


class WebAppHandler(DashboardHandler):
    """在 M07 只读 API 上增加页面路由，不改变既有 API 契约。"""

    task_manager = None

    def _get_task_manager(self):
        manager = getattr(type(self), "task_manager", None)
        if manager is None:
            manager = TaskManager(DEFAULT_TASK_DIR)
            type(self).task_manager = manager
        return manager

    def _send_page(self, payload):
        self._send(200, "text/html; charset=utf-8", payload)

    def do_GET(self):
        request_path = urlsplit(self.path).path
        manager = self._get_task_manager()
        if request_path == "/api/tasks":
            items = manager.list_tasks()
            self._send_json(200, {"count": len(items), "items": items})
            return
        if request_path.startswith("/api/tasks/"):
            task_path = unquote(request_path[len("/api/tasks/"):])
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
                    "entry_count": len(self.dashboard_data["rows"]),
                    "accepted_run_evidence_count": self.dashboard_data["summary"].get(
                        "accepted_run_evidence_count"
                    ),
                },
            )
            return
        if request_path in {"/", "/dashboard", "/scenarios"}:
            self._send_page(HTML_PAGE)
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
