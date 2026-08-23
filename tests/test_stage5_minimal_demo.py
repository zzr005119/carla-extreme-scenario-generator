import json
import tempfile
import unittest
from pathlib import Path

from tools.stage5_minimal_demo import DEFAULT_RECORD, DEFAULT_LIBRARY, DEFAULT_BASE_CONFIG, run_demo


class Stage5MinimalDemoTests(unittest.TestCase):
    def test_offline_demo_writes_auditable_manifest(self):
        with tempfile.TemporaryDirectory() as output_dir:
            manifest = run_demo(
                record_path=DEFAULT_RECORD,
                library_path=DEFAULT_LIBRARY,
                base_config_path=DEFAULT_BASE_CONFIG,
                output_dir=output_dir,
            )
            self.assertFalse(manifest["carla_connected"])
            self.assertEqual(manifest["execution_mode"], "offline_static_and_evidence")
            self.assertEqual(manifest["stages"]["M02_validation_and_compile"]["status"], "passed")
            self.assertEqual(manifest["stages"]["M04_static_simulation_adapter"]["status"], "passed")
            self.assertEqual(manifest["stages"]["M07_dashboard_data"]["row_count"], 117)
            self.assertEqual(manifest["stages"]["M03_library_query"]["collision_entry_count"], 39)
            self.assertTrue(Path(manifest["outputs"]["demo_manifest"]).is_file())
            self.assertTrue(Path(manifest["outputs"]["openscenario"]).is_file())

            saved = json.loads(Path(manifest["outputs"]["demo_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["sample_id"], manifest["sample_id"])
            self.assertFalse(saved["stages"]["M05_risk_evidence"]["new_carla_risk_evaluation"])

    def test_demo_rejects_missing_record(self):
        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(FileNotFoundError):
                run_demo(
                    record_path=Path(output_dir) / "missing.json",
                    library_path=DEFAULT_LIBRARY,
                    base_config_path=DEFAULT_BASE_CONFIG,
                    output_dir=output_dir,
                )


if __name__ == "__main__":
    unittest.main()
