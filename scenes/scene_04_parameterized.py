# -*- coding: utf-8 -*-
"""场景04：由 JSON 配置驱动的多危险、多传感器 CARLA 场景。"""

import argparse
import json
import math
import os
import threading
import time
from datetime import datetime

import carla
import numpy as np
from PIL import Image


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    if float(camera["sensor_tick"]) < 0:
        raise ValueError("sensors.camera.sensor_tick 不能小于 0")
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
        "result": {
            "status": "starting",
            "collision_count": 0,
            "minimum_lead_distance_m": None,
        },
    }

    actors = []
    sensor_actors = []
    traffic_light_states = []
    world = None
    original_weather = None
    start_time = None

    def record_event(event_type, elapsed_seconds, **details):
        event = {
            "type": event_type,
            "elapsed_seconds": round(float(elapsed_seconds), 3),
        }
        event.update(details)
        with metadata_lock:
            metadata["events"].append(event)

    def count_frame(sensor_name):
        with metadata_lock:
            frame_counts[sensor_name] += 1

    try:
        client = carla.Client("localhost", 2000)
        client.set_timeout(20.0)
        world = client.get_world()
        original_weather = world.get_weather()
        world.set_weather(build_weather(config["weather"]))
        metadata["map"] = world.get_map().name
        print(f"[CONNECT] CARLA 地图: {metadata['map']}")

        traffic_config = config["traffic"]
        tm_port = int(config["scenario"]["traffic_manager_port"])
        traffic_manager = client.get_trafficmanager(tm_port)
        traffic_manager.set_global_distance_to_leading_vehicle(
            float(traffic_config["leading_distance_m"])
        )
        traffic_manager.set_synchronous_mode(False)

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

        sensor_config = config["sensors"]
        camera_config = sensor_config["camera"]
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
                count_frame("rgb")

            rgb_camera.listen(save_rgb)

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
                count_frame("depth")

            depth_camera.listen(save_depth)

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
                count_frame("semantic")

            semantic_camera.listen(save_semantic)

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
                elapsed = time.monotonic() - start_time if start_time else 0.0
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

            collision_sensor.listen(on_collision)

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
        next_status_time = 1.0
        pedestrian_started = False
        pedestrian_finished = False
        brake_started = False
        minimum_lead_distance = float("inf")

        print("[RUN] 场景开始")
        print(
            f"[RUN] {pedestrian_trigger:.1f}s 行人冲出, "
            f"{brake_trigger:.1f}s 前车急刹, 总时长 {duration:.1f}s"
        )

        while True:
            elapsed = time.monotonic() - start_time
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

            lead_distance = ego_vehicle.get_location().distance(
                lead_vehicle.get_location()
            )
            minimum_lead_distance = min(minimum_lead_distance, lead_distance)

            if elapsed >= next_status_time:
                velocity = ego_vehicle.get_velocity()
                speed_kmh = 3.6 * math.sqrt(
                    velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2
                )
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

            time.sleep(0.05)

        metadata["result"]["status"] = "completed"
        metadata["result"]["minimum_lead_distance_m"] = round(
            minimum_lead_distance,
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
        print("[CLEANUP] 清理传感器和场景 Actor")
        for sensor in sensor_actors:
            try:
                sensor.stop()
            except RuntimeError:
                pass
        time.sleep(0.2)

        for actor in reversed(actors):
            try:
                if actor.is_alive:
                    actor.destroy()
            except RuntimeError:
                pass

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

        if start_time is not None:
            metadata["result"]["actual_duration_seconds"] = round(
                time.monotonic() - start_time,
                3,
            )
        metadata["finished_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        with metadata_lock:
            metadata["frames"] = dict(frame_counts)

        metadata_path = os.path.join(run_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)
        print(f"[DONE] 元数据: {metadata_path}")
        print(f"[DONE] 帧数: {metadata['frames']}")


if __name__ == "__main__":
    main()
