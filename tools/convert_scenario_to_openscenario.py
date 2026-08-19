"""将单条自定义场景记录转换为 OpenSCENARIO 1.0 交换文件和 CARLA 配置。"""

import argparse
import copy
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    load_json,
    rebase_output_root,
    require_valid_scenario,
    validate_schema_value,
)


DEFAULT_MAPPING_PATH = os.path.join(
    PROJECT_ROOT, "configs", "openscenario_adapter_v1.json"
)
DEFAULT_MAPPING_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT, "schemas", "openscenario_mapping_v1.schema.json"
)


class AdapterValidationError(ValueError):
    """适配映射、输入记录或生成结果未通过静态校验。"""


def _absolute_project_path(path):
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(PROJECT_ROOT, path))


def _number(value):
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path):
    with open(path, "rb") as file:
        return _sha256_bytes(file.read())


def load_mapping(path=DEFAULT_MAPPING_PATH):
    mapping_path = os.path.abspath(path)
    mapping = load_json(mapping_path)
    schema = load_json(DEFAULT_MAPPING_SCHEMA_PATH)
    errors = validate_schema_value(mapping, schema)
    if errors:
        raise AdapterValidationError("\n".join(errors))
    return mapping_path, mapping


def _property(parent, name, value):
    properties = parent.find("Properties")
    if properties is None:
        properties = ET.SubElement(parent, "Properties")
    ET.SubElement(
        properties,
        "Property",
        {"name": str(name), "value": str(value)},
    )


def _bounding_box(parent, width, length, height):
    bounding_box = ET.SubElement(parent, "BoundingBox")
    ET.SubElement(
        bounding_box,
        "Center",
        {"x": "0", "y": "0", "z": _number(float(height) / 2.0)},
    )
    ET.SubElement(
        bounding_box,
        "Dimensions",
        {
            "width": _number(width),
            "length": _number(length),
            "height": _number(height),
        },
    )


def _vehicle(parent, name, blueprint):
    vehicle = ET.SubElement(
        parent,
        "Vehicle",
        {"name": str(name), "vehicleCategory": "car"},
    )
    _bounding_box(vehicle, 1.9, 4.5, 1.5)
    ET.SubElement(
        vehicle,
        "Performance",
        {"maxSpeed": "69.44", "maxDeceleration": "10.0", "maxAcceleration": "5.0"},
    )
    axles = ET.SubElement(vehicle, "Axles")
    ET.SubElement(
        axles,
        "FrontAxle",
        {
            "maxSteering": "0.5",
            "wheelDiameter": "0.7",
            "trackWidth": "1.6",
            "wheelbase": "2.7",
            "positionX": "1.35",
            "positionZ": "0.35",
        },
    )
    ET.SubElement(
        axles,
        "RearAxle",
        {
            "maxSteering": "0.0",
            "wheelDiameter": "0.7",
            "trackWidth": "1.6",
            "wheelbase": "2.7",
            "positionX": "-1.35",
            "positionZ": "0.35",
        },
    )
    _property(vehicle, "carla:blueprint", blueprint)
    return vehicle


def _pedestrian(parent, name, blueprint):
    pedestrian = ET.SubElement(
        parent,
        "Pedestrian",
        {
            "name": str(name),
            "model3d": str(blueprint),
            "mass": "75.0",
            "pedestrianCategory": "pedestrian",
        },
    )
    _bounding_box(pedestrian, 0.6, 0.6, 1.8)
    _property(pedestrian, "carla:blueprint", blueprint)
    return pedestrian


def _world_position(parent):
    position = ET.SubElement(parent, "Position")
    world = ET.SubElement(
        position,
        "WorldPosition",
        {"x": "0", "y": "0", "z": "0", "h": "0", "p": "0", "r": "0"},
    )
    return world


