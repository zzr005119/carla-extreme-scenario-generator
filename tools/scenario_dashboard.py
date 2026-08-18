"""提供场景库 V1 的本地只读可视化界面。"""

import argparse
import csv
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"


def _read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _parse_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_index_row(row):
    normalized = dict(row)
    normalized["sample_id"] = row.get("sample_id") or row.get("canonical_sample_id", "")
    normalized["operational_quality"] = row.get("operational_quality") or row.get("executability_score")
    normalized["risk_score_mean"] = _parse_float(row.get("risk_score_mean"))
    normalized["operational_quality"] = _parse_float(row.get("operational_quality"))
    if normalized["operational_quality"] is None:
        normalized["operational_quality"] = _parse_float(row.get("executability_score"))
    normalized["diversity_score"] = _parse_float(row.get("diversity_score"))
    normalized["collision_observed"] = _parse_bool(row.get("collision_observed"))
    return normalized


def load_dashboard_data(library_dir=DEFAULT_LIBRARY_DIR):
    library_dir = Path(library_dir).resolve()
    index_path = library_dir / "index.csv"
    entries_path = library_dir / "entries.jsonl"
    summary_path = library_dir / "summary.json"
    for required_path in (index_path, entries_path, summary_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"缺少场景库文件: {required_path}")

    with index_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = [_normalize_index_row(row) for row in csv.DictReader(file)]

    entries = {}
    with entries_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            library_id = record.get("library_id")
            if not library_id:
                raise ValueError(f"entries.jsonl 第 {line_number} 行缺少 library_id")
            entries[library_id] = record

    quality_summary_path = library_dir / "quality_analysis_v1" / "analysis_summary.json"
    quality_summary = _read_json(quality_summary_path) if quality_summary_path.is_file() else {}
    return {
        "library_dir": str(library_dir),
        "rows": rows,
        "entries": entries,
        "summary": _read_json(summary_path),
        "quality_summary": quality_summary,
    }


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


