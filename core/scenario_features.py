"""参数级场景模型的统一特征编码与记录构建。"""

import json
from datetime import datetime

import numpy as np

from core.scenario_validator import derive_weather_tags, require_valid_scenario


RISK_LEVELS = ("low", "medium", "high", "critical")
WEATHER_TAGS = (
    "rain",
    "heavy_rain",
    "fog",
    "dense_fog",
    "night",
    "day",
    "wet_road",
    "strong_wind",
)
HAZARD_TAGS = ("lead_vehicle_braking", "pedestrian_crossing")

# 第一版模型只学习种子数据实际覆盖的 15 维连续参数。
FEATURE_SPECS = (
    ("weather.cloudiness", 35.0, 100.0),
    ("weather.precipitation", 20.0, 100.0),
    ("weather.precipitation_deposits", 20.0, 100.0),
    ("weather.wind_intensity", 5.0, 100.0),
    ("weather.fog_density", 15.0, 100.0),
    ("weather.fog_distance", 3.0, 60.0),
    ("weather.sun_altitude_angle", -30.0, 20.0),
    ("weather.wetness", 30.0, 100.0),
    ("lead_vehicle.initial_distance_m", 12.0, 46.0),
    ("lead_vehicle.brake_trigger_seconds", 2.8, 10.0),
    ("lead_vehicle.brake_intensity", 0.55, 1.0),
    ("pedestrian.forward_distance_m", 18.0, 45.0),
    ("pedestrian.roadside_offset_m", 5.0, 9.0),
    ("pedestrian.trigger_seconds", 1.8, 7.5),
    ("pedestrian.speed_mps", 2.0, 8.0),
)
FEATURE_NAMES = tuple(spec[0] for spec in FEATURE_SPECS)
FEATURE_LOW = np.asarray([spec[1] for spec in FEATURE_SPECS], dtype=np.float64)
FEATURE_HIGH = np.asarray([spec[2] for spec in FEATURE_SPECS], dtype=np.float64)
FEATURE_DIM = len(FEATURE_SPECS)
CONDITION_DIM = len(RISK_LEVELS) + len(WEATHER_TAGS)
FEATURE_INDEX = {name: index for index, (name, _low, _high) in enumerate(FEATURE_SPECS)}


def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 解析失败: {exc}") from exc
    return records


def _nested_value(record, dotted_name):
    value = record
    for part in dotted_name.split("."):
        value = value[part]
    return float(value)


def parameter_vector(record):
    return np.asarray(
        [_nested_value(record, name) for name in FEATURE_NAMES],
        dtype=np.float64,
    )


def normalize_vector(values, clip=False):
    values = np.asarray(values, dtype=np.float64)
    if values.shape[-1] != FEATURE_DIM:
        raise ValueError(f"特征维度必须为 {FEATURE_DIM}，实际为 {values.shape[-1]}")
    normalized = (values - FEATURE_LOW) / (FEATURE_HIGH - FEATURE_LOW)
    return np.clip(normalized, 0.0, 1.0) if clip else normalized


def denormalize_vector(values, clip=True):
    values = np.asarray(values, dtype=np.float64)
    if values.shape[-1] != FEATURE_DIM:
        raise ValueError(f"特征维度必须为 {FEATURE_DIM}，实际为 {values.shape[-1]}")
    if clip:
        values = np.clip(values, 0.0, 1.0)
    return FEATURE_LOW + values * (FEATURE_HIGH - FEATURE_LOW)


def encode_record(record):
    return normalize_vector(parameter_vector(record), clip=True)


def validate_requested_conditions(target_risk_level, weather_tags):
    if target_risk_level not in RISK_LEVELS:
        raise ValueError(f"未知风险等级: {target_risk_level}")
    unknown = sorted(set(weather_tags) - set(WEATHER_TAGS))
    if unknown:
        raise ValueError(f"未知天气标签: {unknown}")
    if "day" in weather_tags and "night" in weather_tags:
        raise ValueError("天气条件不能同时包含 day 和 night")
    if "rain" in weather_tags and "heavy_rain" in weather_tags:
        raise ValueError("rain 与 heavy_rain 只需指定一个")
    if "fog" in weather_tags and "dense_fog" in weather_tags:
        raise ValueError("fog 与 dense_fog 只需指定一个")


