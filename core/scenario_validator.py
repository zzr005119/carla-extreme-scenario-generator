"""生成式场景记录校验与 CARLA 配置编译。"""

import argparse
import copy
import json
import math
import os
import re


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "generated_scenario.schema.json",
)
DEFAULT_BASE_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "multi_hazard_rainy_night.json",
)


class ScenarioValidationError(ValueError):
    """场景记录未通过结构或语义校验。"""


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _type_matches(value, expected_type):
    if expected_type == "null":
        return value is None
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    return False


def _validate_schema_node(value, schema, path, errors):
    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not any(_type_matches(value, item) for item in expected_types):
            errors.append(
                f"{path}: 类型错误，应为 {'/'.join(expected_types)}"
            )
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 必须等于 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 值 {value!r} 不在允许范围内")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required_name in schema.get("required", []):
            if required_name not in value:
                errors.append(f"{path}.{required_name}: 缺少必填字段")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}.{name}: 不允许的额外字段")
        for name, child_value in value.items():
            child_schema = properties.get(name)
            if child_schema is not None:
                _validate_schema_node(
                    child_value,
                    child_schema,
                    f"{path}.{name}",
                    errors,
                )

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(
                f"{path}: 元素数量不能少于 {schema['minItems']}"
            )
        if schema.get("uniqueItems"):
            serialized = [
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in value
            ]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: 元素不能重复")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema_node(
                    item,
                    item_schema,
                    f"{path}[{index}]",
                    errors,
                )

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(
                f"{path}: 字符长度不能少于 {schema['minLength']}"
            )
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            errors.append(f"{path}: 不符合格式 {pattern}")

    if _type_matches(value, "number"):
        numeric_value = float(value)
        if "minimum" in schema and numeric_value < float(schema["minimum"]):
            errors.append(f"{path}: 不能小于 {schema['minimum']}")
        if "maximum" in schema and numeric_value > float(schema["maximum"]):
            errors.append(f"{path}: 不能大于 {schema['maximum']}")


def _semantic_validation(record):
    errors = []
    warnings = []
    duration = float(record["scenario"]["duration_seconds"])
    brake_time = float(record["lead_vehicle"]["brake_trigger_seconds"])
    pedestrian_time = float(record["pedestrian"]["trigger_seconds"])
    pedestrian_speed = float(record["pedestrian"]["speed_mps"])
    roadside_offset = float(record["pedestrian"]["roadside_offset_m"])

    if brake_time > duration - 1.0:
        errors.append("$.lead_vehicle.brake_trigger_seconds: 急刹后至少保留 1 秒仿真")
    estimated_crossing_seconds = 2.0 * roadside_offset / pedestrian_speed
    if pedestrian_time + estimated_crossing_seconds > duration:
        errors.append(
            "$.pedestrian: 按道路两侧距离估算，行人无法在场景结束前完成横穿"
        )

    conditions = record["conditions"]
    weather = record["weather"]
    tags = set(conditions["weather_tags"])
    expected_tags = set(derive_weather_tags(weather))
    if tags != expected_tags:
        errors.append(
            "$.conditions.weather_tags: 与天气参数推导结果不一致，"
            f"应为 {sorted(expected_tags)}"
        )

    hazard_tags = set(conditions["hazard_tags"])
    expected_hazards = {
        "lead_vehicle_braking",
        "pedestrian_crossing",
    }
    if hazard_tags != expected_hazards:
        errors.append(
            "$.conditions.hazard_tags: multi_hazard_parameter_v1 必须包含前车急刹和行人横穿"
        )

    target_level = conditions["target_risk_level"]
    initial_distance = float(record["lead_vehicle"]["initial_distance_m"])
    if target_level == "critical" and initial_distance > 24.0:
        warnings.append("临界风险样本的前车初始距离偏大，需通过 CARLA 实测确认")
    if target_level == "low" and (
        float(weather["fog_density"]) >= 85.0
        or pedestrian_speed >= 5.5
        or initial_distance <= 20.0
    ):
        warnings.append("低风险目标包含高危参数，条件标签可能不稳定")

    observed = record["observed_risk"]
    if observed["status"] == "not_simulated":
        if any(
            observed[name] is not None
            for name in ("method", "score", "level", "run_dir")
        ):
            errors.append(
                "$.observed_risk: not_simulated 状态下实测字段必须为 null"
            )
    elif observed["status"] == "completed":
        if any(
            observed[name] is None
            for name in ("method", "score", "level", "run_dir")
        ):
            errors.append(
                "$.observed_risk: completed 状态下实测字段不能为空"
            )

    return errors, warnings


