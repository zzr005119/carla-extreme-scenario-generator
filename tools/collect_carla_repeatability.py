"""收集 CVAE 多种子复测结果并生成重复性分析。"""

import argparse
import csv
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.analyze_carla_repeatability import write_analysis  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="收集 CARLA 多种子复测结果")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def matching_metadata(run_root, expected_seed):
    if not os.path.isdir(run_root):
        return None
    matches = []
    for root, _, files in os.walk(run_root):
        if "metadata.json" not in files:
            continue
        path = os.path.join(root, "metadata.json")
        try:
            metadata = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        actual_seed = (metadata.get("simulation") or {}).get(
            "traffic_manager_seed"
        )
        if actual_seed is not None and int(actual_seed) == int(expected_seed):
            matches.append((os.path.getmtime(path), path, metadata))
    if not matches:
        return None
    _, path, metadata = max(matches, key=lambda item: item[0])
    return path, metadata


def collect_row(
    run,
    route_lock_required=False,
    acceptance_requirements=None,
):
    acceptance_requirements = acceptance_requirements or {}
    match = matching_metadata(
        run["expected_run_root"],
        run["traffic_manager_seed"],
    )
    base = {
        "run_id": run["run_id"],
        "sample_id": run["sample_id"],
        "target_risk_level": run["target_risk_level"],
        "traffic_manager_seed": int(run["traffic_manager_seed"]),
        "repeat_round": int(run["repeat_round"]),
        "source": run["source"],
    }
    if match is None:
        return {
            **base,
            "status": "missing",
            "acceptance_status": "missing",
            "acceptance_failures": "metadata_missing",
            "runtime_verified": False,
            "observed_risk_level": None,
            "risk_score": None,
            "target_match": None,
            "collision_count": None,
            "minimum_ttc_seconds": None,
            "minimum_lead_gap_m": None,
            "minimum_pedestrian_distance_m": None,
            "sensor_status": None,
            "server_status": None,
            "route_status": None,
            "route_ego_on_route_rate": None,
            "route_lead_on_route_rate": None,
            "route_both_on_route_rate": None,
            "route_maximum_ego_deviation_m": None,
            "route_maximum_lead_deviation_m": None,
            "route_verified": None,
            "rgb_frames": None,
            "run_dir": None,
            "metadata_path": None,
        }

    metadata_path, metadata = match
    result = metadata.get("result") or {}
    risk = result.get("risk_evaluation") or {}
    route_control = metadata.get("route_control") or {}
    sensor_status = (metadata.get("sensor_pipeline") or {}).get("status")
    server_status = (metadata.get("server_health") or {}).get("status")
    rgb_frames = int((metadata.get("frames") or {}).get("rgb") or 0)
    minimum_route_rate = float(
        acceptance_requirements.get("minimum_route_both_on_rate", 0.999)
    )
    maximum_route_deviation = acceptance_requirements.get(
        "maximum_route_deviation_m"
    )
    expected_route_mode = acceptance_requirements.get("route_control_mode")
    ego_deviation = route_control.get("maximum_ego_deviation_m")
    lead_deviation = route_control.get("maximum_lead_deviation_m")
    route_deviation_verified = (
        maximum_route_deviation is None
        or (
            ego_deviation is not None
            and lead_deviation is not None
            and float(ego_deviation) <= float(maximum_route_deviation)
            and float(lead_deviation) <= float(maximum_route_deviation)
        )
    )
    route_verified = (
        route_control.get("enabled") is True
        and route_control.get("status") == "completed"
        and float(route_control.get("both_on_route_rate") or 0.0)
        >= minimum_route_rate
        and route_control.get("auto_lane_change_enabled") is False
        and (
            expected_route_mode is None
            or route_control.get("mode") == expected_route_mode
        )
        and route_deviation_verified
        if route_lock_required
        else None
    )
    completed = (
        result.get("status") == "completed"
        and risk.get("method") is not None
        and risk.get("score") is not None
        and risk.get("level") in ("low", "medium", "high", "critical")
    )
    required_sensor_status = acceptance_requirements.get("sensor_status")
    required_server_status = acceptance_requirements.get("server_status")
    minimum_rgb_frames = int(
        acceptance_requirements.get("minimum_rgb_frames", 0)
    )
    runtime_verified = (
        completed
        and (
            required_sensor_status is None
            or sensor_status == required_sensor_status
        )
        and (
            required_server_status is None
            or server_status == required_server_status
        )
        and rgb_frames >= minimum_rgb_frames
    )
    observed_level = risk.get("level") if completed else None
    accepted = runtime_verified and (
        not route_lock_required or route_verified
    )
    acceptance_failures = []
    if not completed:
        acceptance_failures.append("simulation_incomplete")
    if required_sensor_status is not None and sensor_status != required_sensor_status:
        acceptance_failures.append("sensor_status")
    if required_server_status is not None and server_status != required_server_status:
        acceptance_failures.append("server_status")
    if rgb_frames < minimum_rgb_frames:
        acceptance_failures.append("rgb_frames")
    if route_lock_required and not route_verified:
        acceptance_failures.append("route_verification")
    return {
        **base,
        "status": "completed" if completed else "failed",
        "acceptance_status": "completed" if accepted else "failed",
        "acceptance_failures": ";".join(acceptance_failures),
        "runtime_verified": runtime_verified,
        "observed_risk_level": observed_level,
        "risk_score": float(risk["score"]) if completed else None,
        "target_match": (
            observed_level == run["target_risk_level"] if completed else None
        ),
        "collision_count": int(result.get("collision_count", 0)),
        "minimum_ttc_seconds": result.get("minimum_ttc_seconds"),
        "minimum_lead_gap_m": result.get("minimum_lead_gap_m"),
        "minimum_pedestrian_distance_m": result.get(
            "minimum_pedestrian_distance_m"
        ),
        "sensor_status": sensor_status,
        "server_status": server_status,
        "route_status": route_control.get("status"),
        "route_ego_on_route_rate": route_control.get("ego_on_route_rate"),
        "route_lead_on_route_rate": route_control.get("lead_on_route_rate"),
        "route_both_on_route_rate": route_control.get("both_on_route_rate"),
        "route_maximum_ego_deviation_m": route_control.get(
            "maximum_ego_deviation_m"
        ),
        "route_maximum_lead_deviation_m": route_control.get(
            "maximum_lead_deviation_m"
        ),
        "route_verified": route_verified,
        "rgb_frames": rgb_frames,
        "run_dir": os.path.dirname(metadata_path),
        "metadata_path": metadata_path,
    }


