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

    def test_episode_scope_excludes_historical_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_completed_run(root)
            current_path = next(root.glob("episodes/**/execution_result.json"))
            payload = json.loads(current_path.read_text(encoding="utf-8"))
            payload["result"]["strict_acceptance_passed"] = False
            self._write(
                root
                / "episodes"
                / "historical"
                / "steps"
                / "00_baseline"
                / "execution_result.json",
                payload,
            )

            aggregate = audit_training(root, 256, "SAC")
            self.assertEqual(aggregate["status"], "failed")
            scoped = audit_training(root, 256, "SAC", "episode")
            self.assertEqual(scoped["status"], "passed")
            self.assertEqual(scoped["audit_scope"]["mode"], "episode")
            self.assertEqual(scoped["audit_scope"]["episode_id"], "episode")
            self.assertEqual(scoped["execution_result_count"], 1)

    def test_episode_id_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            for episode_id in ("../episode", ".."):
                with self.subTest(episode_id=episode_id):
                    with self.assertRaises(ValueError):
                        audit_training(Path(temp), 256, "SAC", episode_id)

    def test_v2_requires_model_replay_buffer_and_sampler_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_completed_run(root)
            summary_path = root / "rl_training_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["scenario_plan_sha256"] = "plan-sha"
            self._write(summary_path, summary)

            manifest_path = root / "checkpoint_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checkpoint = Path(manifest["checkpoints"][0]["path"])
            replay = checkpoint.with_name(checkpoint.stem + "_replay_buffer.pkl")
            sampler = checkpoint.with_name(checkpoint.stem + "_sampler_state.json")
            replay.write_bytes(b"replay")
            self._write(
                sampler,
                {"format": "carla_online_rl_sampler_state_v2"},
            )
            manifest["format"] = "carla_online_rl_checkpoint_manifest_v2"
            manifest["checkpoints"][0].update(
                {
                    "continuity_complete": True,
                    "artifacts": {
                        "model": {
                            "required": True,
                            "path": str(checkpoint),
                            "exists": True,
                        },
                        "replay_buffer": {
                            "required": True,
                            "path": str(replay),
                            "exists": True,
                        },
                        "sampler_state": {
                            "required": True,
                            "path": str(sampler),
                            "exists": True,
                        },
                    },
                }
            )
            self._write(manifest_path, manifest)
            passed = audit_training(root, 256, "SAC", require_continuity=True)
            self.assertEqual(passed["status"], "passed")
            self.assertTrue(
                next(
                    item
                    for item in passed["checks"]
                    if item["name"] == "checkpoint_resume_continuity"
                )["passed"]
            )

            replay.unlink()
            failed = audit_training(root, 256, "SAC", require_continuity=True)
            self.assertIn("checkpoint_resume_continuity", failed["failed_checks"])


if __name__ == "__main__":
    unittest.main()