HTML_PAGE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CARLA 极端场景库 V1</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #61708a;
      --line: #dbe3ef;
      --panel: #ffffff;
      --canvas: #f4f7fb;
      --primary: #2563eb;
      --primary-soft: #eaf1ff;
      --success: #15803d;
      --warning: #b45309;
      --danger: #b91c1c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    }
    header {
      background: linear-gradient(135deg, #132243 0%, #1f4b8f 100%);
      color: #fff;
      padding: 28px clamp(18px, 5vw, 72px);
    }
    header h1 { margin: 0 0 8px; font-size: clamp(24px, 4vw, 38px); }
    header p { margin: 0; color: #dbeafe; }
    main { max-width: 1500px; margin: 0 auto; padding: 24px clamp(14px, 4vw, 48px) 48px; }
    .notice {
      border: 1px solid #f4d58d;
      background: #fff9e8;
      color: #7c4a03;
      border-radius: 12px;
      padding: 12px 16px;
      margin-bottom: 18px;
    }
    .cards { display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 12px; margin-bottom: 18px; }
    .card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 8px 24px rgba(26, 46, 84, .06); }
    .card { padding: 16px; }
    .card .label { color: var(--muted); font-size: 13px; }
    .card .value { margin-top: 8px; font-size: 28px; font-weight: 700; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(320px, .85fr); gap: 18px; align-items: start; }
    .panel { padding: 18px; }
    .panel h2 { margin: 0 0 14px; font-size: 19px; }
    .filters { display: grid; grid-template-columns: 1.4fr repeat(5, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; }
    input, select, button { border: 1px solid var(--line); border-radius: 8px; min-height: 36px; padding: 7px 9px; background: #fff; color: var(--ink); }
    button { cursor: pointer; background: var(--primary); color: #fff; border-color: var(--primary); font-weight: 600; }
    button.secondary { background: #fff; color: var(--primary); }
    .table-wrap { overflow: auto; max-height: 630px; border: 1px solid var(--line); border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; min-width: 780px; }
    th, td { padding: 10px 9px; border-bottom: 1px solid #edf1f7; text-align: left; white-space: nowrap; font-size: 13px; }
    th { position: sticky; top: 0; background: #f8fafc; color: var(--muted); z-index: 1; }
    tbody tr { cursor: pointer; }
    tbody tr:hover, tbody tr.selected { background: var(--primary-soft); }
    .badge { display: inline-flex; padding: 3px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .low { color: #166534; background: #dcfce7; }
    .medium { color: #854d0e; background: #fef3c7; }
    .high { color: #9a3412; background: #ffedd5; }
    .critical { color: #991b1b; background: #fee2e2; }
    .good { color: #166534; background: #dcfce7; }
    .caution { color: #854d0e; background: #fef3c7; }
    .detail-empty { color: var(--muted); line-height: 1.7; }
    .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 16px; }
    .detail-item { background: #f8fafc; border-radius: 9px; padding: 10px; }
    .detail-item .label { color: var(--muted); font-size: 12px; }
    .detail-item .value { margin-top: 4px; font-weight: 700; overflow-wrap: anywhere; }
    .kv { width: 100%; border-collapse: collapse; margin-top: 8px; }
    .kv td { white-space: normal; vertical-align: top; padding: 7px 4px; }
    .kv td:first-child { color: var(--muted); width: 42%; }
    .flags { display: flex; flex-wrap: wrap; gap: 6px; }
    .flag { background: #eef2f7; border-radius: 999px; padding: 4px 8px; color: #475569; font-size: 12px; }
    .subtle { color: var(--muted); font-size: 13px; }
    .status { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
    @media (max-width: 1050px) {
      .cards { grid-template-columns: repeat(3, minmax(130px, 1fr)); }
      .layout { grid-template-columns: 1fr; }
      .filters { grid-template-columns: repeat(3, minmax(130px, 1fr)); }
    }
    @media (max-width: 560px) {
      .cards { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .filters { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>CARLA 极端场景库 V1</h1>
    <p>只读管理原型 · 场景筛选 · 运行证据 · 风险结果</p>
  </header>
  <main>
    <div class="notice">当前库是风险反馈驱动的压力测试库；真实性尚未评估，页面不提供写入、修改或重新运行 CARLA 的功能。</div>
    <section class="cards" id="summary-cards"></section>
    <div class="layout">
      <section class="panel">
        <div class="status">
          <div>
            <h2>场景筛选</h2>
            <div class="subtle" id="match-count">正在加载场景库...</div>
          </div>
          <button class="secondary" id="reset-button">重置筛选</button>
        </div>
        <div class="filters">
          <input id="search" type="search" placeholder="搜索 sample_id / library_id">
          <select id="generator"><option value="">全部生成器</option><option value="lhs">LHS</option><option value="gmm">GMM</option><option value="cvae">CVAE</option></select>
          <select id="target"><option value="">全部目标风险</option><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="critical">critical</option></select>
          <select id="observed"><option value="">全部实测风险</option><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="critical">critical</option></select>
          <select id="quality"><option value="">全部质量层级</option><option value="silver">silver</option><option value="bronze">bronze</option></select>
          <select id="collision"><option value="">碰撞不限</option><option value="yes">有碰撞</option><option value="no">无碰撞</option></select>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>样本</th><th>生成器</th><th>目标风险</th><th>实测风险</th><th>均值分数</th><th>碰撞</th><th>证据</th><th>质量</th></tr></thead>
            <tbody id="scenario-rows"></tbody>
          </table>
        </div>
      </section>
      <aside class="panel" id="detail-panel">
        <h2>场景详情</h2>
        <div class="detail-empty">点击左侧场景查看参数、风险和运行证据。</div>
      </aside>
    </div>
  </main>
  <script>
    const state = { rows: [], selected: "" };

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>'"]/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[character]));
    }

    function badge(value) {
      const safeValue = escapeHtml(value || "unknown");
      const className = ["low", "medium", "high", "critical"].includes(value) ? value : "caution";
      return `<span class="badge ${className}">${safeValue}</span>`;
    }

    function formatNumber(value, digits = 3) {
      if (value === null || value === undefined || value === "") return "—";
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(digits).replace(/\.0+$/, "") : escapeHtml(value);
    }

    function formatBoolean(value) {
      return value ? "是" : "否";
    }

    function renderSummary(summary) {
      const cards = [
        ["独立场景", summary.entry_count],
        ["严格验收证据", summary.accepted_run_evidence_count],
        ["实测高/临界", summary.high_or_critical_scene_count],
        ["碰撞场景", summary.collision_scene_count],
        ["平均风险分", formatNumber(summary.mean_risk_score, 2)]
      ];
      document.getElementById("summary-cards").innerHTML = cards.map(card => `<div class="card"><div class="label">${escapeHtml(card[0])}</div><div class="value">${escapeHtml(card[1])}</div></div>`).join("");
    }

    function filteredRows() {
      const search = document.getElementById("search").value.trim().toLowerCase();
      const generator = document.getElementById("generator").value;
      const target = document.getElementById("target").value;
      const observed = document.getElementById("observed").value;
      const quality = document.getElementById("quality").value;
      const collision = document.getElementById("collision").value;
      return state.rows.filter(row => {
        const matchesSearch = !search || `${row.sample_id} ${row.library_id}`.toLowerCase().includes(search);
        const matchesGenerator = !generator || row.generators === generator;
        const matchesTarget = !target || row.target_risk_levels === target;
        const matchesObserved = !observed || row.observed_risk_level === observed;
        const matchesQuality = !quality || row.quality_tier === quality;
        const matchesCollision = !collision || (collision === "yes" ? row.collision_observed : !row.collision_observed);
        return matchesSearch && matchesGenerator && matchesTarget && matchesObserved && matchesQuality && matchesCollision;
      });
    }

    function renderRows() {
      const rows = filteredRows();
      document.getElementById("match-count").textContent = `显示 ${rows.length} / ${state.rows.length} 个场景`;
      document.getElementById("scenario-rows").innerHTML = rows.map(row => `
        <tr data-id="${escapeHtml(row.library_id)}" class="${state.selected === row.library_id ? "selected" : ""}">
          <td>${escapeHtml(row.sample_id)}</td>
          <td>${escapeHtml(row.generators)}</td>
          <td>${badge(row.target_risk_levels)}</td>
          <td>${badge(row.observed_risk_level)}</td>
          <td>${formatNumber(row.risk_score_mean, 2)}</td>
          <td>${row.collision_observed ? "⚠️ 是" : "否"}</td>
          <td>${escapeHtml(row.evidence_granularity)}</td>
          <td>${escapeHtml(row.quality_tier)}</td>
        </tr>`).join("");
      document.querySelectorAll("#scenario-rows tr").forEach(row => row.addEventListener("click", () => showDetail(row.dataset.id)));
    }

    function valueOrDash(value) {
      return value === null || value === undefined || value === "" ? "—" : escapeHtml(value);
    }

    function objectRows(object) {
      return Object.entries(object || {}).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${typeof value === "object" ? valueOrDash(JSON.stringify(value)) : valueOrDash(value)}</td></tr>`).join("");
    }

    async function showDetail(libraryId) {
      state.selected = libraryId;
      renderRows();
      const response = await fetch(`/api/scenarios/${encodeURIComponent(libraryId)}`);
      if (!response.ok) return;
      const record = await response.json();
      const parameters = record.parameters || {};
      const labels = record.labels || {};
      const evidence = record.execution_evidence || {};
      const risk = record.observed_risk || {};
      const quality = record.quality || {};
      const flags = quality.flags || [];
      document.getElementById("detail-panel").innerHTML = `
        <h2>场景详情</h2>
        <div class="detail-grid">
          <div class="detail-item"><div class="label">样本 ID</div><div class="value">${valueOrDash(record.canonical_sample_id)}</div></div>
          <div class="detail-item"><div class="label">库 ID</div><div class="value">${valueOrDash(record.library_id)}</div></div>
          <div class="detail-item"><div class="label">实测风险</div><div class="value">${badge(risk.modal_level)} ${formatNumber(risk.score_mean, 2)}</div></div>
          <div class="detail-item"><div class="label">碰撞</div><div class="value">${formatBoolean(risk.collision_observed)}</div></div>
        </div>
        <h3>标签与质量</h3>
        <table class="kv">
          <tr><td>生成器</td><td>${valueOrDash((labels.generators || []).join(", "))}</td></tr>
          <tr><td>目标风险</td><td>${valueOrDash((labels.target_risk_levels || []).join(", "))}</td></tr>
          <tr><td>天气标签</td><td>${valueOrDash((labels.weather_tags || []).join(", "))}</td></tr>
          <tr><td>危险标签</td><td>${valueOrDash((labels.hazard_tags || []).join(", "))}</td></tr>
          <tr><td>质量层级</td><td>${valueOrDash(quality.tier)}</td></tr>
          <tr><td>真实性</td><td>${valueOrDash(quality.realism && quality.realism.status)}</td></tr>
        </table>
        <h3>风险与证据</h3>
        <table class="kv">
          <tr><td>分数范围</td><td>${formatNumber(risk.score_min, 2)} – ${formatNumber(risk.score_max, 2)}</td></tr>
          <tr><td>最小 TTC</td><td>${formatNumber(risk.minimum_ttc_seconds, 3)} s</td></tr>
          <tr><td>最小前车净间距</td><td>${formatNumber(risk.minimum_lead_gap_m, 3)} m</td></tr>
          <tr><td>完成运行</td><td>${valueOrDash(evidence.completed_run_count)} / ${valueOrDash(evidence.expected_run_count)}</td></tr>
          <tr><td>严格验收</td><td>${valueOrDash(evidence.accepted_run_count)}</td></tr>
          <tr><td>验收依据</td><td>${valueOrDash(evidence.verification_basis)}</td></tr>
          <tr><td>证据粒度</td><td>${valueOrDash(evidence.evidence_granularity)}</td></tr>
        </table>
        <h3>场景参数</h3>
        <table class="kv">${objectRows(parameters)}</table>
        <h3>质量标记</h3>
        <div class="flags">${flags.length ? flags.map(flag => `<span class="flag">${escapeHtml(flag)}</span>`).join("") : "<span class=\"subtle\">无</span>"}</div>`;
    }

    async function loadDashboard() {
      const [summaryResponse, scenariosResponse] = await Promise.all([fetch("/api/summary"), fetch("/api/scenarios")]);
      if (!summaryResponse.ok || !scenariosResponse.ok) throw new Error("无法读取场景库接口");
      const summary = await summaryResponse.json();
      const scenarios = await scenariosResponse.json();
      state.rows = scenarios.items || [];
      renderSummary(summary);
      renderRows();
    }

    ["search", "generator", "target", "observed", "quality", "collision"].forEach(id => document.getElementById(id).addEventListener("input", renderRows));
    document.getElementById("reset-button").addEventListener("click", () => {
      ["search", "generator", "target", "observed", "quality", "collision"].forEach(id => document.getElementById(id).value = "");
      state.selected = "";
      renderRows();
      document.getElementById("detail-panel").innerHTML = '<h2>场景详情</h2><div class="detail-empty">点击左侧场景查看参数、风险和运行证据。</div>';
    });
    loadDashboard().catch(error => {
      document.getElementById("match-count").textContent = error.message;
    });
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    dashboard_data = None

    def _send(self, status_code, content_type, payload):
        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code, payload):
        self._send(status_code, "application/json; charset=utf-8", _json_bytes(payload))

    def do_GET(self):
        request_path = urlsplit(self.path).path
        if request_path == "/":
            self._send(200, "text/html; charset=utf-8", HTML_PAGE)
            return
        if request_path == "/api/summary":
            summary = dict(self.dashboard_data["summary"])
            summary["quality_summary"] = self.dashboard_data["quality_summary"]
            self._send_json(200, summary)
            return
        if request_path == "/api/scenarios":
            self._send_json(200, {"count": len(self.dashboard_data["rows"]), "items": self.dashboard_data["rows"]})
            return
        prefix = "/api/scenarios/"
        if request_path.startswith(prefix):
            library_id = unquote(request_path[len(prefix):])
            record = self.dashboard_data["entries"].get(library_id)
            if record is None:
                self._send_json(404, {"error": "未找到场景"})
                return
            self._send_json(200, record)
            return
        self._send_json(404, {"error": "未找到接口"})

    def log_message(self, format_string, *arguments):
        sys.stdout.write(f"[DASHBOARD] {format_string % arguments}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="启动场景库 V1 只读可视化原型")
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
        print(f"[DASHBOARD] 数据加载失败: {error}", file=sys.stderr)
        return 1

    print(f"[DASHBOARD] 场景数: {len(dashboard_data['rows'])}")
    print(f"[DASHBOARD] 数据目录: {dashboard_data['library_dir']}")
    if args.validate_only:
        print("[DASHBOARD] validate-only 完成")
        return 0

    DashboardHandler.dashboard_data = dashboard_data
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"[DASHBOARD] 访问地址: {url}")
    print("[DASHBOARD] 只读模式，按 Ctrl+C 停止")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DASHBOARD] 已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
