# -*- coding: utf-8 -*-
"""场景04：由 JSON 配置驱动的多危险、多传感器 CARLA 场景。"""

import argparse
import json
import math
import os
import sys
import threading
import time
from datetime import datetime

import carla
import numpy as np
from PIL import Image


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.risk_metrics import (  # noqa: E402
    calculate_ttc,
    evaluate_telemetry_risk,
    vehicle_speed_kmh,
    write_telemetry_csv,
)
from core.sensor_pipeline import SensorWritePipeline  # noqa: E402


DEFAULT_CONFIG = os.path.join(
    SCRIPT_DIR,
    "..",
    "configs",
    "multi_hazard_rainy_night.json",
)


def parse_args():
    parser = argparse.ArgumentParser(description="运行配置驱动的 CARLA 极端场景")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="场景 JSON 配置文件路径",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅校验配置，不连接 CARLA",
    )
    return parser.parse_args()


def load_config(config_path):
    absolute_path = os.path.abspath(config_path)
    with open(absolute_path, "r", encoding="utf-8") as file:
        config = json.load(file)
    validate_config(config)
    return absolute_path, config


def validate_config(config):
    required_sections = {
        "scenario",
        "weather",
        "traffic",
        "ego_vehicle",
        "lead_vehicle",
        "pedestrian",
        "sensors",
        "risk_evaluation",
        "output",
    }
    missing = sorted(required_sections - set(config))
    if missing:
        raise ValueError(f"配置缺少顶层字段: {', '.join(missing)}")

    duration = float(config["scenario"]["duration_seconds"])
    if duration <= 0:
        raise ValueError("scenario.duration_seconds 必须大于 0")
    if not str(config["scenario"]["name"]).strip():
        raise ValueError("scenario.name 不能为空")

    synchronous_mode = bool(config["scenario"].get("synchronous_mode", False))
    fixed_delta_seconds = float(
        config["scenario"].get("fixed_delta_seconds", 0.05)
    )
    if synchronous_mode and fixed_delta_seconds <= 0:
        raise ValueError("同步模式下 scenario.fixed_delta_seconds 必须大于 0")
    traffic_manager_seed = int(
        config["scenario"].get("traffic_manager_seed", 0)
    )
    if traffic_manager_seed < 0:
        raise ValueError("scenario.traffic_manager_seed 不能小于 0")

    for section, field in [
        ("lead_vehicle", "brake_trigger_seconds"),
        ("pedestrian", "trigger_seconds"),
    ]:
        trigger_time = float(config[section][field])
        if not 0 <= trigger_time <= duration:
            raise ValueError(f"{section}.{field} 必须位于场景运行时间内")

    camera = config["sensors"]["camera"]
    if int(camera["width"]) <= 0 or int(camera["height"]) <= 0:
        raise ValueError("相机分辨率必须为正整数")
    sensor_tick = float(camera["sensor_tick"])
    if sensor_tick < 0:
        raise ValueError("sensors.camera.sensor_tick 不能小于 0")
    if synchronous_mode and sensor_tick > 0:
        tick_ratio = sensor_tick / fixed_delta_seconds
        if not math.isclose(tick_ratio, round(tick_ratio), abs_tol=1e-6):
            raise ValueError(
                "同步模式下 sensors.camera.sensor_tick 必须是固定步长的整数倍"
            )
    if int(camera.get("writer_workers", 2)) <= 0:
        raise ValueError("sensors.camera.writer_workers 必须大于 0")
    if int(camera.get("writer_queue_size", 16)) <= 0:
        raise ValueError("sensors.camera.writer_queue_size 必须大于 0")
    if float(camera.get("frame_wait_timeout_seconds", 30.0)) <= 0:
        raise ValueError("sensors.camera.frame_wait_timeout_seconds 必须大于 0")
    if float(camera.get("flush_timeout_seconds", 120.0)) <= 0:
        raise ValueError("sensors.camera.flush_timeout_seconds 必须大于 0")
    if float(config["sensors"]["depth"]["visualization_max_distance_m"]) <= 0:
        raise ValueError("深度图最大可视距离必须大于 0")

    pedestrian_speed = float(config["pedestrian"]["speed_mps"])
    if pedestrian_speed <= 0:
        raise ValueError("pedestrian.speed_mps 必须大于 0")

    brake_intensity = float(config["lead_vehicle"]["brake_intensity"])
    if not 0 <= brake_intensity <= 1:
        raise ValueError("lead_vehicle.brake_intensity 必须位于 0 到 1")

    ignore_lights = float(config["traffic"]["ignore_lights_percentage"])
    if not 0 <= ignore_lights <= 100:
        raise ValueError("traffic.ignore_lights_percentage 必须位于 0 到 100")

    camera_names = ("rgb", "depth", "semantic")
    if not any(config["sensors"][name]["enabled"] for name in camera_names):
        raise ValueError("RGB、Depth、Semantic 至少启用一个")

    risk_config = config["risk_evaluation"]
    risk_thresholds = (
        ("ttc", "critical_seconds", "safe_seconds"),
        ("lead_distance", "critical_m", "safe_m"),
        ("pedestrian_distance", "critical_m", "safe_m"),
    )
    for section, critical_key, safe_key in risk_thresholds:
        critical_value = float(risk_config[section][critical_key])
        safe_value = float(risk_config[section][safe_key])
        if critical_value < 0 or safe_value <= critical_value:
            raise ValueError(
                f"risk_evaluation.{section} 要求 0 <= critical < safe"
            )
    if float(risk_config["vehicle_distance_buffer_m"]) < 0:
        raise ValueError("risk_evaluation.vehicle_distance_buffer_m 不能小于 0")
    risk_method = risk_config.get("method", "heuristic_v1")
    if risk_method not in {"heuristic_v1", "heuristic_v2"}:
        raise ValueError(f"不支持的风险评估方法: {risk_method}")
    if risk_method == "heuristic_v2":
        v2_weights = risk_config.get("v2", {}).get("weights", {})
        if v2_weights and sum(float(value) for value in v2_weights.values()) <= 0:
            raise ValueError("risk_evaluation.v2.weights 权重之和必须大于 0")