def _relative_position(parent, entity_ref, dx, dy, dz):
    position = ET.SubElement(parent, "Position")
    relative = ET.SubElement(
        position,
        "RelativeObjectPosition",
        {
            "entityRef": str(entity_ref),
            "dx": _number(dx),
            "dy": _number(dy),
            "dz": _number(dz),
        },
    )
    ET.SubElement(
        relative,
        "Orientation",
        {"type": "relative", "h": "0", "p": "0", "r": "0"},
    )
    return relative


def _time_trigger(parent, tag, name, value, rule="greaterThan"):
    trigger = ET.SubElement(parent, tag)
    condition_group = ET.SubElement(trigger, "ConditionGroup")
    condition = ET.SubElement(
        condition_group,
        "Condition",
        {"name": str(name), "delay": "0", "conditionEdge": "rising"},
    )
    by_value = ET.SubElement(condition, "ByValueCondition")
    ET.SubElement(
        by_value,
        "SimulationTimeCondition",
        {"value": _number(value), "rule": rule},
    )


def _simulation_time_trigger(parent, name, value):
    _time_trigger(parent, "StartTrigger", name, value)


def _speed_action(parent, target_speed):
    private_action = ET.SubElement(parent, "PrivateAction")
    longitudinal = ET.SubElement(private_action, "LongitudinalAction")
    speed_action = ET.SubElement(longitudinal, "SpeedAction")
    ET.SubElement(
        speed_action,
        "SpeedActionDynamics",
        {"dynamicsShape": "step", "value": "0", "dynamicsDimension": "time"},
    )
    target = ET.SubElement(speed_action, "SpeedActionTarget")
    ET.SubElement(target, "AbsoluteTargetSpeed", {"value": _number(target_speed)})


def _user_defined_action(parent, command, payload):
    private_action = ET.SubElement(parent, "PrivateAction")
    user_defined = ET.SubElement(private_action, "UserDefinedAction")
    custom = ET.SubElement(user_defined, "CustomCommandAction", {"type": command})
    custom.text = json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _add_parameter(parent, name, parameter_type, value):
    ET.SubElement(
        parent,
        "ParameterDeclaration",
        {
            "name": name,
            "parameterType": parameter_type,
            "value": str(value),
        },
    )


