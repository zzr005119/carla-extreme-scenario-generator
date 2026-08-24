"""Preflight and explicitly gated ScenarioRunner direct execution.

The command is never executed unless ``--execute`` is supplied.  A dry-run
still parses the XOSC and records the exact command for reproducibility.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_runner_script(root):
    root = Path(root).expanduser().resolve()
    candidates = (root / "scenario_runner.py", root / "scenario_runner" / "scenario_runner.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"找不到 ScenarioRunner 入口: {root}")


def build_command(
    runner_script,
    xosc_path,
    *,
    host="127.0.0.1",
    port=2000,
    traffic_manager_port=8100,
    traffic_manager_seed=None,
    sync=False,
    reload_world=False,
    wait_for_ego=False,
    record=False,
):
    command = [
        sys.executable,
        str(Path(runner_script).resolve()),
        "--openscenario",
        str(Path(xosc_path).resolve()),
        "--host",
        str(host),
        "--port",
        str(int(port)),
        "--trafficManagerPort",
        str(int(traffic_manager_port)),
    ]
    if traffic_manager_seed is not None:
        command.extend(["--trafficManagerSeed", str(int(traffic_manager_seed))])
    if sync:
        command.append("--sync")
    if reload_world:
        command.append("--reloadWorld")
    if wait_for_ego:
        command.append("--waitForEgo")
    if record:
        command.extend(["--record", "records" if record is True else str(record)])
    return command


def preflight(
    runner_root,
    xosc_path,
    *,
    host="127.0.0.1",
    port=2000,
    traffic_manager_port=8100,
    traffic_manager_seed=None,
    sync=False,
    reload_world=False,
    wait_for_ego=False,
    record=False,
):
    xosc_path = Path(xosc_path).expanduser().resolve()
    if not xosc_path.is_file():
        raise FileNotFoundError(f"XOSC 不存在: {xosc_path}")
    root = ET.parse(xosc_path).getroot()
    if root.tag != "OpenSCENARIO":
        raise ValueError(f"XOSC 根节点必须是 OpenSCENARIO，实际为 {root.tag}")
    runner_script = resolve_runner_script(runner_root)
    command = build_command(
        runner_script,
        xosc_path,
        host=host,
        port=port,
        traffic_manager_port=traffic_manager_port,
        traffic_manager_seed=traffic_manager_seed,
        sync=sync,
        reload_world=reload_world,
        wait_for_ego=wait_for_ego,
        record=record,
    )
    return {
        "format": "scenario_runner_direct_execution_plan_v1",
        "runner_script": str(runner_script),
        "xosc_path": str(xosc_path),
        "carla_host": str(host),
        "carla_port": int(port),
        "traffic_manager_port": int(traffic_manager_port),
        "traffic_manager_seed": traffic_manager_seed,
        "sync": bool(sync),
        "reload_world": bool(reload_world),
        "wait_for_ego": bool(wait_for_ego),
        "command": command,
        "execution_started": False,
        "status": "ready_for_explicit_execute",
        "evidence_kind": "scenario_runner_preflight",
    }


def run(plan, *, output_path=None, execute=False, timeout=600):
    result = dict(plan)
    if not execute:
        result["status"] = "dry_run"
    else:
        completed = subprocess.run(
            plan["command"], cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=int(timeout), check=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"},
        )
        result.update({
            "execution_started": True,
            "returncode": completed.returncode,
            "status": "completed" if completed.returncode == 0 else "failed",
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "evidence_kind": "scenario_runner_runtime" if completed.returncode == 0 else "scenario_runner_runtime_failure",
        })
    if output_path:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        result["manifest_path"] = str(path)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="ScenarioRunner 直执行预检与显式运行入口")
    parser.add_argument("--runner-root", required=True)
    parser.add_argument("--xosc", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--traffic-manager-port", type=int, default=8100)
    parser.add_argument("--traffic-manager-seed", type=int, default=None)
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--reload-world", action="store_true")
    parser.add_argument("--wait-for-ego", action="store_true")
    parser.add_argument(
        "--record",
        nargs="?",
        const="records",
        default=False,
        help="启用 CARLA recorder，并将记录写入 ScenarioRunner 根目录下的目录",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true", help="显式启动 ScenarioRunner；默认仅预检")
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main():
    args = parse_args()
    plan = preflight(
        args.runner_root,
        args.xosc,
        host=args.host,
        port=args.port,
        traffic_manager_port=args.traffic_manager_port,
        traffic_manager_seed=args.traffic_manager_seed,
        sync=args.sync,
        reload_world=args.reload_world,
        wait_for_ego=args.wait_for_ego,
        record=args.record,
    )
    result = run(plan, output_path=args.output, execute=args.execute, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"dry_run", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