def create_run_directory(config_path, config):
    output_config = config["output"]
    output_root = output_config["root"]
    if not os.path.isabs(output_root):
        output_root = os.path.abspath(
            os.path.join(os.path.dirname(config_path), output_root)
        )

    scenario_name = config["scenario"]["name"]
    timestamp_format = output_config.get("timestamp_format", "%Y%m%d_%H%M%S")
    run_id = datetime.now().strftime(timestamp_format)
    run_dir = os.path.join(output_root, scenario_name, run_id)

    suffix = 1
    unique_run_dir = run_dir
    while os.path.exists(unique_run_dir):
        unique_run_dir = f"{run_dir}_{suffix:02d}"
        suffix += 1
    run_dir = unique_run_dir

    os.makedirs(run_dir, exist_ok=False)
    for sensor_name in ("rgb", "depth", "semantic"):
        if config["sensors"][sensor_name]["enabled"]:
            os.makedirs(os.path.join(run_dir, sensor_name), exist_ok=True)

    with open(
        os.path.join(run_dir, "config_snapshot.json"),
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(config, file, ensure_ascii=False, indent=2)

    return run_dir, os.path.basename(run_dir)


def build_weather(weather_config):
    weather = carla.WeatherParameters()
    for name, value in weather_config.items():
        if not hasattr(weather, name):
            raise ValueError(f"CARLA 不支持天气参数: {name}")
        setattr(weather, name, float(value))
    return weather


def camera_transform_from_config(transform_config):
    return carla.Transform(
        carla.Location(
            x=float(transform_config["x"]),
            y=float(transform_config["y"]),
            z=float(transform_config["z"]),
        ),
        carla.Rotation(
            pitch=float(transform_config["pitch"]),
            yaw=float(transform_config["yaw"]),
            roll=float(transform_config["roll"]),
        ),
    )


def spawn_ego_vehicle(world, blueprint_library, config):
    blueprint = blueprint_library.find(config["ego_vehicle"]["blueprint"])
    spawn_points = world.get_map().get_spawn_points()
    if not spawn_points:
        raise RuntimeError("当前地图没有车辆出生点")

    preferred_index = int(config["scenario"]["ego_spawn_index"]) % len(spawn_points)
    ordered_points = [spawn_points[preferred_index]] + [
        point for index, point in enumerate(spawn_points) if index != preferred_index
    ]
    for spawn_point in ordered_points:
        vehicle = world.try_spawn_actor(blueprint, spawn_point)
        if vehicle:
            return vehicle, spawn_point
    raise RuntimeError("无法生成主车，请清理地图中的已有车辆后重试")


def angle_difference_degrees(first, second):
    return abs((first - second + 180.0) % 360.0 - 180.0)


def find_driving_waypoint_ahead(world_map, start_transform, distance):
    start_waypoint = world_map.get_waypoint(
        start_transform.location,
        project_to_road=True,
        lane_type=carla.LaneType.Driving,
    )
    if start_waypoint is None:
        return None

    candidates = start_waypoint.next(float(distance))
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda waypoint: angle_difference_degrees(
            waypoint.transform.rotation.yaw,
            start_transform.rotation.yaw,
        ),
    )


def find_adjacent_sidewalk(start_waypoint, side, max_lanes=8):
    waypoint = start_waypoint
    for _ in range(max_lanes):
        waypoint = (
            waypoint.get_left_lane()
            if side == "left"
            else waypoint.get_right_lane()
        )
        if waypoint is None:
            return None
        if waypoint.lane_type == carla.LaneType.Sidewalk:
            return waypoint
    return None