def build_openscenario_xml(record, mapping, base_config=None):
    names = mapping["openscenario"]["entity_names"]
    duration = float(record["scenario"]["duration_seconds"])
    base_config = base_config or {}
    ego_blueprint = base_config.get("ego_vehicle", {}).get(
        "blueprint", "vehicle.tesla.model3"
    )
    lead_blueprint = base_config.get("lead_vehicle", {}).get(
        "blueprint", "vehicle.audi.a2"
    )
    pedestrian_blueprint = base_config.get("pedestrian", {}).get(
        "blueprint", "walker.pedestrian.0007"
    )
    ego_spawn_index = base_config.get("scenario", {}).get("ego_spawn_index")
    root = ET.Element("OpenSCENARIO")
    ET.SubElement(
        root,
        "FileHeader",
        {
            "revMajor": "1",
            "revMinor": "0",
            "date": str(record["provenance"]["created_at"]),
            "description": f"{record['sample_id']} minimal CARLA adapter",
            "author": "carla-extreme-scenario-generator",
        },
    )
    parameters = ET.SubElement(root, "ParameterDeclarations")
    _add_parameter(parameters, "carla_target_risk_level", "string", record["conditions"]["target_risk_level"])
    _add_parameter(parameters, "carla_traffic_manager_seed", "int", record["scenario"]["traffic_manager_seed"])
    for field, value in record["weather"].items():
        _add_parameter(parameters, f"carla_weather_{field}", "double", _number(value))
    _add_parameter(parameters, "carla_lead_vehicle_brake_intensity", "double", _number(record["lead_vehicle"]["brake_intensity"]))
    _add_parameter(parameters, "carla_pedestrian_speed_mps", "double", _number(record["pedestrian"]["speed_mps"]))

    catalog_locations = ET.SubElement(root, "CatalogLocations")
    for catalog_name in ("VehicleCatalog", "PedestrianCatalog", "ControllerCatalog", "MiscObjectCatalog", "EnvironmentCatalog", "RouteCatalog"):
        catalog = ET.SubElement(catalog_locations, catalog_name)
        ET.SubElement(catalog, "Directory", {"path": ""})

    road_network = ET.SubElement(root, "RoadNetwork")
    ET.SubElement(road_network, "LogicFile", {"filepath": mapping["openscenario"]["road_network_logic_file"]})
    _add_parameter(
        parameters,
        "carla_map_name",
        "string",
        mapping["openscenario"]["road_network_logic_file"],
    )

    entities = ET.SubElement(root, "Entities")
    ego = ET.SubElement(entities, "ScenarioObject", {"name": names["ego"]})
    ego_vehicle = _vehicle(ego, "ego_vehicle", ego_blueprint)
    _property(ego_vehicle, "carla:position_semantics", "ego_spawn_index")
    _property(ego_vehicle, "carla:ego_spawn_index_source", "base_config.scenario.ego_spawn_index")
    if ego_spawn_index is not None:
        _property(ego_vehicle, "carla:ego_spawn_index", ego_spawn_index)
    lead = ET.SubElement(entities, "ScenarioObject", {"name": names["lead"]})
    lead_vehicle = _vehicle(lead, "lead_vehicle", lead_blueprint)
    _property(lead_vehicle, "carla:brake_intensity", record["lead_vehicle"]["brake_intensity"])
    pedestrian = ET.SubElement(entities, "ScenarioObject", {"name": names["pedestrian"]})
    _pedestrian(pedestrian, "pedestrian", pedestrian_blueprint)

    storyboard = ET.SubElement(root, "Storyboard")
    init = ET.SubElement(storyboard, "Init")
    actions = ET.SubElement(init, "Actions")
    ego_private = ET.SubElement(actions, "Private", {"entityRef": names["ego"]})
    ego_action = ET.SubElement(ego_private, "PrivateAction")
    teleport = ET.SubElement(ego_action, "TeleportAction")
    _world_position(teleport)

    lead_private = ET.SubElement(actions, "Private", {"entityRef": names["lead"]})
    lead_action = ET.SubElement(lead_private, "PrivateAction")
    lead_teleport = ET.SubElement(lead_action, "TeleportAction")
    _relative_position(
        lead_teleport,
        names["ego"],
        record["lead_vehicle"]["initial_distance_m"],
        0,
        0,
    )

    pedestrian_private = ET.SubElement(actions, "Private", {"entityRef": names["pedestrian"]})
    pedestrian_teleport_action = ET.SubElement(pedestrian_private, "PrivateAction")
    pedestrian_teleport = ET.SubElement(pedestrian_teleport_action, "TeleportAction")
    _relative_position(
        pedestrian_teleport,
        names["ego"],
        record["pedestrian"]["forward_distance_m"],
        record["pedestrian"]["roadside_offset_m"],
        record["pedestrian"]["spawn_z_offset_m"],
    )
    _speed_action(pedestrian_private, record["pedestrian"]["speed_mps"])

    story = ET.SubElement(storyboard, "Story", {"name": record["sample_id"]})
    lead_act = ET.SubElement(story, "Act", {"name": "lead_braking_act"})
    lead_group = ET.SubElement(lead_act, "ManeuverGroup", {"maximumExecutionCount": "1", "name": "lead_braking_group"})
    lead_actors = ET.SubElement(lead_group, "Actors", {"selectTriggeringEntities": "false"})
    ET.SubElement(lead_actors, "EntityRef", {"entityRef": names["lead"]})
    lead_maneuver = ET.SubElement(lead_group, "Maneuver", {"name": "lead_braking_maneuver"})
    lead_event = ET.SubElement(lead_maneuver, "Event", {"name": "lead_braking_event", "priority": "overwrite", "maximumExecutionCount": "1"})
    lead_action_node = ET.SubElement(lead_event, "Action", {"name": "lead_braking_action"})
    _speed_action(lead_action_node, 0.0)
    _simulation_time_trigger(lead_event, "lead_brake_trigger", record["lead_vehicle"]["brake_trigger_seconds"])
    _time_trigger(lead_act, "StartTrigger", "lead_act_start", 0.0)
    _time_trigger(lead_act, "StopTrigger", "lead_act_stop", duration)

    pedestrian_act = ET.SubElement(story, "Act", {"name": "pedestrian_crossing_act"})
    pedestrian_group = ET.SubElement(pedestrian_act, "ManeuverGroup", {"maximumExecutionCount": "1", "name": "pedestrian_crossing_group"})
    pedestrian_actors = ET.SubElement(pedestrian_group, "Actors", {"selectTriggeringEntities": "false"})
    ET.SubElement(pedestrian_actors, "EntityRef", {"entityRef": names["pedestrian"]})
    pedestrian_maneuver = ET.SubElement(pedestrian_group, "Maneuver", {"name": "pedestrian_crossing_maneuver"})
    pedestrian_event = ET.SubElement(pedestrian_maneuver, "Event", {"name": "pedestrian_crossing_event", "priority": "overwrite", "maximumExecutionCount": "1"})
    pedestrian_action = ET.SubElement(pedestrian_event, "Action", {"name": "pedestrian_crossing_action"})
    _user_defined_action(
        pedestrian_action,
        "CARLA:pedestrian_crossing",
        {
            "forward_distance_m": record["pedestrian"]["forward_distance_m"],
            "roadside_offset_m": record["pedestrian"]["roadside_offset_m"],
            "speed_mps": record["pedestrian"]["speed_mps"],
        },
    )
    _simulation_time_trigger(pedestrian_event, "pedestrian_crossing_trigger", record["pedestrian"]["trigger_seconds"])
    _time_trigger(pedestrian_act, "StartTrigger", "pedestrian_act_start", 0.0)
    _time_trigger(pedestrian_act, "StopTrigger", "pedestrian_act_stop", duration)

    stop_trigger = ET.SubElement(storyboard, "StopTrigger")
    stop_group = ET.SubElement(stop_trigger, "ConditionGroup")
    stop_condition = ET.SubElement(stop_group, "Condition", {"name": "scenario_duration", "delay": "0", "conditionEdge": "rising"})
    stop_by_value = ET.SubElement(stop_condition, "ByValueCondition")
    ET.SubElement(stop_by_value, "SimulationTimeCondition", {"value": _number(duration), "rule": "greaterThan"})
    return root


