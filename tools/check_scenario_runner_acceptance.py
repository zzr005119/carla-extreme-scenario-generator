"""Check full CARLA acceptance evidence produced from a prepared config."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


RISK_LEVELS = {"low", "medium", "high", "critical"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def newest_metadata(root):
    root = Path(root)
    candidates = list(root.rglob("metadata.json")) if root.is_dir() else []
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def check_acceptance(manifest_path, metadata_path=None):
    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = load_json(manifest_path)
    if manifest.get("format") != "scenario_runner_carla_full_acceptance_v1":
        raise ValueError("unsupported acceptance manifest format")
    metadata_path = Path(metadata_path).expanduser().resolve() if metadata_path else newest_metadata(manifest["expected_run_root"])
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if metadata_path is None:
        add("metadata_present", False, "metadata.json not found")
        result = {"format": "scenario_runner_carla_full_acceptance_result_v1", "status": "failed", "manifest": str(manifest_path), "metadata_path": None, "checks": checks}
        return result
    metadata = load_json(metadata_path)
    required = manifest["acceptance_requirements"]
    versions = metadata.get("carla_versions") or {}
    result = metadata.get("result") or {}
    sensor = metadata.get("sensor_pipeline") or {}
    sensors = sensor.get("sensors") or {}
    server = metadata.get("server_health") or {}
    collision = metadata.get("collision_sensor") or {}
    route = metadata.get("route_control") or {}
    risk = result.get("risk_evaluation") or {}
    frames = metadata.get("frames") or {}

    add("metadata_present", True, str(metadata_path))
    add("scenario_completed", result.get("status") == "completed", result.get("status"))
    add("carla_versions", versions.get("client") == required["carla_version"] and versions.get("server") == required["carla_version"] and versions.get("match") is True, versions)
    add("sensor_pipeline", sensor.get("status") == required["sensor_status"], sensor.get("status"))
    for name in ("rgb", "depth", "semantic"):
        minimum = int(required[f"minimum_{name}_frames"])
        state = sensors.get(name) or {}
        saved = int(frames.get(name, state.get("saved", 0) or 0))
        add(f"sensor_{name}", saved >= minimum and state.get("complete") is True and int(state.get("failed", 0)) == 0, {"saved": saved, "minimum": minimum, "state": state})
    add(
        "sensor_collision",
        collision.get("enabled") is True
        and collision.get("status") == required["collision_sensor_status"]
        and collision.get("complete") is True
        and int(collision.get("event_count", -1))
        == int(result.get("collision_count", -2)),
        collision,
    )
    add("server_health", server.get("status") == required["server_status"], server.get("status"))
    add("route_control", route.get("enabled") is True and route.get("status") == "completed" and route.get("mode") == required["route_control_mode"], {"enabled": route.get("enabled"), "status": route.get("status"), "mode": route.get("mode")})
    both_rate = float(route.get("both_on_route_rate", 0.0) or 0.0)
    max_ego = route.get("maximum_ego_deviation_m")
    max_lead = route.get("maximum_lead_deviation_m")
    tolerance = float(required["maximum_route_deviation_m"])
    add("route_quality", both_rate >= float(required["minimum_route_both_on_rate"]) and max_ego is not None and max_lead is not None and float(max_ego) <= tolerance and float(max_lead) <= tolerance, {"both_on_route_rate": both_rate, "maximum_ego_deviation_m": max_ego, "maximum_lead_deviation_m": max_lead, "tolerance_m": tolerance})
    add("risk_evaluation", risk.get("method") == required["risk_method"] and risk.get("level") in RISK_LEVELS and math.isfinite(float(risk.get("score"))), {"method": risk.get("method"), "level": risk.get("level"), "score": risk.get("score")})
    add("cleanup", (metadata.get("cleanup") or {}).get("status") == "completed", metadata.get("cleanup"))
    passed = all(item["passed"] for item in checks)
    output = {
        "format": "scenario_runner_carla_full_acceptance_result_v1",
        "status": "passed" if passed else "failed",
        "manifest": str(manifest_path),
        "metadata_path": str(metadata_path),
        "sample_id": manifest.get("sample_id"),
        "risk": {"method": risk.get("method"), "level": risk.get("level"), "score": risk.get("score"), "collision_count": result.get("collision_count")},
        "sensor_frames": {name: frames.get(name) for name in ("rgb", "depth", "semantic")},
        "route": {"both_on_route_rate": both_rate, "maximum_ego_deviation_m": max_ego, "maximum_lead_deviation_m": max_lead},
        "checks": checks,
    }
    return output


def parse_args():
    parser = argparse.ArgumentParser(description="检查 ScenarioRunner 伴随 CARLA 完整验收证据")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metadata")
    return parser.parse_args()


def main():
    args = parse_args()
    result = check_acceptance(args.manifest, args.metadata)
    output_path = Path(args.manifest).expanduser().resolve().with_name("acceptance_result.json")
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
