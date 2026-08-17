"""从场景参数计算运行前可知的物理交互派生特征。"""

import numpy as np

from core.scenario_features import (
    FEATURE_DIM,
    FEATURE_HIGH,
    FEATURE_LOW,
    FEATURE_NAMES,
)


PHYSICAL_FEATURE_VERSION = "physical_interaction_v1"
NOMINAL_EGO_SPEED_KMH = 29.0
NOMINAL_EGO_SPEED_MPS = NOMINAL_EGO_SPEED_KMH / 3.6
SCENARIO_DURATION_SECONDS = 20.0

PHYSICAL_FEATURE_NAMES = (
    "derived_ego_time_to_lead_s",
    "derived_lead_distance_at_brake_m",
    "derived_lead_brake_time_margin_s",
    "derived_ego_time_to_pedestrian_s",
    "derived_pedestrian_distance_at_trigger_m",
    "derived_pedestrian_trigger_time_margin_s",
    "derived_hazard_trigger_gap_s",
    "derived_hazard_trigger_gap_ratio",
    "derived_pedestrian_speed_ratio",
    "derived_lead_braking_demand_index",
    "derived_hazard_spatial_gap_m",
    "derived_weather_visibility_severity",
)


def _as_feature_matrix(values):
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or matrix.shape[1] != FEATURE_DIM:
        raise ValueError(
            f"输入必须是形状 (n, {FEATURE_DIM}) 的参数特征矩阵，"
            f"实际为 {matrix.shape}"
        )
    return matrix


def _clip01(values):
    return np.clip(values, 0.0, 1.0)


def _normalized_high_risk(values, safe_value, critical_value):
    return _clip01(
        (values - float(safe_value))
        / (float(critical_value) - float(safe_value))
    )


def _normalized_low_risk(values, critical_value, safe_value):
    return _clip01(
        (float(safe_value) - values)
        / (float(safe_value) - float(critical_value))
    )


def physical_feature_matrix(normalized_values):
    """将 15 维归一化参数转换为物理交互特征矩阵。"""

    normalized = _as_feature_matrix(normalized_values)
    raw = FEATURE_LOW + normalized * (FEATURE_HIGH - FEATURE_LOW)
    index = {name: position for position, name in enumerate(FEATURE_NAMES)}

    cloudiness = raw[:, index["weather.cloudiness"]]
    precipitation = raw[:, index["weather.precipitation"]]
    fog_density = raw[:, index["weather.fog_density"]]
    fog_distance = raw[:, index["weather.fog_distance"]]
    sun_altitude = raw[:, index["weather.sun_altitude_angle"]]
    wetness = raw[:, index["weather.wetness"]]
    lead_distance = raw[:, index["lead_vehicle.initial_distance_m"]]
    brake_trigger = raw[:, index["lead_vehicle.brake_trigger_seconds"]]
    brake_intensity = raw[:, index["lead_vehicle.brake_intensity"]]
    pedestrian_distance = raw[:, index["pedestrian.forward_distance_m"]]
    pedestrian_trigger = raw[:, index["pedestrian.trigger_seconds"]]
    pedestrian_speed = raw[:, index["pedestrian.speed_mps"]]

    ego_time_to_lead = lead_distance / NOMINAL_EGO_SPEED_MPS
    lead_distance_at_brake = (
        lead_distance - NOMINAL_EGO_SPEED_MPS * brake_trigger
    )
    lead_brake_time_margin = ego_time_to_lead - brake_trigger

    ego_time_to_pedestrian = pedestrian_distance / NOMINAL_EGO_SPEED_MPS
    pedestrian_distance_at_trigger = (
        pedestrian_distance
        - NOMINAL_EGO_SPEED_MPS * pedestrian_trigger
    )
    pedestrian_trigger_time_margin = (
        ego_time_to_pedestrian - pedestrian_trigger
    )

    hazard_trigger_gap = np.abs(brake_trigger - pedestrian_trigger)
    hazard_trigger_gap_ratio = hazard_trigger_gap / SCENARIO_DURATION_SECONDS
    pedestrian_speed_ratio = pedestrian_speed / NOMINAL_EGO_SPEED_MPS

    available_gap = np.maximum(lead_distance_at_brake, 0.5)
    lead_braking_demand_index = (
        brake_intensity * NOMINAL_EGO_SPEED_MPS / available_gap
    )
    hazard_spatial_gap = np.abs(pedestrian_distance - lead_distance)

    visibility_components = np.column_stack(
        (
            _normalized_high_risk(fog_density, 60.0, 95.0),
            _normalized_low_risk(fog_distance, 5.0, 30.0),
            _normalized_high_risk(precipitation, 60.0, 100.0),
            _normalized_low_risk(sun_altitude, -15.0, 10.0),
            _normalized_high_risk(wetness, 60.0, 100.0),
            _normalized_high_risk(cloudiness, 60.0, 100.0),
        )
    )
    weather_visibility_severity = np.column_stack(
        (
            visibility_components[:, 0],
            visibility_components[:, 1],
            visibility_components[:, 2],
            visibility_components[:, 3],
            visibility_components[:, 4],
            visibility_components[:, 5],
        )
    ).mean(axis=1)

    return np.column_stack(
        (
            ego_time_to_lead,
            lead_distance_at_brake,
            lead_brake_time_margin,
            ego_time_to_pedestrian,
            pedestrian_distance_at_trigger,
            pedestrian_trigger_time_margin,
            hazard_trigger_gap,
            hazard_trigger_gap_ratio,
            pedestrian_speed_ratio,
            lead_braking_demand_index,
            hazard_spatial_gap,
            weather_visibility_severity,
        )
    )


def physical_feature_names():
    return PHYSICAL_FEATURE_NAMES
