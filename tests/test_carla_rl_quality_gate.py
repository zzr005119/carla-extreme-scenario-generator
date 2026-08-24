import json
import tempfile
import unittest
from pathlib import Path

from tools.check_carla_rl_training import audit_training


class CarlaRLQualityGateTests(unittest.TestCase):
    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def _make_completed_run(self, root):
        model = root / "sac_seed_7_final.zip"
        checkpoint = root / "models" / "sac_seed_7_steps_000256.zip"
        checkpoint.parent.mkdir(parents=True)
        model.write_bytes(b"model")
        checkpoint.write_bytes(b"checkpoint")
        summary = {
            "status": "completed",
            "algorithm": "SAC",
            "trained_num_timesteps": 256,
            "model_path": str(model),
            "sampler_snapshot": {"selected_splits": ["train"]},
        }
        self._write(root / "rl_training_summary.json", summary)
        self._write(root / "run_manifest.json", {"status": "completed"})
        self._write(
            root / "checkpoint_manifest.json",
            {
                "checkpoints": [
                    {"path": str(checkpoint), "trained_num_timesteps": 256}
                ]
            },
        )
        self._write(
            root / "episodes" / "episode" / "steps" / "00_baseline" / "execution_result.json",
            {
                "result": {
                    "status": "completed",
                    "run_valid": True,
                    "strict_acceptance_passed": True,
                    "carla_service_healthy": True,
                },
                "acceptance": {
                    "carla_client_version": "0.9.16",
                    "carla_server_version": "0.9.16",
                },
            },
        )

    def test_completed_strict_run_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_completed_run(root)
            result = audit_training(root, 256, "SAC")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["failed_checks"], [])

    def test_failed_acceptance_blocks_next_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_completed_run(root)
            result_path = next(root.glob("episodes/**/execution_result.json"))
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["result"]["strict_acceptance_passed"] = False
            self._write(result_path, payload)
            result = audit_training(root, 256, "SAC")
            self.assertEqual(result["status"], "failed")
            self.assertIn("all_executions_strict", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
