"""Build small, auditable SVG and sensor-preview artifacts for Web task results."""

from __future__ import annotations

import csv
import html
import json
import math
import re
import shutil
from pathlib import Path


REPLAY_CHANNELS = ("rgb", "depth", "semantic")
REPLAY_FRAME_NAME = re.compile(r"frame_\d{6,}\.(?:png|jpg|jpeg)", re.IGNORECASE)
REPLAY_NUMERIC_FIELDS = (
    "elapsed_seconds", "ego_speed_kmh", "lead_speed_kmh", "lead_gap_distance_m",
    "pedestrian_distance_m", "ttc_seconds", "ego_control_brake", "collision_count",
)


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _series(rows, field):
    values = []
    for index, row in enumerate(rows):
        x = _number(row.get("elapsed_seconds"))
        y = _number(row.get(field))
        if x is not None and y is not None:
            values.append((x, y))
    return values


def _polyline(values, left, top, width, height, x_min, x_max, y_min, y_max, color):
    if not values:
        return ""
    x_span = max(x_max - x_min, 1e-9)
    y_span = max(y_max - y_min, 1e-9)
    points = []
    for x, y in values:
        px = left + (x - x_min) / x_span * width
        py = top + height - (y - y_min) / y_span * height
        points.append(f"{px:.1f},{py:.1f}")
    return f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(points)}" />'


def _panel(rows, title, fields, left, top, width, height, y_label):
    all_values = [point[1] for field in fields for point in _series(rows, field[0])]
    if not all_values:
        return f'<text x="{left}" y="{top + 22}" class="empty">{html.escape(title)}：暂无可绘制字段</text>'
    x_values = [point[0] for field in fields for point in _series(rows, field[0])]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(0.0, min(all_values)), max(all_values)
    if math.isclose(y_min, y_max):
        y_max = y_min + 1.0
    margin = max((y_max - y_min) * 0.08, 0.1)
    y_min -= margin
    y_max += margin
    parts = [
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" class="plot" />',
        f'<text x="{left}" y="{top - 12}" class="title">{html.escape(title)}</text>',
        f'<text x="{left - 8}" y="{top + 12}" text-anchor="end" class="axis">{y_max:.1f}</text>',
        f'<text x="{left - 8}" y="{top + height}" text-anchor="end" class="axis">{y_min:.1f}</text>',
        f'<text x="{left + width}" y="{top + height + 28}" text-anchor="end" class="axis">{x_max:.1f}s</text>',
        f'<text x="{left}" y="{top + height + 28}" class="axis">{x_min:.1f}s</text>',
    ]
    for index, (field, label, color) in enumerate(fields):
        values = _series(rows, field)
        parts.append(_polyline(values, left, top, width, height, x_min, x_max, y_min, y_max, color))
        legend_x = left + index * 170
        parts.append(f'<line x1="{legend_x}" y1="{top + height + 48}" x2="{legend_x + 22}" y2="{top + height + 48}" stroke="{color}" stroke-width="3" />')
        parts.append(f'<text x="{legend_x + 28}" y="{top + height + 52}" class="legend">{html.escape(label)}</text>')
    parts.append(f'<text x="{left - 52}" y="{top + height / 2}" transform="rotate(-90 {left - 52} {top + height / 2})" class="axis">{html.escape(y_label)}</text>')
    return "".join(parts)


