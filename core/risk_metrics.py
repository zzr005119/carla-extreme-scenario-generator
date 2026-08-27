"""场景遥测与启发式风险评估。"""

import csv
import math


TELEMETRY_FIELDS = [
    "elapsed_seconds",
    "ego_speed_kmh",
    "lead_speed_kmh",
    "lead_center_distance_m",
    "lead_gap_distance_m",
    "closing_speed_mps",
    "ttc_seconds",
    "pedestrian_distance_m",
    "pedestrian_active",
    "lead_braking",
    "ego_hazard_brake_reason",
    "collision_count",
    "ego_control_throttle",
    "ego_control_brake",
    "ego_control_steer",
    "lead_control_throttle",
    "lead_control_brake",
    "lead_control_steer",
    "lead_stop_lock_active",
    "lead_stop_lock_below_threshold_steps",
    "ego_road_id",
    "ego_lane_id",
    "ego_planned_road_id",
    "ego_planned_lane_id",
    "ego_route_index",
    "ego_route_deviation_m",
    "ego_route_topology_match",
    "ego_on_planned_route",
    "ego_controller_progress_index",
    "ego_controller_target_index",
    "lead_road_id",
    "lead_lane_id",
    "lead_planned_road_id",
    "lead_planned_lane_id",
    "lead_route_index",
    "lead_route_deviation_m",
    "lead_route_topology_match",
    "lead_on_planned_route",
    "lead_controller_progress_index",
    "lead_controller_target_index",
    "route_lock_active",
    "route_control_mode",
]


RISK_V2_DEFAULTS = {
    "weights": {
        "collision": 0.25,
        "ttc": 0.25,
        "lead_gap": 0.15,
        "pedestrian_distance": 0.12,
        "pedestrian_speed": 0.08,
        "weather_visibility": 0.15,
    },
    "ttc": {"critical_seconds": 0.5, "safe_seconds": 4.0},
    "lead_gap": {"critical_m": 1.0, "safe_m": 8.0},
    "pedestrian_distance": {"critical_m": 1.0, "safe_m": 6.0},
    "pedestrian_speed": {"safe_mps": 3.0, "critical_mps": 6.0},
    "weather": {
        "fog_density_safe": 60.0,
        "fog_density_critical": 95.0,
        "fog_distance_critical_m": 5.0,
        "fog_distance_safe_m": 30.0,
        "precipitation_safe": 60.0,
        "precipitation_critical": 100.0,
        "sun_altitude_critical": -15.0,
        "sun_altitude_safe": 10.0,
        "fog_density_weight": 0.4,
        "fog_distance_weight": 0.3,
        "precipitation_weight": 0.2,
        "night_weight": 0.1,
    },
    "levels": {"medium": 25.0, "high": 50.0, "critical": 75.0},
}


def vector_length(vector):
    return math.sqrt(vector.x ** 2 + vector.y ** 2 + vector.z ** 2)


def vehicle_speed_kmh(velocity):
    return 3.6 * vector_length(velocity)


def calculate_ttc(
    ego_location,
    ego_velocity,
    lead_location,
    lead_velocity,
    distance_buffer_m=4.5,
):
    delta_x = lead_location.x - ego_location.x
    delta_y = lead_location.y - ego_location.y
    delta_z = lead_location.z - ego_location.z
    center_distance = math.sqrt(delta_x ** 2 + delta_y ** 2 + delta_z ** 2)
    gap_distance = max(0.0, center_distance - float(distance_buffer_m))

    if center_distance <= 1e-6:
        return center_distance, gap_distance, float("inf"), 0.0

    unit_x = delta_x / center_distance
    unit_y = delta_y / center_distance
    unit_z = delta_z / center_distance
    ego_along = (
        ego_velocity.x * unit_x
        + ego_velocity.y * unit_y
        + ego_velocity.z * unit_z
    )
    lead_along = (
        lead_velocity.x * unit_x
        + lead_velocity.y * unit_y
        + lead_velocity.z * unit_z
    )
    closing_speed = ego_along - lead_along

    if closing_speed <= 0.1:
        return center_distance, gap_distance, closing_speed, None
    return center_distance, gap_distance, closing_speed, gap_distance / closing_speed


def normalized_low_value_risk(value, critical_value, safe_value):
    if value is None:
        return 0.0
    value = float(value)
    critical_value = float(critical_value)
    safe_value = float(safe_value)
    if safe_value <= critical_value:
        raise ValueError("风险阈值要求 safe_value 大于 critical_value")
    if value <= critical_value:
        return 1.0
    if value >= safe_value:
        return 0.0
    return (safe_value - value) / (safe_value - critical_value)


def normalized_high_value_risk(value, safe_value, critical_value):
    if value is None:
        return 0.0
    value = float(value)
    safe_value = float(safe_value)
    critical_value = float(critical_value)
    if critical_value <= safe_value:
        raise ValueError("风险阈值要求 critical_value 大于 safe_value")
    if value <= safe_value:
        return 0.0
    if value >= critical_value:
        return 1.0
    return (value - safe_value) / (critical_value - safe_value)