def spawn_lead_vehicle(world, blueprint_library, ego_transform, config):
    blueprint = blueprint_library.find(config["lead_vehicle"]["blueprint"])
    requested_distance = float(config["lead_vehicle"]["initial_distance_m"])
    world_map = world.get_map()

    for distance in (
        requested_distance,
        requested_distance - 3.0,
        requested_distance + 3.0,
        requested_distance - 6.0,
        requested_distance + 6.0,
    ):
        if distance <= 8.0:
            continue
        waypoint = find_driving_waypoint_ahead(world_map, ego_transform, distance)
        if waypoint is None:
            continue
        waypoint_transform = waypoint.transform
        transform = carla.Transform(
            carla.Location(
                x=waypoint_transform.location.x,
                y=waypoint_transform.location.y,
                z=waypoint_transform.location.z + 0.5,
            ),
            carla.Rotation(yaw=waypoint_transform.rotation.yaw),
        )
        vehicle = world.try_spawn_actor(blueprint, transform)
        if vehicle:
            return vehicle, distance
    raise RuntimeError("无法在主车前方道路 waypoint 生成前车")


def spawn_pedestrian(world, blueprint_library, ego_transform, config):
    pedestrian_config = config["pedestrian"]
    blueprint = blueprint_library.find(pedestrian_config["blueprint"])
    forward_distance = float(pedestrian_config["forward_distance_m"])
    crossing_waypoint = find_driving_waypoint_ahead(
        world.get_map(),
        ego_transform,
        forward_distance,
    )
    if crossing_waypoint is None:
        raise RuntimeError("无法定位行人横穿位置的道路 waypoint")

    crossing_transform = crossing_waypoint.transform
    yaw_radians = math.radians(crossing_transform.rotation.yaw)
    forward = crossing_transform.get_forward_vector()
    right = carla.Vector3D(
        x=-math.sin(yaw_radians),
        y=math.cos(yaw_radians),
        z=0.0,
    )

    roadside_offset = float(pedestrian_config["roadside_offset_m"])
    z_offset = float(pedestrian_config.get("spawn_z_offset_m", 0.5))
    crossing_center = crossing_transform.location

    right_sidewalk = find_adjacent_sidewalk(crossing_waypoint, "right")
    left_sidewalk = find_adjacent_sidewalk(crossing_waypoint, "left")
    road_edge_offset = crossing_waypoint.lane_width / 2.0 + 1.0

    if right_sidewalk is not None:
        base_start = right_sidewalk.transform.location
        base_destination = (
            left_sidewalk.transform.location
            if left_sidewalk is not None
            else crossing_center - right * road_edge_offset
        )
    elif left_sidewalk is not None:
        base_start = left_sidewalk.transform.location
        base_destination = crossing_center + right * road_edge_offset
    else:
        fallback_offset = min(
            roadside_offset,
            crossing_waypoint.lane_width + 1.0,
        )
        base_start = crossing_center + right * fallback_offset
        base_destination = crossing_center - right * fallback_offset

    walker = None
    start = None
    destination = None
    for longitudinal_offset in (0.0, -1.0, 1.0, -2.0, 2.0):
        candidate_start = base_start + forward * longitudinal_offset
        candidate_start.z += z_offset
        candidate_destination = base_destination + forward * longitudinal_offset
        candidate_destination.z += z_offset
        walker = world.try_spawn_actor(
            blueprint,
            carla.Transform(candidate_start),
        )
        if walker:
            start = candidate_start
            destination = candidate_destination
            break

    if not walker:
        raise RuntimeError("无法在道路相邻人行道生成行人")

    crossing_vector = destination - start
    crossing_length = math.hypot(crossing_vector.x, crossing_vector.y)
    if crossing_length <= 0:
        raise ValueError("行人横穿距离必须大于 0")
    direction = carla.Vector3D(
        x=crossing_vector.x / crossing_length,
        y=crossing_vector.y / crossing_length,
        z=0.0,
    )
    walker.apply_control(carla.WalkerControl(direction=direction, speed=0.0))
    return walker, start, direction, crossing_length


def configure_camera_blueprint(blueprint, camera_config):
    blueprint.set_attribute("image_size_x", str(int(camera_config["width"])))
    blueprint.set_attribute("image_size_y", str(int(camera_config["height"])))
    blueprint.set_attribute("fov", str(float(camera_config["fov"])))
    blueprint.set_attribute("sensor_tick", str(float(camera_config["sensor_tick"])))