def validate_openscenario_tree(root, record, mapping):
    errors = []
    if root.tag != "OpenSCENARIO":
        errors.append("根元素必须是 OpenSCENARIO")
        return errors
    header = root.find("FileHeader")
    if header is None or header.get("revMajor") != "1" or header.get("revMinor") != "0":
        errors.append("FileHeader 必须声明 OpenSCENARIO 1.0")
    entities = root.find("Entities")
    expected_names = set(mapping["openscenario"]["entity_names"].values())
    actual_names = (
        {item.get("name") for item in entities}
        if entities is not None
        else set()
    )
    if actual_names != expected_names:
        errors.append(f"实体集合不匹配: expected={sorted(expected_names)} actual={sorted(actual_names)}")
    storyboard = root.find("Storyboard")
    if storyboard is None or storyboard.find("Init") is None or storyboard.find("StopTrigger") is None:
        errors.append("Storyboard 必须包含 Init 和 StopTrigger")
    condition_values = [
        float(node.get("value"))
        for node in root.findall(".//SimulationTimeCondition")
        if node.get("value") is not None
    ]
    duration = float(record["scenario"]["duration_seconds"])
    if not any(abs(value - duration) < 1e-6 for value in condition_values):
        errors.append("StopTrigger 未保留 scenario.duration_seconds")
    if not root.findall(".//Event[@name='lead_braking_event']"):
        errors.append("缺少前车急刹事件")
    if not root.findall(".//Event[@name='pedestrian_crossing_event']"):
        errors.append("缺少行人横穿事件")
    return errors