def validate_scenario_record(record, schema=None, schema_path=DEFAULT_SCHEMA_PATH):
    if schema is None:
        schema = load_json(schema_path)
    errors = []
    _validate_schema_node(record, schema, "$", errors)
    warnings = []
    if not errors:
        semantic_errors, warnings = _semantic_validation(record)
        errors.extend(semantic_errors)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def require_valid_scenario(record, schema=None, schema_path=DEFAULT_SCHEMA_PATH):
    result = validate_scenario_record(record, schema=schema, schema_path=schema_path)
    if not result["valid"]:
        raise ScenarioValidationError("\n".join(result["errors"]))
    return result


def derive_weather_tags(weather):
    tags = []
    precipitation = float(weather["precipitation"])
    fog_density = float(weather["fog_density"])
    fog_distance = float(weather["fog_distance"])
    sun_altitude = float(weather["sun_altitude_angle"])
    wetness = float(weather["wetness"])
    wind = float(weather["wind_intensity"])

    if precipitation >= 80.0:
        tags.append("heavy_rain")
    elif precipitation >= 20.0:
        tags.append("rain")
    if fog_density >= 85.0 or fog_distance <= 8.0:
        tags.append("dense_fog")
    elif fog_density >= 30.0 or fog_distance <= 30.0:
        tags.append("fog")
    tags.append("night" if sun_altitude < 0.0 else "day")
    if wetness >= 60.0:
        tags.append("wet_road")
    if wind >= 70.0:
        tags.append("strong_wind")
    return tags


def compile_carla_config(record, base_config):
    require_valid_scenario(record)
    compiled = copy.deepcopy(base_config)
    compiled["scenario"]["name"] = record["sample_id"]
    compiled["scenario"]["duration_seconds"] = record["scenario"][
        "duration_seconds"
    ]
    compiled["scenario"]["traffic_manager_seed"] = record["scenario"][
        "traffic_manager_seed"
    ]
    compiled["weather"].update(record["weather"])
    compiled["lead_vehicle"].update(record["lead_vehicle"])
    compiled["pedestrian"].update(record["pedestrian"])
    return compiled


def rebase_output_root(config, base_config_path, destination_config_path):
    output_root = config["output"]["root"]
    if os.path.isabs(output_root):
        return config

    base_config_dir = os.path.dirname(os.path.abspath(base_config_path))
    destination_dir = os.path.dirname(os.path.abspath(destination_config_path))
    absolute_output_root = os.path.abspath(
        os.path.join(base_config_dir, output_root)
    )
    try:
        config["output"]["root"] = os.path.relpath(
            absolute_output_root,
            destination_dir,
        )
    except ValueError:
        config["output"]["root"] = absolute_output_root
    return config


def _iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if stripped:
                yield line_number, json.loads(stripped)


def parse_args():
    parser = argparse.ArgumentParser(description="校验生成式场景记录")
    parser.add_argument("path", help="单个 JSON 或 JSONL 文件")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG_PATH)
    parser.add_argument("--compiled-output", help="将单个记录编译为 CARLA JSON")
    return parser.parse_args()


def main():
    args = parse_args()
    path = os.path.abspath(args.path)
    schema = load_json(os.path.abspath(args.schema))
    records = []
    if path.lower().endswith(".jsonl"):
        records = list(_iter_jsonl(path))
    else:
        records = [(1, load_json(path))]

    warning_count = 0
    for line_number, record in records:
        result = validate_scenario_record(record, schema=schema)
        if not result["valid"]:
            for error in result["errors"]:
                print(f"[INVALID line={line_number}] {error}")
            return 1
        warning_count += len(result["warnings"])
        for warning in result["warnings"]:
            print(f"[WARNING line={line_number}] {warning}")

    if args.compiled_output:
        if len(records) != 1:
            raise ValueError("--compiled-output 仅支持单个 JSON 记录")
        base_config = load_json(os.path.abspath(args.base_config))
        compiled = compile_carla_config(records[0][1], base_config)
        output_path = os.path.abspath(args.compiled_output)
        rebase_output_root(compiled, args.base_config, output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(compiled, file, ensure_ascii=False, indent=2)
        print(f"[COMPILED] {output_path}")

    print(
        f"[VALID] {path} | records={len(records)} | warnings={warning_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
