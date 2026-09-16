import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ServerStorageWorkflowTests(unittest.TestCase):
    def test_runtime_data_paths_use_data_volume(self):
        config = json.loads(
            (PROJECT_ROOT / "configs" / "server_workflow.json").read_text(
                encoding="utf-8"
            )
        )
        runtime = config["runtime"]

        self.assertEqual(
            runtime["output_root"],
            "/data/zhaozirong/software/output/carla-0.9.16",
        )
        self.assertEqual(
            runtime["model_root"],
            "/data/zhaozirong/software/models/carla-extreme-scenario-generator",
        )
        self.assertTrue(runtime["gpu_lock"].startswith(runtime["output_root"] + "/"))

    def test_remote_job_scripts_do_not_require_executable_bits(self):
        script = (PROJECT_ROOT / "tools" / "server_run.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertNotIn("chmod 700", script)
        self.assertIn('bash "`$job_directory/command.sh"', script)
        self.assertIn("bash '$jobDirectory/runner.sh'", script)


if __name__ == "__main__":
    unittest.main()