def _as_float(value):
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _merge_v2_config(risk_config):
    merged = {
        section: dict(values) if isinstance(values, dict) else values
        for section, values in RISK_V2_DEFAULTS.items()
    }
    supplied = (risk_config or {}).get("v2", {})
    for section, values in supplied.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section].update(values)
        else:
            merged[section] = values
    return merged


def _minimum_telemetry_value(rows, field_name):
    values = [_as_float(row.get(field_name)) for row in rows]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _first_event_time(events, event_type):
    values = []
    for event in events or []:
        if event.get("type") != event_type:
            continue
        elapsed_seconds = _as_float(event.get("elapsed_seconds"))
        if elapsed_seconds is not None:
            values.append(elapsed_seconds)
    return min(values) if values else None


def _weather_visibility_risk(weather_config, parameters):
    if not weather_config:
        return 0.0, {}

    weather = parameters["weather"]
    components = {
        "fog_density": normalized_high_value_risk(
            _as_float(weather_config.get("fog_density")),
            weather["fog_density_safe"],
            weather["fog_density_critical"],
        ),
        "fog_distance": normalized_low_value_risk(
            _as_float(weather_config.get("fog_distance")),
            weather["fog_distance_critical_m"],
            weather["fog_distance_safe_m"],
        ),
        "precipitation": normalized_high_value_risk(
            _as_float(weather_config.get("precipitation")),
            weather["precipitation_safe"],
            weather["precipitation_critical"],
        ),
        "night": normalized_low_value_risk(
            _as_float(weather_config.get("sun_altitude_angle")),
            weather["sun_altitude_critical"],
            weather["sun_altitude_safe"],
        ),
    }
    weights = {
        "fog_density": float(weather["fog_density_weight"]),
        "fog_distance": float(weather["fog_distance_weight"]),
        "precipitation": float(weather["precipitation_weight"]),
        "night": float(weather["night_weight"]),
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("天气风险权重之和必须大于 0")
    score = sum(components[name] * weights[name] for name in components)
    return score / total_weight, components


def _level_from_score(score, levels):
    medium_threshold = float(levels.get("medium", 25.0))
    high_threshold = float(levels.get("high", 50.0))
    critical_threshold = float(levels.get("critical", 75.0))
    if score >= critical_threshold:
        return "critical"
    if score >= high_threshold:
        return "high"
    if score >= medium_threshold:
        return "medium"
    return "low"


def evaluate_risk(
    minimum_ttc_seconds,
    minimum_lead_gap_m,
    minimum_pedestrian_distance_m,
    collision_count,
    config,
):
    components = {
        "ttc": normalized_low_value_risk(
            minimum_ttc_seconds,
            config["ttc"]["critical_seconds"],
            config["ttc"]["safe_seconds"],
        ),
        "lead_distance": normalized_low_value_risk(
            minimum_lead_gap_m,
            config["lead_distance"]["critical_m"],
            config["lead_distance"]["safe_m"],
        ),
        "pedestrian_distance": normalized_low_value_risk(
            minimum_pedestrian_distance_m,
            config["pedestrian_distance"]["critical_m"],
            config["pedestrian_distance"]["safe_m"],
        ),
        "collision": 1.0 if int(collision_count) > 0 else 0.0,
    }
    weights = {
        "ttc": float(config["ttc"]["weight"]),
        "lead_distance": float(config["lead_distance"]["weight"]),
        "pedestrian_distance": float(config["pedestrian_distance"]["weight"]),
        "collision": float(config["collision"]["weight"]),
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("风险权重之和必须大于 0")

    score = 100.0 * sum(
        components[name] * weights[name] for name in components
    ) / total_weight
    score = round(score, 3)

    return {
        "method": config.get("method", "heuristic_v1"),
        "score": score,
        "level": _level_from_score(score, config.get("levels", {})),
        "components": {
            name: round(value, 4) for name, value in components.items()
        },
        "weights": weights,
    }


def evaluate_risk_v2(
    telemetry_rows,
    collision_count,
    risk_config,
    weather_config=None,
    pedestrian_config=None,
    scenario_config=None,
    events=None,
):
    rows = list(telemetry_rows or [])
    parameters = _merge_v2_config(risk_config)

    minimum_ttc_seconds = _minimum_telemetry_value(rows, "ttc_seconds")
    minimum_lead_gap_m = _minimum_telemetry_value(
        rows,
        "lead_gap_distance_m",
    )
    minimum_pedestrian_distance_m = _minimum_telemetry_value(
        rows,
        "pedestrian_distance_m",
    )

    pedestrian_started = any(
        event.get("type") == "pedestrian_started" for event in events or []
    ) or any(_as_bool(row.get("pedestrian_active")) for row in rows)
    pedestrian_speed_mps = _as_float(
        (pedestrian_config or {}).get("speed_mps")
    )

    weather_visibility_risk, weather_components = _weather_visibility_risk(
        weather_config,
        parameters,
    )
    components = {
        "collision": 1.0 if int(collision_count) > 0 else 0.0,
        "ttc": normalized_low_value_risk(
            minimum_ttc_seconds,
            parameters["ttc"]["critical_seconds"],
            parameters["ttc"]["safe_seconds"],
        ),
        "lead_gap": normalized_low_value_risk(
            minimum_lead_gap_m,
            parameters["lead_gap"]["critical_m"],
            parameters["lead_gap"]["safe_m"],
        ),
        "pedestrian_distance": normalized_low_value_risk(
            minimum_pedestrian_distance_m,
            parameters["pedestrian_distance"]["critical_m"],
            parameters["pedestrian_distance"]["safe_m"],
        ),
        "pedestrian_speed": (
            normalized_high_value_risk(
                pedestrian_speed_mps,
                parameters["pedestrian_speed"]["safe_mps"],
                parameters["pedestrian_speed"]["critical_mps"],
            )
            if pedestrian_started
            else 0.0
        ),
        "weather_visibility": weather_visibility_risk,
    }
    weights = {
        name: float(parameters["weights"][name]) for name in components
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("风险 V2 权重之和必须大于 0")

    score = round(
        100.0
        * sum(components[name] * weights[name] for name in components)
        / total_weight,
        3,
    )

    lead_brake_elapsed_seconds = _first_event_time(
        events,
        "lead_vehicle_brake",
    )
    pedestrian_start_seconds = _first_event_time(
        events,
        "pedestrian_started",
    )
    pedestrian_finish_seconds = _first_event_time(
        events,
        "pedestrian_finished",
    )
    minimum_ttc_after_brake = None
    minimum_gap_after_brake = None
    if lead_brake_elapsed_seconds is not None:
        post_brake_rows = [
            row
            for row in rows
            if (_as_float(row.get("elapsed_seconds")) or -1.0)
            >= lead_brake_elapsed_seconds
        ]
        minimum_ttc_after_brake = _minimum_telemetry_value(
            post_brake_rows,
            "ttc_seconds",
        )
        minimum_gap_after_brake = _minimum_telemetry_value(
            post_brake_rows,
            "lead_gap_distance_m",
        )

    pedestrian_crossing_duration_seconds = None
    if (
        pedestrian_start_seconds is not None
        and pedestrian_finish_seconds is not None
    ):
        pedestrian_crossing_duration_seconds = max(
            0.0,
            pedestrian_finish_seconds - pedestrian_start_seconds,
        )

    duration_seconds = _as_float(
        (scenario_config or {}).get("duration_seconds")
    )
    diagnostics = {
        "minimum_ttc_seconds": minimum_ttc_seconds,
        "minimum_lead_gap_m": minimum_lead_gap_m,
        "minimum_pedestrian_distance_m": minimum_pedestrian_distance_m,
        "pedestrian_speed_mps": pedestrian_speed_mps,
        "pedestrian_crossing_duration_seconds": (
            pedestrian_crossing_duration_seconds
        ),
        "lead_brake_elapsed_seconds": lead_brake_elapsed_seconds,
        "minimum_ttc_after_brake_seconds": minimum_ttc_after_brake,
        "minimum_gap_after_brake_m": minimum_gap_after_brake,
        "scenario_duration_seconds": duration_seconds,
        "weather_components": weather_components,
    }

    return {
        "method": "heuristic_v2",
        "score": score,
        "level": _level_from_score(score, parameters["levels"]),
        "components": {
            name: round(value, 4) for name, value in components.items()
        },
        "weights": weights,
        "diagnostics": {
            name: (
                round(value, 4) if isinstance(value, float) else value
            )
            for name, value in diagnostics.items()
        },
        "notes": [
            "weather_visibility 为基于 CARLA 天气参数的暴露代理，不等同于图像实测能见度",
            "评分用于同一场景族内部筛选，不替代法规或功能安全认证",
        ],
    }


def evaluate_telemetry_risk(
    telemetry_rows,
    collision_count,
    risk_config,
    weather_config=None,
    pedestrian_config=None,
    scenario_config=None,
    events=None,
):
    rows = list(telemetry_rows or [])
    method = (risk_config or {}).get("method", "heuristic_v1")
    if method == "heuristic_v2":
        return evaluate_risk_v2(
            rows,
            collision_count,
            risk_config,
            weather_config=weather_config,
            pedestrian_config=pedestrian_config,
            scenario_config=scenario_config,
            events=events,
        )
    if method != "heuristic_v1":
        raise ValueError(f"不支持的风险评估方法: {method}")

    return evaluate_risk(
        _minimum_telemetry_value(rows, "ttc_seconds"),
        _minimum_telemetry_value(rows, "lead_gap_distance_m"),
        _minimum_telemetry_value(rows, "pedestrian_distance_m"),
        collision_count,
        risk_config,
    )


def write_telemetry_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TELEMETRY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: "" if row.get(field) is None else row.get(field)
                    for field in TELEMETRY_FIELDS
                }
            )
