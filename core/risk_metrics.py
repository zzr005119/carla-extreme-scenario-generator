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
    "collision_count",
]


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

    levels = config.get("levels", {})
    medium_threshold = float(levels.get("medium", 25.0))
    high_threshold = float(levels.get("high", 50.0))
    critical_threshold = float(levels.get("critical", 75.0))
    if score >= critical_threshold:
        level = "critical"
    elif score >= high_threshold:
        level = "high"
    elif score >= medium_threshold:
        level = "medium"
    else:
        level = "low"

    return {
        "method": config.get("method", "heuristic_v1"),
        "score": score,
        "level": level,
        "components": {
            name: round(value, 4) for name, value in components.items()
        },
        "weights": weights,
    }


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
