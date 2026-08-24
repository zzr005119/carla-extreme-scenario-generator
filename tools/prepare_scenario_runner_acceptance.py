"""Prepare a full CARLA acceptance config for an OpenSCENARIO sample."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTE_PROFILE = PROJECT_ROOT / "configs" / "route_control_profiles" / "waypoint_follower_v1.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_config(xosc_path, carla_config_path, output_dir, route_profile_path, traffic_manager_port):
    xosc_path = Path(xosc_path).expanduser().resolve()
    carla_config_path = Path(carla_config_path).expanduser().resolve()
    route_profile_path = Path(route_profile_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    root = ET.parse(xosc_path).getroot()
    if root.tag != "OpenSCENARIO":
        raise ValueError("XOSC root must be OpenSCENARIO")
    logic_file = root.find("./RoadNetwork/LogicFile")
    if logic_file is None or not logic_file.get("filepath"):
        raise ValueError("XOSC must declare RoadNetwork/LogicFile")
    config = copy.deepcopy(load_json(carla_config_path))
    for section in ("scenario", "traffic", "sensors", "risk_evaluation", "output"):
        if section not in config:
            raise ValueError(f"CARLA config missing section: {section}")
    profile = load_json(route_profile_path)
    route = profile["route"]
    config["scenario"]["traffic_manager_port"] = int(traffic_manager_port)
    config["traffic"].update(
        {
            "route_lock_enabled": True,
            "route_control_mode": "waypoint_follower",
            "route_length_m": float(route["route_length_m"]),
            "route_step_m": float(route["route_step_m"]),
            "route_deviation_tolerance_m": float(route["route_deviation_tolerance_m"]),
            "route_controller": copy.deepcopy(profile["controller"]),
        }
    )
    # Full sensor acceptance deliberately enables all camera modalities.
    for name in ("rgb", "depth", "semantic"):
        config["sensors"][name]["enabled"] = True
    config["sensors"]["collision"]["enabled"] = True
    config["output"] = dict(config["output"])
    config["output"]["root"] = str(output_dir / "carla_runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "acceptance_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "format": "scenario_runner_carla_full_acceptance_v1",
        "status": "prepared",
        "sample_id": config["scenario"].get("name"),
        "xosc": {
            "path": str(xosc_path),
            "sha256": sha256(xosc_path),
            "map": logic_file.get("filepath"),
        },
        "source_carla_config": {
            "path": str(carla_config_path),
            "sha256": sha256(carla_config_path),
        },
        "acceptance_config": {
            "path": str(config_path),
            "sha256": sha256(config_path),
        },
        "route_profile": {
            "path": str(route_profile_path),
            "profile_id": profile.get("profile_id"),
            "sha256": sha256(route_profile_path),
        },
        "traffic_manager_port": int(traffic_manager_port),
        "expected_run_root": str(config["output"]["root"]),
        "acceptance_requirements": {
            "carla_version": "0.9.16",
            "sensor_status": "completed",
            "minimum_rgb_frames": 100,
            "minimum_depth_frames": 100,
            "minimum_semantic_frames": 100,
            "server_status": "healthy",
            "route_control_mode": "waypoint_follower",
            "minimum_route_both_on_rate": 1.0,
            "maximum_route_deviation_m": float(route["route_deviation_tolerance_m"]),
            "risk_method": "heuristic_v2",
        },
        "direct_execution": None,
        "metadata_path": None,
        "result_path": str(output_dir / "acceptance_result.json"),
    }
    manifest_path = output_dir / "acceptance_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path, config_path


def parse_args():
    parser = argparse.ArgumentParser(description="准备 ScenarioRunner 对应的完整 CARLA 验收配置")
    parser.add_argument("--xosc", required=True)
    parser.add_argument("--carla-config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--route-profile", default=str(DEFAULT_ROUTE_PROFILE))
    parser.add_argument("--traffic-manager-port", type=int, default=8100)
    return parser.parse_args()


def main():
    args = parse_args()
    manifest_path, config_path = prepare_config(
        args.xosc,
        args.carla_config,
        args.output_dir,
        args.route_profile,
        args.traffic_manager_port,
    )
    print(f"[PREPARED] manifest={manifest_path}")
    print(f"[PREPARED] config={config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
