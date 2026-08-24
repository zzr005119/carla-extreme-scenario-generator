import json
import tempfile
import unittest
from pathlib import Path

from tools.check_scenario_runner_acceptance import check_acceptance
from tools.prepare_scenario_runner_acceptance import prepare_config


class ScenarioRunnerAcceptanceTests(unittest.TestCase):
    def test_prepare_enables_full_sensors_and_route(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            xosc = root / "sample.xosc"
            xosc.write_text(
                '<OpenSCENARIO><RoadNetwork><LogicFile filepath="Town10HD_Opt"/></RoadNetwork></OpenSCENARIO>',
                encoding="utf-8",
            )
            source = root / "source.json"
            source.write_text(json.dumps({
                "scenario": {"name": "sample", "traffic_manager_port": 8000},
                "traffic": {},
                "sensors": {"camera": {}, "rgb": {}, "depth": {}, "semantic": {}, "collision": {}},
                "risk_evaluation": {},
                "output": {"root": "old"},
            }), encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text(json.dumps({
                "profile_id": "test_profile",
                "route": {"route_length_m": 300, "route_step_m": 2, "route_deviation_tolerance_m": 3},
                "controller": {"target_speed_kmh": 29},
            }), encoding="utf-8")
            manifest_path, config_path = prepare_config(xosc, source, root / "out", profile, 8100)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(all(config["sensors"][name]["enabled"] for name in ("rgb", "depth", "semantic", "collision")))
            self.assertTrue(config["traffic"]["route_lock_enabled"])
            self.assertEqual(config["scenario"]["traffic_manager_port"], 8100)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["status"], "prepared")

    def test_check_accepts_complete_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_root = root / "runs" / "run1"
            run_root.mkdir(parents=True)
            metadata = {
                "carla_versions": {"client": "0.9.16", "server": "0.9.16", "match": True},
                "frames": {"rgb": 200, "depth": 200, "semantic": 200},
                "sensor_pipeline": {"status": "completed", "sensors": {name: {"complete": True, "failed": 0, "saved": 200} for name in ("rgb", "depth", "semantic")}},
                "server_health": {"status": "healthy"},
                "route_control": {"enabled": True, "status": "completed", "mode": "waypoint_follower", "both_on_route_rate": 1.0, "maximum_ego_deviation_m": 1.0, "maximum_lead_deviation_m": 1.1},
                "result": {"status": "completed", "collision_count": 0, "risk_evaluation": {"method": "heuristic_v2", "level": "medium", "score": 27.0}},
                "cleanup": {"status": "completed"},
            }
            (run_root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            manifest = {"format": "scenario_runner_carla_full_acceptance_v1", "sample_id": "sample", "expected_run_root": str(root / "runs"), "acceptance_requirements": {"carla_version": "0.9.16", "sensor_status": "completed", "minimum_rgb_frames": 100, "minimum_depth_frames": 100, "minimum_semantic_frames": 100, "server_status": "healthy", "route_control_mode": "waypoint_follower", "minimum_route_both_on_rate": 1.0, "maximum_route_deviation_m": 3.0, "risk_method": "heuristic_v2"}}
            manifest_path = root / "acceptance_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(check_acceptance(manifest_path)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