def condition_vector(target_risk_level, weather_tags):
    weather_tags = tuple(dict.fromkeys(weather_tags))
    validate_requested_conditions(target_risk_level, weather_tags)
    values = np.zeros(CONDITION_DIM, dtype=np.float64)
    values[RISK_LEVELS.index(target_risk_level)] = 1.0
    offset = len(RISK_LEVELS)
    for tag in weather_tags:
        values[offset + WEATHER_TAGS.index(tag)] = 1.0
    return values


def encode_record_condition(record):
    conditions = record["conditions"]
    return condition_vector(
        conditions["target_risk_level"],
        conditions["weather_tags"],
    )


def records_to_arrays(records):
    features = np.asarray([encode_record(record) for record in records], dtype=np.float32)
    conditions = np.asarray(
        [encode_record_condition(record) for record in records],
        dtype=np.float32,
    )
    return features, conditions


def vector_to_sections(normalized_values):
    values = denormalize_vector(normalized_values, clip=True)
    flat = dict(zip(FEATURE_NAMES, values.tolist()))
    return {
        "weather": {
            name.split(".", 1)[1]: round(value, 3)
            for name, value in flat.items()
            if name.startswith("weather.")
        },
        "lead_vehicle": {
            name.split(".", 1)[1]: round(value, 3)
            for name, value in flat.items()
            if name.startswith("lead_vehicle.")
        },
        "pedestrian": {
            name.split(".", 1)[1]: round(value, 3)
            for name, value in flat.items()
            if name.startswith("pedestrian.")
        },
    }


def weather_request_satisfied(requested_tags, actual_tags):
    actual = set(actual_tags)
    for tag in requested_tags:
        if tag == "rain":
            if not ({"rain", "heavy_rain"} & actual):
                return False
        elif tag == "fog":
            if not ({"fog", "dense_fog"} & actual):
                return False
        elif tag not in actual:
            return False
    return True


def project_requested_weather_constraints(normalized_values, requested_tags):
    """Project a candidate onto the requested weather-label constraints.

    The policy still supplies the original 15-dimensional action.  This helper
    only moves the smallest number of weather parameters needed to keep the
    requested condition labels true after a bounded action.  It returns an
    auditable description of every changed field so evaluation can distinguish
    a constrained candidate from an unconstrained policy output.
    """
    values = np.asarray(normalized_values, dtype=np.float64).reshape(-1)
    if values.shape != (FEATURE_DIM,):
        raise ValueError(f"特征维度必须为 {FEATURE_DIM}，实际为 {values.shape}")
    requested = tuple(dict.fromkeys(requested_tags))
    validate_requested_conditions("low", requested)
    projected = np.clip(values, 0.0, 1.0).copy()
    initial_tags = derive_weather_tags(vector_to_sections(projected)["weather"])
    changes = []

    # Each option is (feature name, physical target, direction).  For labels
    # with aliases (rain/fog), the least-displacing option is selected.
    options = {
        "rain": (("weather.precipitation", 20.0, "min"),),
        "heavy_rain": (("weather.precipitation", 80.0, "min"),),
        "fog": (("weather.fog_density", 30.0, "min"),
                ("weather.fog_distance", 30.0, "max")),
        "dense_fog": (("weather.fog_density", 85.0, "min"),
                      ("weather.fog_distance", 8.0, "max")),
        "night": (("weather.sun_altitude_angle", -0.001, "max"),),
        "day": (("weather.sun_altitude_angle", 0.0, "min"),),
        "wet_road": (("weather.wetness", 60.0, "min"),),
        "strong_wind": (("weather.wind_intensity", 70.0, "min"),),
    }

    for tag in requested:
        actual = derive_weather_tags(vector_to_sections(projected)["weather"])
        if weather_request_satisfied(requested, actual):
            break
        if tag in actual or weather_request_satisfied((tag,), actual):
            continue
        candidates = []
        for feature_name, target, direction in options.get(tag, ()):
            index = FEATURE_INDEX[feature_name]
            current_physical = float(denormalize_vector(projected, clip=True)[index])
            if direction == "min":
                target_physical = max(current_physical, float(target))
            else:
                target_physical = min(current_physical, float(target))
            trial = projected.copy()
            trial[index] = float(
                np.clip(
                    (target_physical - FEATURE_LOW[index])
                    / (FEATURE_HIGH[index] - FEATURE_LOW[index]),
                    0.0,
                    1.0,
                )
            )
            trial_tags = derive_weather_tags(vector_to_sections(trial)["weather"])
            if weather_request_satisfied((tag,), trial_tags):
                displacement = abs(float(trial[index]) - float(projected[index]))
                candidates.append((displacement, feature_name, target_physical, trial))
        if not candidates:
            continue
        _displacement, feature_name, target_physical, selected = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        index = FEATURE_INDEX[feature_name]
        before_physical = float(denormalize_vector(projected, clip=True)[index])
        projected = selected
        after_physical = float(denormalize_vector(projected, clip=True)[index])
        changes.append(
            {
                "tag": tag,
                "feature": feature_name,
                "before": round(before_physical, 6),
                "after": round(after_physical, 6),
                "target": round(float(target_physical), 6),
            }
        )

    final_tags = derive_weather_tags(vector_to_sections(projected)["weather"])
    return projected.tolist(), {
        "enabled": True,
        "applied": bool(changes),
        "requested_tags": list(requested),
        "before_tags": list(initial_tags),
        "raw_satisfied": weather_request_satisfied(requested, initial_tags),
        "after_tags": list(final_tags),
        "changed_fields": changes,
        "satisfied": weather_request_satisfied(requested, final_tags),
    }