def main():
    args = parse_args()
    config_path, config = load_config(args.config)
    print(f"[CONFIG] 校验通过: {config_path}")
    if args.validate_only:
        print("[CONFIG] validate-only 完成，未连接 CARLA")
        return

    run_dir, run_id = create_run_directory(config_path, config)
    print(f"[OUTPUT] 本次运行目录: {run_dir}")

    scenario_config = config["scenario"]
    synchronous_mode = bool(scenario_config.get("synchronous_mode", False))
    fixed_delta_seconds = float(
        scenario_config.get("fixed_delta_seconds", 0.05)
    )
    traffic_manager_seed = int(
        scenario_config.get("traffic_manager_seed", 0)
    )
    sensor_config = config["sensors"]
    camera_config = sensor_config["camera"]
    enabled_camera_names = [
        name
        for name in ("rgb", "depth", "semantic")
        if sensor_config[name]["enabled"]
    ]
    sensor_tick = float(camera_config["sensor_tick"])
    writer_workers = int(camera_config.get("writer_workers", 2))
    writer_queue_size = int(camera_config.get("writer_queue_size", 16))
    frame_wait_timeout = float(
        camera_config.get("frame_wait_timeout_seconds", 30.0)
    )
    flush_timeout = float(camera_config.get("flush_timeout_seconds", 120.0))
    sensor_pipeline = SensorWritePipeline(
        queue_size=writer_queue_size,
        workers_per_sensor=writer_workers,
    )
    metadata_lock = threading.Lock()
    collision_detected = threading.Event()
    frame_counts = {"rgb": 0, "depth": 0, "semantic": 0}
    metadata = {
        "scenario_name": config["scenario"]["name"],
        "run_id": run_id,
        "source_config": config_path,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "events": [],
        "frames": frame_counts,
        "simulation": {
            "synchronous_mode": synchronous_mode,
            "fixed_delta_seconds": fixed_delta_seconds,
            "traffic_manager_seed": traffic_manager_seed,
        },
        "sensor_pipeline": {
            "status": "starting",
            "queue_size": writer_queue_size,
            "workers_per_sensor": writer_workers,
            "sensors": {},
        },
        "server_health": {"status": "not_checked"},
        "result": {
            "status": "starting",
            "collision_count": 0,
            "minimum_lead_distance_m": None,
            "minimum_lead_gap_m": None,
            "minimum_ttc_seconds": None,
            "minimum_pedestrian_distance_m": None,
            "risk_evaluation": None,
        },
    }

    risk_config = config["risk_evaluation"]
    telemetry_rows = []
    minimum_lead_distance = None
    minimum_lead_gap_m = None
    minimum_ttc_seconds = None
    minimum_pedestrian_distance_m = None
    actors = []
    sensor_actors = []
    traffic_light_states = []
    client = None
    traffic_manager = None
    world = None
    original_settings = None
    original_weather = None
    start_time = None
    simulation_elapsed = 0.0
    simulation_step = 0
    walker = None
    walker_direction = None
    callback_condition = threading.Condition()
    active_sensor_callbacks = 0

    def record_event(event_type, elapsed_seconds, **details):
        event = {
            "type": event_type,
            "elapsed_seconds": round(float(elapsed_seconds), 3),
        }
        event.update(details)
        with metadata_lock:
            metadata["events"].append(event)

    def guarded_callback(callback):
        def listener(data):
            nonlocal active_sensor_callbacks
            with callback_condition:
                active_sensor_callbacks += 1
            try:
                callback(data)
            finally:
                with callback_condition:
                    active_sensor_callbacks -= 1
                    callback_condition.notify_all()

        return listener

    def expected_sensor_frame_counts():
        if not synchronous_mode or simulation_step <= 0:
            return {}
        if sensor_tick <= 0:
            expected_count = simulation_step
        else:
            interval_steps = max(
                1,
                round(sensor_tick / fixed_delta_seconds),
            )
            expected_count = simulation_step // interval_steps
        return {
            sensor_name: expected_count
            for sensor_name in enabled_camera_names
        }

    def update_sensor_metadata():
        snapshot = sensor_pipeline.snapshot(expected_sensor_frame_counts())
        metadata["sensor_pipeline"] = snapshot
        saved_counts = {
            sensor_name: snapshot["sensors"].get(sensor_name, {}).get("saved", 0)
            for sensor_name in frame_counts
        }
        with metadata_lock:
            frame_counts.update(saved_counts)
            metadata["frames"] = dict(frame_counts)
        return snapshot

    def destroy_actor_group(actor_group, label):
        if client is None or not actor_group:
            return True
        commands = [
            carla.command.DestroyActor(actor.id)
            for actor in reversed(actor_group)
        ]
        try:
            responses = client.apply_batch_sync(commands, synchronous_mode)
        except RuntimeError as error:
            print(f"[CLEANUP] {label}同步销毁失败: {error}", flush=True)
            return False
        errors = [
            response.error
            for response in (responses or [])
            if response.error
        ]
        if errors:
            print(
                f"[CLEANUP] {label}销毁错误: {'; '.join(errors)}",
                flush=True,
            )
            return False
        print(f"[CLEANUP] {label}同步销毁完成", flush=True)
        return True

    def persist_results(cleanup_status):
        if start_time is not None:
            wall_duration = time.monotonic() - start_time
            actual_duration = (
                simulation_elapsed if synchronous_mode else wall_duration
            )
            metadata["result"]["actual_duration_seconds"] = round(
                actual_duration,
                3,
            )
            metadata["result"]["wall_duration_seconds"] = round(
                wall_duration,
                3,
            )
        metadata["finished_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        metadata["cleanup"] = {"status": cleanup_status}
        metadata["simulation"]["elapsed_seconds"] = round(
            simulation_elapsed,
            3,
        )
        metadata["simulation"]["completed_steps"] = (
            round(simulation_elapsed / fixed_delta_seconds)
            if synchronous_mode
            else len(telemetry_rows)
        )
        update_sensor_metadata()

        if minimum_lead_gap_m is not None and math.isfinite(minimum_lead_gap_m):
            metadata["result"]["minimum_lead_gap_m"] = round(
                minimum_lead_gap_m,
                3,
            )
        if minimum_ttc_seconds is not None:
            metadata["result"]["minimum_ttc_seconds"] = round(
                minimum_ttc_seconds,
                3,
            )
        if minimum_pedestrian_distance_m is not None:
            metadata["result"]["minimum_pedestrian_distance_m"] = round(
                minimum_pedestrian_distance_m,
                3,
            )
        if telemetry_rows:
            metadata["result"]["risk_evaluation"] = evaluate_telemetry_risk(
                telemetry_rows,
                metadata["result"]["collision_count"],
                risk_config,
                weather_config=config["weather"],
                pedestrian_config=config["pedestrian"],
                scenario_config=config["scenario"],
                events=metadata["events"],
            )

        telemetry_path = os.path.join(run_dir, "telemetry.csv")
        write_telemetry_csv(telemetry_path, telemetry_rows)
        metadata["telemetry"] = {
            "path": telemetry_path,
            "sample_count": len(telemetry_rows),
        }

        metadata_path = os.path.join(run_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)
        return metadata_path

    try:
        client = carla.Client("localhost", 2000)
        client.set_timeout(20.0)
        world = client.get_world()
        original_settings = world.get_settings()
        original_weather = world.get_weather()
        traffic_config = config["traffic"]
        tm_port = int(scenario_config["traffic_manager_port"])
        traffic_manager = client.get_trafficmanager(tm_port)
        traffic_manager.set_global_distance_to_leading_vehicle(
            float(traffic_config["leading_distance_m"])
        )
        traffic_manager.set_random_device_seed(traffic_manager_seed)

        if synchronous_mode:
            settings = world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = fixed_delta_seconds
            world.apply_settings(settings)
            traffic_manager.set_synchronous_mode(True)
            world.tick()
        else:
            traffic_manager.set_synchronous_mode(False)

        world.set_weather(build_weather(config["weather"]))
        metadata["map"] = world.get_map().name
        print(f"[CONNECT] CARLA 地图: {metadata['map']}")
        print(
            f"[SIM] sync={synchronous_mode} | "
            f"delta={fixed_delta_seconds:.3f}s | "
            f"TM seed={traffic_manager_seed}"
        )

        if traffic_config["force_green_lights"]:
            traffic_lights = list(
                world.get_actors().filter("traffic.traffic_light*")
            )
            traffic_light_states = [
                (light, light.get_state(), light.is_frozen())
                for light in traffic_lights
            ]
            for light in traffic_lights:
                light.set_state(carla.TrafficLightState.Green)
                light.freeze(True)
            print(f"[TRAFFIC] {len(traffic_lights)} 个交通灯已锁定为绿灯")

        blueprint_library = world.get_blueprint_library()
        ego_vehicle, ego_spawn = spawn_ego_vehicle(
            world,
            blueprint_library,
            config,
        )
        actors.append(ego_vehicle)
        # Actor 刚生成时 get_transform() 可能在服务器下一帧前返回零坐标。
        # 使用地图提供的出生点作为后续 Actor 的可靠定位基准。
        ego_transform = ego_spawn
        print(f"[EGO] {ego_vehicle.type_id}")

        lead_vehicle, actual_lead_distance = spawn_lead_vehicle(
            world,
            blueprint_library,
            ego_transform,
            config,
        )
        actors.append(lead_vehicle)
        print(
            f"[LEAD] {lead_vehicle.type_id}, 初始距离约 "
            f"{actual_lead_distance:.1f} m"
        )

        walker, walker_start, walker_direction, crossing_length = spawn_pedestrian(
            world,
            blueprint_library,
            ego_transform,
            config,
        )
        actors.append(walker)
        print("[WALKER] 行人已在路边待命")

        if synchronous_mode:
            world.tick()
        else:
            world.wait_for_tick(2.0)
        measured_initial_distance = ego_vehicle.get_location().distance(
            lead_vehicle.get_location()
        )
        if measured_initial_distance > actual_lead_distance + 15.0:
            raise RuntimeError(
                "前车实际初始距离异常: "
                f"期望约 {actual_lead_distance:.1f} m, "
                f"实际 {measured_initial_distance:.1f} m"
            )
        print(f"[LEAD] 实际初始距离 {measured_initial_distance:.1f} m")

        camera_transform = camera_transform_from_config(sensor_config["transform"])

        if sensor_config["rgb"]["enabled"]:
            rgb_blueprint = blueprint_library.find("sensor.camera.rgb")
            configure_camera_blueprint(rgb_blueprint, camera_config)
            rgb_camera = world.spawn_actor(
                rgb_blueprint,
                camera_transform,
                attach_to=ego_vehicle,
            )
            actors.append(rgb_camera)
            sensor_actors.append(rgb_camera)

            def save_rgb(image):
                image.save_to_disk(
                    os.path.join(run_dir, "rgb", f"frame_{image.frame:06d}.png")
                )

            sensor_pipeline.register("rgb", save_rgb)
            rgb_camera.listen(
                guarded_callback(
                    lambda image: sensor_pipeline.submit("rgb", image)
                )
            )

        if sensor_config["depth"]["enabled"]:
            depth_blueprint = blueprint_library.find("sensor.camera.depth")
            configure_camera_blueprint(depth_blueprint, camera_config)
            depth_camera = world.spawn_actor(
                depth_blueprint,
                camera_transform,
                attach_to=ego_vehicle,
            )
            actors.append(depth_camera)
            sensor_actors.append(depth_camera)
            max_depth = float(
                sensor_config["depth"]["visualization_max_distance_m"]
            )

            def save_depth(image):
                raw = np.frombuffer(image.raw_data, dtype=np.uint8)
                raw = raw.reshape((image.height, image.width, 4))
                depth_m = (
                    raw[:, :, 2].astype(np.float32)
                    + raw[:, :, 1].astype(np.float32) * 256.0
                    + raw[:, :, 0].astype(np.float32) * 65536.0
                ) / 16777215.0 * 1000.0
                depth_gray = np.clip(
                    depth_m / max_depth * 255.0,
                    0,
                    255,
                ).astype(np.uint8)
                Image.fromarray(depth_gray, mode="L").save(
                    os.path.join(
                        run_dir,
                        "depth",
                        f"frame_{image.frame:06d}.png",
                    )
                )

            sensor_pipeline.register("depth", save_depth)
            depth_camera.listen(
                guarded_callback(
                    lambda image: sensor_pipeline.submit("depth", image)
                )
            )

        if sensor_config["semantic"]["enabled"]:
            semantic_blueprint = blueprint_library.find(
                "sensor.camera.semantic_segmentation"
            )
            configure_camera_blueprint(semantic_blueprint, camera_config)
            semantic_camera = world.spawn_actor(
                semantic_blueprint,
                camera_transform,
                attach_to=ego_vehicle,
            )
            actors.append(semantic_camera)
            sensor_actors.append(semantic_camera)
            save_raw_labels = sensor_config["semantic"]["save_raw_labels"]

            def save_semantic(image):
                if save_raw_labels:
                    raw = np.frombuffer(image.raw_data, dtype=np.uint8)
                    raw = raw.reshape((image.height, image.width, 4)).copy()
                    labels = raw[:, :, 2].copy()
                    np.save(
                        os.path.join(
                            run_dir,
                            "semantic",
                            f"labels_{image.frame:06d}.npy",
                        ),
                        labels,
                    )
                image.convert(carla.ColorConverter.CityScapesPalette)
                image.save_to_disk(
                    os.path.join(
                        run_dir,
                        "semantic",
                        f"frame_{image.frame:06d}.png",
                    )
                )

            sensor_pipeline.register("semantic", save_semantic)
            semantic_camera.listen(
                guarded_callback(
                    lambda image: sensor_pipeline.submit("semantic", image)
                )
            )

        if sensor_config["collision"]["enabled"]:
            collision_blueprint = blueprint_library.find("sensor.other.collision")
            collision_sensor = world.spawn_actor(
                collision_blueprint,
                carla.Transform(),
                attach_to=ego_vehicle,
            )
            actors.append(collision_sensor)
            sensor_actors.append(collision_sensor)

            def on_collision(event):
                impulse = event.normal_impulse
                intensity = math.sqrt(
                    impulse.x ** 2 + impulse.y ** 2 + impulse.z ** 2
                )
                elapsed = (
                    simulation_elapsed
                    if synchronous_mode
                    else time.monotonic() - start_time
                    if start_time
                    else 0.0
                )
                with metadata_lock:
                    metadata["result"]["collision_count"] += 1
                record_event(
                    "collision",
                    elapsed,
                    frame=event.frame,
                    other_actor=event.other_actor.type_id,
                    impulse=round(intensity, 3),
                )
                collision_detected.set()

            collision_sensor.listen(guarded_callback(on_collision))

        ego_vehicle.set_autopilot(True, tm_port)
        lead_vehicle.set_autopilot(True, tm_port)
        ignore_percentage = float(traffic_config["ignore_lights_percentage"])
        traffic_manager.ignore_lights_percentage(ego_vehicle, ignore_percentage)
        traffic_manager.ignore_lights_percentage(lead_vehicle, ignore_percentage)

        pedestrian_config = config["pedestrian"]
        lead_config = config["lead_vehicle"]
        pedestrian_trigger = float(pedestrian_config["trigger_seconds"])
        pedestrian_speed = float(pedestrian_config["speed_mps"])
        brake_trigger = float(lead_config["brake_trigger_seconds"])
        brake_intensity = float(lead_config["brake_intensity"])
        duration = float(config["scenario"]["duration_seconds"])

        metadata["actors"] = {
            "ego_vehicle": ego_vehicle.type_id,
            "lead_vehicle": lead_vehicle.type_id,
            "pedestrian": walker.type_id,
            "lead_initial_distance_m": round(measured_initial_distance, 3),
            "ego_spawn": {
                "x": round(ego_spawn.location.x, 3),
                "y": round(ego_spawn.location.y, 3),
                "z": round(ego_spawn.location.z, 3),
            },
        }
        metadata["result"]["status"] = "running"

        start_time = time.monotonic()
        simulation_elapsed = 0.0
        next_status_time = 1.0
        pedestrian_started = False
        pedestrian_finished = False
        brake_started = False
        minimum_lead_distance = float("inf")
        minimum_lead_gap_m = float("inf")

        print("[RUN] 场景开始")
        print(
            f"[RUN] {pedestrian_trigger:.1f}s 行人冲出, "
            f"{brake_trigger:.1f}s 前车急刹, 总时长 {duration:.1f}s"
        )

        while True:
            if synchronous_mode:
                if simulation_elapsed >= duration:
                    break
                world.tick()
                simulation_step += 1
                simulation_elapsed = min(
                    simulation_step * fixed_delta_seconds,
                    duration,
                )
                elapsed = simulation_elapsed
                expected_counts = expected_sensor_frame_counts()
                if expected_counts and not sensor_pipeline.wait_for_received(
                    expected_counts,
                    frame_wait_timeout,
                ):
                    snapshot = sensor_pipeline.snapshot(expected_counts)
                    received = {
                        name: details["received"]
                        for name, details in snapshot["sensors"].items()
                    }
                    raise RuntimeError(
                        "等待同步传感器帧超时: "
                        f"expected={expected_counts}, received={received}"
                    )
            else:
                elapsed = time.monotonic() - start_time
                simulation_elapsed = elapsed
                if elapsed >= duration:
                    break

            if elapsed >= pedestrian_trigger and not pedestrian_started:
                pedestrian_started = True
                record_event("pedestrian_started", elapsed, speed_mps=pedestrian_speed)
                print(f"[EVENT {elapsed:5.2f}s] 行人突然冲出")

            if pedestrian_started and not pedestrian_finished:
                walked_distance = walker.get_location().distance(walker_start)
                if walked_distance >= crossing_length:
                    walker.apply_control(
                        carla.WalkerControl(
                            direction=walker_direction,
                            speed=0.0,
                        )
                    )
                    pedestrian_finished = True
                    record_event("pedestrian_finished", elapsed)
                else:
                    walker.apply_control(
                        carla.WalkerControl(
                            direction=walker_direction,
                            speed=pedestrian_speed,
                        )
                    )

            if elapsed >= brake_trigger and not brake_started:
                lead_vehicle.set_autopilot(False, tm_port)
                brake_started = True
                record_event("lead_vehicle_brake", elapsed, intensity=brake_intensity)
                print(f"[EVENT {elapsed:5.2f}s] 前车开始急刹")

            if brake_started:
                lead_vehicle.apply_control(
                    carla.VehicleControl(
                        throttle=0.0,
                        brake=brake_intensity,
                        hand_brake=False,
                    )
                )

            ego_location = ego_vehicle.get_location()
            lead_location = lead_vehicle.get_location()
            ego_velocity = ego_vehicle.get_velocity()
            lead_velocity = lead_vehicle.get_velocity()
            lead_distance, lead_gap_distance, closing_speed, ttc_seconds = calculate_ttc(
                ego_location,
                ego_velocity,
                lead_location,
                lead_velocity,
                risk_config["vehicle_distance_buffer_m"],
            )
            pedestrian_distance = None
            if pedestrian_started:
                pedestrian_distance = ego_location.distance(walker.get_location())

            minimum_lead_distance = min(minimum_lead_distance, lead_distance)
            minimum_lead_gap_m = min(minimum_lead_gap_m, lead_gap_distance)
            if ttc_seconds is not None and math.isfinite(ttc_seconds):
                if minimum_ttc_seconds is None:
                    minimum_ttc_seconds = ttc_seconds
                else:
                    minimum_ttc_seconds = min(minimum_ttc_seconds, ttc_seconds)
            if pedestrian_distance is not None:
                if minimum_pedestrian_distance_m is None:
                    minimum_pedestrian_distance_m = pedestrian_distance
                else:
                    minimum_pedestrian_distance_m = min(
                        minimum_pedestrian_distance_m,
                        pedestrian_distance,
                    )

            with metadata_lock:
                collision_count = metadata["result"]["collision_count"]
            telemetry_rows.append(
                {
                    "elapsed_seconds": round(elapsed, 3),
                    "ego_speed_kmh": round(vehicle_speed_kmh(ego_velocity), 3),
                    "lead_speed_kmh": round(vehicle_speed_kmh(lead_velocity), 3),
                    "lead_center_distance_m": round(lead_distance, 3),
                    "lead_gap_distance_m": round(lead_gap_distance, 3),
                    "closing_speed_mps": round(closing_speed, 3),
                    "ttc_seconds": (
                        round(ttc_seconds, 3)
                        if ttc_seconds is not None and math.isfinite(ttc_seconds)
                        else None
                    ),
                    "pedestrian_distance_m": (
                        round(pedestrian_distance, 3)
                        if pedestrian_distance is not None
                        else None
                    ),
                    "pedestrian_active": pedestrian_started and not pedestrian_finished,
                    "lead_braking": brake_started,
                    "collision_count": collision_count,
                }
            )

            if elapsed >= next_status_time:
                speed_kmh = vehicle_speed_kmh(ego_velocity)
                print(
                    f"[STATE {elapsed:5.1f}s] 主车 {speed_kmh:5.1f} km/h, "
                    f"距前车 {lead_distance:5.1f} m"
                )
                next_status_time += 1.0

            if (
                collision_detected.is_set()
                and config["scenario"]["stop_on_collision"]
            ):
                print("[RUN] 检测到碰撞，按配置提前结束")
                break

            if not synchronous_mode:
                time.sleep(0.05)

        metadata["result"]["status"] = "completed"
        metadata["result"]["minimum_lead_distance_m"] = round(
            minimum_lead_distance,
            3,
        )
        metadata["result"]["minimum_lead_gap_m"] = round(
            minimum_lead_gap_m,
            3,
        )
        if minimum_ttc_seconds is not None:
            metadata["result"]["minimum_ttc_seconds"] = round(
                minimum_ttc_seconds,
                3,
            )
        if minimum_pedestrian_distance_m is not None:
            metadata["result"]["minimum_pedestrian_distance_m"] = round(
                minimum_pedestrian_distance_m,
                3,
            )

    except KeyboardInterrupt:
        metadata["result"]["status"] = "interrupted"
        print("[STOP] 用户中断")
    except Exception as error:
        metadata["result"]["status"] = "failed"
        metadata["result"]["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        checkpoint_path = persist_results("pending")
        print(f"[CHECKPOINT] 运行数据已保存: {checkpoint_path}", flush=True)
        print("[CLEANUP] 清理传感器和场景 Actor", flush=True)
        expected_counts = expected_sensor_frame_counts()
        if expected_counts and not sensor_pipeline.wait_for_received(
            expected_counts,
            frame_wait_timeout,
        ):
            snapshot = sensor_pipeline.snapshot(expected_counts)
            print(
                "[CLEANUP] 等待传感器接收超时: "
                f"{snapshot['sensors']}",
                flush=True,
            )
        for sensor in sensor_actors:
            try:
                sensor.stop()
            except RuntimeError:
                pass
        print("[CLEANUP] 传感器监听已停止", flush=True)
        callback_deadline = time.monotonic() + 5.0
        with callback_condition:
            while active_sensor_callbacks > 0:
                remaining = callback_deadline - time.monotonic()
                if remaining <= 0:
                    break
                callback_condition.wait(timeout=remaining)
        print(
            f"[CLEANUP] 传感器回调剩余: {active_sensor_callbacks}",
            flush=True,
        )
        pipeline_drained = sensor_pipeline.close(flush_timeout)
        pipeline_snapshot = update_sensor_metadata()
        print(
            "[CLEANUP] 传感器写盘状态: "
            f"{pipeline_snapshot['status']} | "
            f"帧数={metadata['frames']}",
            flush=True,
        )
        if not pipeline_drained or pipeline_snapshot["status"] != "completed":
            if metadata["result"]["status"] == "completed":
                metadata["result"]["status"] = "failed"
                metadata["result"]["error"] = (
                    "传感器数据写盘不完整: "
                    f"{pipeline_snapshot['status']}"
                )

        sensor_ids = {sensor.id for sensor in sensor_actors}
        scene_actors = [actor for actor in actors if actor.id not in sensor_ids]
        sensors_destroyed = destroy_actor_group(sensor_actors, "传感器 Actor")
        actors_destroyed = destroy_actor_group(scene_actors, "场景 Actor")

        for light, state, was_frozen in traffic_light_states:
            try:
                if light.is_alive:
                    light.freeze(False)
                    light.set_state(state)
                    light.freeze(was_frozen)
            except RuntimeError:
                pass

        if world is not None and original_weather is not None:
            try:
                world.set_weather(original_weather)
            except RuntimeError:
                pass
        if traffic_manager is not None and synchronous_mode:
            try:
                traffic_manager.set_synchronous_mode(False)
            except RuntimeError:
                pass
        if world is not None and original_settings is not None:
            try:
                world.apply_settings(original_settings)
            except RuntimeError:
                pass
        print("[CLEANUP] 交通灯、天气和世界设置已恢复", flush=True)

        cleanup_ok = sensors_destroyed and actors_destroyed
        if client is not None:
            try:
                client.set_timeout(5.0)
                time.sleep(1.0)
                server_version = client.get_server_version()
                health_world = client.get_world()
                health_world.get_snapshot()
                metadata["server_health"] = {
                    "status": "healthy",
                    "server_version": server_version,
                }
                print("[CLEANUP] CARLA 服务健康检查通过", flush=True)
            except RuntimeError as error:
                cleanup_ok = False
                metadata["server_health"] = {
                    "status": "unreachable",
                    "error": f"{type(error).__name__}: {error}",
                }
                print(f"[CLEANUP] CARLA 服务健康检查失败: {error}", flush=True)
        if not cleanup_ok and metadata["result"]["status"] == "completed":
            metadata["result"]["status"] = "failed"
            metadata["result"]["error"] = "Actor 清理或 CARLA 服务健康检查失败"

        metadata_path = persist_results("completed" if cleanup_ok else "failed")
        print(f"[DONE] 元数据: {metadata_path}")
        print(f"[DONE] 帧数: {metadata['frames']}")


if __name__ == "__main__":
    main()