def main():
    args = parse_args()
    manifest_path = os.path.abspath(args.manifest)
    output_dir = os.path.dirname(manifest_path)
    manifest = load_json(manifest_path)
    supported_formats = {
        "cvae_carla_repeatability_v1",
        "cvae_carla_route_repeatability_v2",
        "cvae_carla_route_repeatability_v3",
        "cvae_carla_route_repeatability_v4",
    }
    if manifest.get("format") not in supported_formats:
        raise ValueError("不支持的复测清单格式")
    route_lock_required = bool(manifest.get("route_lock_required", False))
    acceptance_requirements = manifest.get("acceptance_requirements") or {}
    rows = [
        collect_row(
            run,
            route_lock_required=route_lock_required,
            acceptance_requirements=acceptance_requirements,
        )
        for run in manifest["runs"]
    ]
    rows.sort(key=lambda row: (row["sample_id"], row["traffic_manager_seed"]))

    fields = tuple(rows[0])
    csv_path = os.path.join(output_dir, "run_results.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    jsonl_path = os.path.join(output_dir, "run_results.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    analysis, summary_path, scenario_csv, seed_csv, report_path = write_analysis(
        rows,
        manifest["traffic_seeds"],
        output_dir,
        route_lock_required=route_lock_required,
    )
    print(
        f"[COLLECT] completed={analysis['completed_runs']} | "
        f"failed={analysis['failed_runs']} | missing={analysis['missing_runs']}"
    )
    print(
        f"[COLLECT] accepted={analysis['accepted_runs']} | "
        f"acceptance_failed={analysis['acceptance_failed_runs']} | "
        f"route_verified={analysis['route_verified_runs']}"
    )
    print(f"[COLLECT] 运行明细: {csv_path}")
    print(f"[COLLECT] 场景统计: {scenario_csv}")
    print(f"[COLLECT] 种子统计: {seed_csv}")
    print(f"[COLLECT] 分析报告: {report_path}")
    print(f"[COLLECT] 汇总: {summary_path}")
    if analysis["missing_runs"] and not args.allow_missing:
        return 1
    return 0 if analysis["acceptance_failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