def validate_carla_config_shape(config):
    required_sections = {
        "scenario", "weather", "traffic", "ego_vehicle", "lead_vehicle",
        "pedestrian", "sensors", "risk_evaluation", "output",
    }
    missing = sorted(required_sections - set(config))
    if missing:
        return [f"CARLA 配置缺少顶层字段: {', '.join(missing)}"]
    if float(config["scenario"]["duration_seconds"]) <= 0:
        return ["CARLA 配置 scenario.duration_seconds 必须大于 0"]
    return []


def convert_record(record, mapping, base_config, base_config_path):
    require_valid_scenario(record)
    root = build_openscenario_xml(record, mapping, base_config)
    xosc_errors = validate_openscenario_tree(root, record, mapping)
    if xosc_errors:
        raise AdapterValidationError("\n".join(xosc_errors))
    compiled = compile_carla_config(copy.deepcopy(record), base_config)
    carla_errors = validate_carla_config_shape(compiled)
    if carla_errors:
        raise AdapterValidationError("\n".join(carla_errors))
    return root, compiled, {
        "adapter_id": mapping["adapter_id"],
        "mapping_version": mapping["mapping_version"],
        "source_sample_id": record["sample_id"],
        "source_family": record["family"],
        "openscenario_standard_version": mapping["openscenario"]["standard_version"],
        "openscenario_execution_status": "exchange_only_minimal_subset",
        "carla_execution_status": "compiled_config_requires_scene_runner_validate_only",
        "coverage": mapping["coverage"],
        "source_conditions": record["conditions"],
        "source_observed_risk": record["observed_risk"],
        "source_provenance": record["provenance"],
        "source_sha256": _sha256_bytes(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        "base_config_sha256": _sha256_file(base_config_path),
    }


def _write_xml(path, root):
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def parse_args():
    parser = argparse.ArgumentParser(description="自定义场景 JSON 到 OpenSCENARIO/CARLA 的最小适配器")
    parser.add_argument("--input", required=True, help="单条 generated_scenario JSON 记录")
    parser.add_argument("--output-dir", default=None, help="输出 xosc、CARLA JSON 和适配清单的目录")
    parser.add_argument("--mapping", default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--base-config", default=None)
    parser.add_argument("--validate-only", action="store_true", help="只校验映射、输入记录、XOSC 结构和 CARLA 配置形状")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    mapping_path, mapping = load_mapping(args.mapping)
    record = load_json(input_path)
    base_config_path = _absolute_project_path(args.base_config or mapping["carla"]["base_config_path"])
    base_config = load_json(base_config_path)
    root, compiled, manifest = convert_record(record, mapping, base_config, base_config_path)
    if args.validate_only:
        print(f"[VALID] {input_path} -> OpenSCENARIO 1.0 minimal subset")
        print(f"[VALID] CARLA config sections={len(compiled)} mapping={mapping_path}")
        return 0

    output_dir = os.path.abspath(args.output_dir or os.path.join(PROJECT_ROOT, "artifacts", "openscenario_adapter_v1", record["sample_id"]))
    os.makedirs(output_dir, exist_ok=True)
    xosc_path = os.path.join(output_dir, f"{record['sample_id']}.xosc")
    carla_path = os.path.join(output_dir, f"{record['sample_id']}.carla.json")
    manifest_path = os.path.join(output_dir, f"{record['sample_id']}.adapter_manifest.json")
    rebase_output_root(compiled, base_config_path, carla_path)
    _write_xml(xosc_path, root)
    with open(carla_path, "w", encoding="utf-8") as file:
        json.dump(compiled, file, ensure_ascii=False, indent=2)
    manifest["mapping_sha256"] = _sha256_file(mapping_path)
    manifest["xosc_path"] = xosc_path
    manifest["carla_config_path"] = carla_path
    manifest["xosc_sha256"] = _sha256_file(xosc_path)
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
    print(f"[CONVERTED] xosc={xosc_path}")
    print(f"[CONVERTED] carla_config={carla_path}")
    print(f"[MANIFEST] {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
