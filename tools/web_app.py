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
  .panel { background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 20px; }
  .panel h2 { margin: 0 0 12px; font-size: 20px; }
  .muted { color: var(--muted); line-height: 1.7; }
  .facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
  .fact { border: 1px solid var(--line); border-radius: 7px; padding: 14px; background: #f8fafc; }
  .fact-label { color: var(--muted); font-size: 12px; }
  .fact-value { margin-top: 5px; font-size: 24px; font-weight: 700; }
  .links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
  .links a { color: var(--primary); border: 1px solid var(--line); border-radius: 7px; padding: 12px; text-decoration: none; background: #fff; }
  .links a:hover { border-color: var(--primary); background: #eff6ff; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 9px 7px; border-bottom: 1px solid #edf1f7; text-align: left; vertical-align: top; }
  th { color: var(--muted); width: 30%; font-weight: 500; }
  code { overflow-wrap: anywhere; }
  @media (max-width: 700px) { .facts, .links { grid-template-columns: 1fr; } }
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


def _placeholder_page(title, module, status="接口边界已预留"):
    content = (
        '<section class="panel"><h2>'
        f"{html.escape(module)}</h2><p class=\"muted\">当前状态：{html.escape(status)}。"
        "首期不执行 CARLA、不写入场景库；接入前先补齐输入输出契约、任务状态和验收证据。</p>"
        '<div class="links"><a href="/dashboard">查看 Dashboard</a>'
        '<a href="/scenarios">查看场景库</a><a href="/healthz">查看服务健康</a></div></section>'
    )
    return _page(title, content, subtitle="阶段五 Web 管理系统 · 模块边界")


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
      <div class="table-wrap"><table><thead><tr><th>任务 ID</th><th>类型</th><th>状态</th><th>创建时间</th><th>结果</th><th>操作</th></tr></thead><tbody id="task-rows"></tbody></table></div>
    </section>
    <script>
      const esc = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
      const message = text => document.getElementById("task-message").textContent = text;
      function renderTasks(items) {
        document.getElementById("task-rows").innerHTML = items.map(task => {
          const result = task.result ? JSON.stringify(task.result) : (task.error ? task.error.message : "—");
          const action = task.status === "awaiting_confirmation"
            ? `<button data-confirm="${esc(task.task_id)}">确认外部任务</button><button class="secondary" data-cancel="${esc(task.task_id)}">取消</button>` : "";
          return `<tr><td><code>${esc(task.task_id)}</code></td><td>${esc(task.kind)}</td><td>${esc(task.status)}</td><td>${esc(task.created_at)}</td><td><code>${esc(result)}</code></td><td>${action}</td></tr>`;
        }).join("");
        document.querySelectorAll("[data-confirm]").forEach(button => button.addEventListener("click", () => transition(button.dataset.confirm, "confirm", true)));
        document.querySelectorAll("[data-cancel]").forEach(button => button.addEventListener("click", () => transition(button.dataset.cancel, "confirm", false)));
      }
      async function loadTasks() {
        const response = await fetch("/api/tasks");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "任务读取失败");
        renderTasks(payload.items || []);
      }
      async function transition(taskId, action, confirmed) {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/${action}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({confirmed})});
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
            "/generation": ("场景生成", "生成模块"),
            "/validation": ("场景校验", "校验模块"),
            "/risk": ("风险分析", "风险分析模块"),
        }
        if request_path == "/tasks":
            self._send_page(_tasks_page())
            return
        if request_path in pages:
            title, module = pages[request_path]
            self._send_page(_placeholder_page(title, module))
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
                if action == "confirm":
                    task = manager.confirm(task_id, confirmed=bool(payload.get("confirmed", False)))
                elif action == "cancel":
                    task = manager.cancel(task_id)
                else:
                    self._send_json(404, {"error": "未找到任务操作"})
                    return
                self._send_json(200, task)
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