def build_svg(output_path, rows, risk=None, *, title="CARLA 运行状态与风险时间线"):
    rows = list(rows or [])
    if not rows:
        raise ValueError("遥测为空，无法生成可视化")
    width, height = 1020, 700
    risk = risk or {}
    risk_text = f"风险：{risk.get('level', 'unknown')} / {risk.get('score', '—')} · method={risk.get('method', '—')}"
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">CARLA 运行状态与风险时间线</title>',
        f'<desc id="desc">{html.escape(risk_text)}</desc>',
        '<style>.bg{fill:#f8fafc}.plot{fill:#fff;stroke:#cbd5e1}.title{font:700 18px Microsoft YaHei, sans-serif;fill:#172033}.axis,.legend{font:12px Microsoft YaHei, sans-serif;fill:#64748b}.empty{font:14px Microsoft YaHei, sans-serif;fill:#b91c1c}.headline{font:700 22px Microsoft YaHei, sans-serif;fill:#132243}.subtitle{font:13px Microsoft YaHei, sans-serif;fill:#475569}</style>',
        f'<rect width="{width}" height="{height}" class="bg"/>',
        f'<text x="30" y="36" class="headline">{html.escape(title)}</text>',
        f'<text x="30" y="60" class="subtitle">{html.escape(risk_text)} · 行数={len(rows)}</text>',
    ]
    body.append(_panel(rows, "速度与前车状态", [("ego_speed_kmh", "主车速度 km/h", "#2563eb"), ("lead_speed_kmh", "前车速度 km/h", "#0f766e")], 95, 105, 850, 190, "速度"))
    body.append(_panel(rows, "安全时间与间距", [("ttc_seconds", "TTC s", "#dc2626"), ("lead_gap_distance_m", "前车净间距 m", "#d97706"), ("pedestrian_distance_m", "行人距离 m", "#7c3aed")], 95, 405, 850, 190, "数值"))
    body.append('</svg>')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(body), encoding="utf-8")
    return output_path


def read_telemetry(path):
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def build_replay_manifest(run_dir):
    run_dir = Path(run_dir)
    telemetry_path = run_dir / "telemetry.csv"
    if not telemetry_path.is_file():
        return None
    rows = read_telemetry(telemetry_path)
    if not rows:
        return None
    channels = {}
    for channel in REPLAY_CHANNELS:
        folder = run_dir / channel
        if not folder.is_dir():
            continue
        frames = sorted(
            item for item in folder.iterdir()
            if item.is_file() and REPLAY_FRAME_NAME.fullmatch(item.name)
            and item.resolve().parent == folder.resolve()
        )
        if frames:
            channels[channel] = [
                {
                    "name": frame.name,
                    "sample_index": round(index * (len(rows) - 1) / max(len(frames) - 1, 1)),
                }
                for index, frame in enumerate(frames)
            ]
    if not channels:
        return None
    telemetry = [
        {
            **{field: _number(row.get(field)) for field in REPLAY_NUMERIC_FIELDS},
            "lead_braking": str(row.get("lead_braking", "")).lower() in {"true", "1"},
            "pedestrian_active": str(row.get("pedestrian_active", "")).lower() in {"true", "1"},
        }
        for row in rows
    ]
    metadata_path = run_dir / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    events = [
        {"type": str(event.get("type", "")), "elapsed_seconds": _number(event.get("elapsed_seconds"))}
        for event in metadata.get("events", [])
        if isinstance(event, dict) and _number(event.get("elapsed_seconds")) is not None
    ]
    return {
        "channels": channels,
        "telemetry": telemetry,
        "events": events,
        "alignment": "frame_order_estimate",
    }


def resolve_replay_frame(run_dir, channel, filename, *, max_bytes=8 * 1024 * 1024):
    if channel not in REPLAY_CHANNELS or not REPLAY_FRAME_NAME.fullmatch(filename):
        raise ValueError("传感器帧路径无效")
    folder = (Path(run_dir) / channel).resolve()
    frame = (folder / filename).resolve()
    if frame.parent != folder or not frame.is_file() or frame.stat().st_size > max_bytes:
        raise ValueError("传感器帧不存在或超出大小限制")
    return frame


def copy_sensor_preview(run_dir, output_path, *, max_bytes=4 * 1024 * 1024):
    run_dir = Path(run_dir)
    candidates = []
    for folder in ("rgb", "depth", "semantic"):
        directory = run_dir / folder
        if directory.is_dir():
            candidates.extend(sorted(item for item in directory.rglob("*") if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg"}))
    if not candidates:
        return None
    source = candidates[0]
    if source.stat().st_size > max_bytes:
        return None
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output_path)
    return output_path


def build_run_visualization(output_dir, run_dir, rows, risk=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chart = build_svg(output_dir / "run_visualization.svg", rows, risk)
    preview = copy_sensor_preview(run_dir, output_dir / "sensor_preview.png") if run_dir else None
    return {
        "chart_name": chart.name,
        "sensor_preview_name": preview.name if preview else None,
        "plot_basis": "elapsed_seconds with speed, TTC, gap and pedestrian-distance series",
        "row_count": len(rows),
        "sensor_preview_source": str(preview) if preview else None,
    }
