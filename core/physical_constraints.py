"""场景参数级物理约束与可解释报告。

该模块只使用生成前已知的场景参数，不能替代 CARLA 运行、碰撞检测或风险
模型。硬约束用于拦截明显不可执行的时间/速度组合；风险边界条件只记为
warning，避免把有意构造的危险场景误判为非法。
"""

import json
import math
from pathlib import Path


PHYSICAL_CONSTRAINTS_VERSION = "physical_constraints_v1"
NOMINAL_EGO_SPEED_MPS = 29.0 / 3.6


def _number(record, path):
    value = record
    for name in path.split("."):
        if not isinstance(value, dict) or name not in value:
            raise ValueError(f"{path}: 缺少字段")
        value = value[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: 必须为有限数值")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{path}: 必须为有限数值")
    return value


def _error(errors, path, message):
    errors.append({"path": path, "code": message[0], "message": message[1]})


def evaluate_physical_constraints(record):
    """评估一条 generated_scenario 记录的参数级物理约束。

    返回值中的 ``valid`` 只表示参数组合是否通过硬约束；``warnings`` 是
    危险边界或名义速度近似产生的提示，不能解释为实测风险。
    """

    errors = []
    warnings = []
    metrics = {"nominal_ego_speed_mps": NOMINAL_EGO_SPEED_MPS}
    paths = (
        "scenario.duration_seconds",
        "lead_vehicle.initial_distance_m",
        "lead_vehicle.brake_trigger_seconds",
        "lead_vehicle.brake_intensity",
        "pedestrian.forward_distance_m",
        "pedestrian.roadside_offset_m",
        "pedestrian.trigger_seconds",
        "pedestrian.speed_mps",
    )
    values = {}
    for path in paths:
        try:
            values[path] = _number(record, path)
        except ValueError as error:
            _error(errors, path, ("missing_or_nonfinite", str(error)))

    if errors:
        return {
            "version": PHYSICAL_CONSTRAINTS_VERSION,
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "metrics": metrics,
        }

    duration = values["scenario.duration_seconds"]
    lead_distance = values["lead_vehicle.initial_distance_m"]
    brake_trigger = values["lead_vehicle.brake_trigger_seconds"]
    brake_intensity = values["lead_vehicle.brake_intensity"]
    pedestrian_distance = values["pedestrian.forward_distance_m"]
    roadside_offset = values["pedestrian.roadside_offset_m"]
    pedestrian_trigger = values["pedestrian.trigger_seconds"]
    pedestrian_speed = values["pedestrian.speed_mps"]
    nominal_speed = NOMINAL_EGO_SPEED_MPS

    if duration <= 0:
        _error(errors, "scenario.duration_seconds", ("nonpositive_duration", "仿真时长必须大于 0 秒"))
    if lead_distance <= 0:
        _error(errors, "lead_vehicle.initial_distance_m", ("nonpositive_distance", "前车初始距离必须大于 0 米"))
    if not 0 <= brake_trigger <= duration:
        _error(errors, "lead_vehicle.brake_trigger_seconds", ("trigger_out_of_window", "前车急刹触发时间必须位于仿真窗口内"))
    if not 0 <= pedestrian_trigger <= duration:
        _error(errors, "pedestrian.trigger_seconds", ("trigger_out_of_window", "行人触发时间必须位于仿真窗口内"))
    if brake_intensity <= 0:
        _error(errors, "lead_vehicle.brake_intensity", ("nonpositive_brake_intensity", "前车制动强度必须大于 0"))
    if pedestrian_distance <= 0 or roadside_offset <= 0 or pedestrian_speed <= 0:
        _error(errors, "pedestrian", ("nonpositive_kinematic_parameter", "行人距离、道路偏移和速度必须大于 0"))

    crossing_time = 2.0 * roadside_offset / pedestrian_speed
    crossing_finish = pedestrian_trigger + crossing_time
    ego_time_to_lead = lead_distance / nominal_speed
    lead_distance_at_brake = lead_distance - nominal_speed * brake_trigger
    lead_brake_time_margin = ego_time_to_lead - brake_trigger
    ego_time_to_pedestrian = pedestrian_distance / nominal_speed
    pedestrian_distance_at_trigger = pedestrian_distance - nominal_speed * pedestrian_trigger
    pedestrian_trigger_time_margin = ego_time_to_pedestrian - pedestrian_trigger
    hazard_trigger_gap = abs(brake_trigger - pedestrian_trigger)
    hazard_spatial_gap = abs(pedestrian_distance - lead_distance)
    available_gap = max(lead_distance_at_brake, 0.5)
    braking_demand = brake_intensity * nominal_speed / available_gap

    metrics.update(
        {
            "pedestrian_crossing_time_s": crossing_time,
            "pedestrian_finish_time_s": crossing_finish,
            "pedestrian_finish_margin_s": duration - crossing_finish,
            "ego_time_to_lead_s": ego_time_to_lead,
            "lead_distance_at_brake_m": lead_distance_at_brake,
            "lead_brake_time_margin_s": lead_brake_time_margin,
            "ego_time_to_pedestrian_s": ego_time_to_pedestrian,
            "pedestrian_distance_at_trigger_m": pedestrian_distance_at_trigger,
            "pedestrian_trigger_time_margin_s": pedestrian_trigger_time_margin,
            "hazard_trigger_gap_s": hazard_trigger_gap,
            "hazard_spatial_gap_m": hazard_spatial_gap,
            "lead_braking_demand_index": braking_demand,
        }
    )

    if crossing_finish > duration:
        _error(
            errors,
            "pedestrian",
            ("crossing_after_scene_end", "按道路两侧距离和速度估算，行人无法在场景结束前完成横穿"),
        )
    if crossing_finish > duration - 1.0:
        warnings.append(
            {
                "path": "pedestrian",
                "code": "small_crossing_finish_margin",
                "message": "行人横穿完成距离场景结束不足 1 秒",
            }
        )
    if lead_distance_at_brake <= 0:
        warnings.append(
            {
                "path": "lead_vehicle",
                "code": "nominal_overlap_at_brake",
                "message": "按名义主车速度，主车在前车急刹时已到达前车初始位置附近；这是危险边界提示，不是参数非法",
            }
        )
    if pedestrian_distance_at_trigger <= 0:
        warnings.append(
            {
                "path": "pedestrian",
                "code": "nominal_pedestrian_point_passed",
                "message": "按名义主车速度，行人触发时主车可能已通过横穿点；需要 CARLA 实测确认交互是否成立",
            }
        )
    if hazard_trigger_gap > 4.0:
        warnings.append(
            {
                "path": "scenario",
                "code": "hazard_trigger_gap",
                "message": "前车急刹与行人触发时间间隔超过 4 秒，多危险叠加可能较弱",
            }
        )

    return {
        "version": PHYSICAL_CONSTRAINTS_VERSION,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }


def build_physical_constraint_report(records, source=None):
    """对多条记录生成可审计的 JSON 报告。"""

    results = []
    valid_count = 0
    warning_count = 0
    for line_number, record in records:
        result = evaluate_physical_constraints(record)
        if result["valid"]:
            valid_count += 1
        warning_count += len(result["warnings"])
        results.append(
            {
                "line_number": line_number,
                "sample_id": record.get("sample_id"),
                **result,
            }
        )
    return {
        "format": "physical_constraint_report_v1",
        "constraint_version": PHYSICAL_CONSTRAINTS_VERSION,
        "source": str(source) if source is not None else None,
        "record_count": len(results),
        "valid_count": valid_count,
        "invalid_count": len(results) - valid_count,
        "warning_count": warning_count,
        "results": results,
    }


def load_json_records(path):
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if line.strip():
                    records.append((line_number, json.loads(line)))
        return records
    with path.open("r", encoding="utf-8") as file:
        return [(1, json.load(file))]
