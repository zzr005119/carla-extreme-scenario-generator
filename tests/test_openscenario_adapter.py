import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.convert_scenario_to_openscenario import (  # noqa: E402
    build_openscenario_xml,
    convert_record,
    load_mapping,
    validate_openscenario_tree,
)
from core.scenario_validator import load_json  # noqa: E402


class OpenScenarioAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_json(
            os.path.join(
                PROJECT_ROOT,
                "data",
                "scenarios",
                "seed_v1",
                "example_record.json",
            )
        )
        cls.base_config_path = os.path.join(
            PROJECT_ROOT, "configs", "multi_hazard_rainy_night.json"
        )
        cls.base_config = load_json(cls.base_config_path)
        cls.mapping_path, cls.mapping = load_mapping()

    def test_mapping_schema_and_minimal_tree(self):
        root = build_openscenario_xml(self.record, self.mapping)
        ET.fromstring(ET.tostring(root, encoding="utf-8"))
        errors = validate_openscenario_tree(root, self.record, self.mapping)
        self.assertEqual(errors, [])
        self.assertEqual(root.find("FileHeader").get("revMinor"), "0")
        weather_parameters = [
            node
            for node in root.findall(".//ParameterDeclaration")
            if node.get("name", "").startswith("carla_weather_")
        ]
        self.assertEqual(len(weather_parameters), 8)

    def test_events_and_carla_extensions_are_preserved(self):
        root = build_openscenario_xml(self.record, self.mapping)
        self.assertEqual(
            root.find(".//Event[@name='lead_braking_event']")
            .find(".//SimulationTimeCondition")
            .get("value"),
            "4.654",
        )
        pedestrian_action = root.find(
            ".//Event[@name='pedestrian_crossing_event']/.//LongitudinalAction"
        )
        self.assertIsNotNone(pedestrian_action)
        self.assertIsNone(root.find(".//CustomCommandAction"))
        self.assertIsNotNone(root.find(".//Property[@name='carla:blueprint']"))

    def test_parameter_types_follow_openscenario_10(self):
        root = build_openscenario_xml(self.record, self.mapping)
        params = {
            node.get("name"): node.get("parameterType")
            for node in root.findall("./ParameterDeclarations/ParameterDeclaration")
        }
        self.assertEqual(params["carla_traffic_manager_seed"], "integer")
        self.assertNotIn("int", params.values())

    def test_axle_attributes_follow_openscenario_10(self):
        root = build_openscenario_xml(self.record, self.mapping)
        for axle in root.findall(".//Axles/*"):
            self.assertNotIn("wheelbase", axle.attrib)

    def test_pedestrian_attributes_follow_openscenario_10(self):
        root = build_openscenario_xml(self.record, self.mapping)
        pedestrian = root.find(".//Pedestrian")
        self.assertIn("model", pedestrian.attrib)
        self.assertNotIn("model3d", pedestrian.attrib)

    def test_ego_actor_is_marked_for_scenario_runner(self):
        root = build_openscenario_xml(self.record, self.mapping)
        ego = root.find(".//ScenarioObject[@name='ego']")
        properties = {
            node.get("name"): node.get("value")
            for node in ego.findall(".//Property")
        }
        self.assertEqual(properties["type"], "ego_vehicle")

    def test_vehicle_names_are_carla_blueprints_and_position_can_be_bound(self):
        root = build_openscenario_xml(
            self.record,
            self.mapping,
            self.base_config,
            (106.0288, 67.4200, 0.6, -89.6093, 0.0, 0.0),
        )
        self.assertEqual(root.find(".//ScenarioObject[@name='ego']/Vehicle").get("name"), "vehicle.tesla.model3")
        self.assertEqual(root.find(".//ScenarioObject[@name='lead_vehicle']/Vehicle").get("name"), "vehicle.audi.a2")
        world = root.findall(".//WorldPosition")[0]
        self.assertEqual(world.get("x"), "106.0288")
        self.assertEqual(world.get("h"), "-89.6093")

    def test_conversion_compiles_scene04_config(self):
        root, compiled, manifest = convert_record(
            self.record,
            self.mapping,
            self.base_config,
            self.base_config_path,
        )
        self.assertEqual(compiled["scenario"]["name"], self.record["sample_id"])
        self.assertEqual(
            compiled["scenario"]["traffic_manager_seed"],
            self.record["scenario"]["traffic_manager_seed"],
        )
        self.assertEqual(manifest["openscenario_execution_status"], "exchange_only_minimal_subset")
        self.assertEqual(manifest["carla_execution_status"], "compiled_config_requires_scene_runner_validate_only")

    def test_cli_output_files_are_reproducible_in_temp_dir(self):
        from tools.convert_scenario_to_openscenario import _write_xml

        with tempfile.TemporaryDirectory() as output_dir:
            root = build_openscenario_xml(self.record, self.mapping)
            path = os.path.join(output_dir, "sample.xosc")
            _write_xml(path, root)
            parsed = ET.parse(path).getroot()
            self.assertEqual(parsed.tag, "OpenSCENARIO")
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
