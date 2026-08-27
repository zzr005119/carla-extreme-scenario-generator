"""Run one existing scenario record with the current CARLA runtime contract."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_RUNNER = PROJECT_ROOT / "scenes" / "scene_04_parameterized.py"
DEFAULT_BASE_CONFIG = PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"
DEFAULT_ROUTE_PROFILE = (
    PROJECT_ROOT / "configs" / "route_control_profiles" / "waypoint_follower_v1.json"
)

sys.path.insert(0, str(PROJECT_ROOT))
from tools.run_adversarial_episode import (  # noqa: E402
    _safe_name,
    build_carla_config,
    load_record,
)
from tools.collect_carla_repeatability import collect_row  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="用当前版本回归一个既有 CARLA 场景记录")
    parser.add_argument("--record", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--traffic-manager-port", type=int, default=8100)
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args()


def run_record(record_path, output_root, name, traffic_manager_port, timeout):
    record_path = Path(record_path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    record = load_record(str(record_path))
    base_config = load_json(str(DEFAULT_BASE_CONFIG))
    route_profile = load_json(str(DEFAULT_ROUTE_PROFILE))
    safe_name = _safe_name(name)
    run_root = output_root / safe_name
    config = build_carla_config(
        record,
        base_config,
        route_profile,
        safe_name,
        run_root,
        traffic_manager_port,
    )
    config_path = output_root / f"{safe_name}.carla.json"
    record_copy = output_root / f"{safe_name}.scenario_record.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_copy.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    command = [
        sys.executable,
        "-u",
        str(SCENE_RUNNER),
        "--config",
        str(config_path),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=int(timeout),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"},
        check=False,
    )
    log_path = output_root / f"{safe_name}.log"
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    metadata_path = None
    for line in completed.stdout.splitlines():
        if line.startswith("[DONE] 元数据:"):
            metadata_path = Path(line.split(": ", 1)[1].strip())
            break
    metadata = {}
    if metadata_path and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    route = metadata.get("route_control") or {}
    result = metadata.get("result") or {}
    acceptance = collect_row(
        {
            "run_id": safe_name,
            "sample_id": record["sample_id"],
            "target_risk_level": record["conditions"]["target_risk_level"],
            "traffic_manager_seed": record["scenario"]["traffic_manager_seed"],
            "repeat_round": 1,
            "expected_run_root": str(run_root),
        },
        route_lock_required=True,
        acceptance_requirements={
            "sensor_status": "completed",
            "server_status": "healthy",
            "minimum_rgb_frames": 100,
            "route_control_mode": "waypoint_follower",
            "minimum_route_both_on_rate": 1.0,
            "maximum_route_deviation_m": 3.0,
            "route_verification_scope": "pre_collision_for_collision_runs",
            "carla_version": "0.9.16",
        },
    )
    summary = {
        "format": "carla_record_recheck_v1",
        "status": "passed"
        if completed.returncode == 0
        and result.get("status") == "completed"
        and acceptance.get("acceptance_status") == "completed"
        else "failed",
        "sample_id": record["sample_id"],
        "record_path": str(record_path),
        "config_path": str(config_path),
        "metadata_path": str(metadata_path) if metadata_path else None,
        "process_returncode": completed.returncode,
        "result_status": result.get("status"),
        "acceptance_status": acceptance.get("acceptance_status"),
        "acceptance_failures": acceptance.get("acceptance_failures"),
        "collision_count": result.get("collision_count"),
        "collision_counts": result.get("collision_counts"),
        "first_collision_elapsed_seconds": result.get("first_collision_elapsed_seconds"),
        "route_status": route.get("status"),
        "route_both_on_route_rate": route.get("both_on_route_rate"),
        "route_maximum_ego_deviation_m": route.get("maximum_ego_deviation_m"),
        "route_maximum_lead_deviation_m": route.get("maximum_lead_deviation_m"),
        "lead_stop_lock": route.get("lead_stop_lock"),
        "collision_sensor": metadata.get("collision_sensor"),
        "server_health": metadata.get("server_health"),
    }
    summary_path = output_root / f"{safe_name}.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


def main():
    args = parse_args()
    return run_record(
        args.record,
        args.output_root,
        args.name,
        args.traffic_manager_port,
        args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
