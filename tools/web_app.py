"""阶段五 Web 统一入口。

首期复用 M07 Dashboard 的数据契约和只读 API，提供页面路由边界，
不启动 CARLA、不写入场景库，也不占用 GPU。
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


class WebAppHandler(DashboardHandler):
    """在 M07 只读 API 上增加页面路由，不改变既有 API 契约。"""

    def _send_page(self, payload):
        self._send(200, "text/html; charset=utf-8", payload)

    def do_GET(self):
        request_path = urlsplit(self.path).path
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
            "/tasks": ("任务编排", "任务模块"),
            "/risk": ("风险分析", "风险分析模块"),
        }
        if request_path in pages:
            title, module = pages[request_path]
            self._send_page(_placeholder_page(title, module))
            return
        self._send_json(404, {"error": "未找到页面"})

    def log_message(self, format_string, *arguments):
        sys.stdout.write(f"[WEB] {format_string % arguments}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="启动阶段五 Web 管理系统")
    parser.add_argument("--library-dir", default=str(DEFAULT_LIBRARY_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