def condition_text_zh(target_risk_level, weather_tags):
    tag_names = {
        "rain": "降雨",
        "heavy_rain": "暴雨",
        "fog": "雾天",
        "dense_fog": "浓雾",
        "night": "夜间",
        "day": "日间",
        "wet_road": "湿滑路面",
        "strong_wind": "强风",
    }
    level_names = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险",
        "critical": "临界风险",
    }
    weather_text = "、".join(tag_names[tag] for tag in weather_tags)
    return f"{weather_text}条件下，前车急刹与行人横穿叠加的{level_names[target_risk_level]}场景"


def build_generated_record(
    normalized_values,
    target_risk_level,
    requested_weather_tags,
    sample_id,
    generator,
    generator_seed,
    source_kind="model_generated",
    duration_seconds=20.0,
    traffic_manager_seed=None,
    created_at=None,
):
    requested_weather_tags = tuple(dict.fromkeys(requested_weather_tags))
    validate_requested_conditions(target_risk_level, requested_weather_tags)
    sections = vector_to_sections(normalized_values)
    weather_tags = derive_weather_tags(sections["weather"])
    if not weather_request_satisfied(requested_weather_tags, weather_tags):
        raise ValueError(
            f"生成天气 {weather_tags} 不满足请求 {list(requested_weather_tags)}"
        )
    sections["pedestrian"]["spawn_z_offset_m"] = 0.5
    if traffic_manager_seed is None:
        traffic_manager_seed = int(generator_seed) % 2147483648
    if created_at is None:
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    record = {
        "schema_version": "1.0",
        "sample_id": sample_id,
        "family": "multi_hazard_parameter_v1",
        "conditions": {
            "target_risk_level": target_risk_level,
            "weather_tags": weather_tags,
            "hazard_tags": list(HAZARD_TAGS),
            "condition_text_zh": condition_text_zh(
                target_risk_level,
                weather_tags,
            ),
        },
        "scenario": {
            "duration_seconds": float(duration_seconds),
            "traffic_manager_seed": traffic_manager_seed,
        },
        **sections,
        "observed_risk": {
            "status": "not_simulated",
            "method": None,
            "score": None,
            "level": None,
            "run_dir": None,
        },
        "provenance": {
            "source_kind": source_kind,
            "generator": generator,
            "generator_seed": int(generator_seed),
            "split": "inference",
            "created_at": created_at,
        },
    }
    require_valid_scenario(record)
    return record
