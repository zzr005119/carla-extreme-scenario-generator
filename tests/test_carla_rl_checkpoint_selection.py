import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.select_carla_rl_checkpoint import select_checkpoint
from tools.train_carla_rl import _checkpoint_entry, _resume_entry


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CarlaRLCheckpointSelectionTests(unittest.TestCase):
    def _summary(self, root, steps, delta, *, split="dev"):
        model = root / f"sac_steps_{steps:06d}.zip"
        model.write_bytes(f"model-{steps}".encode("ascii"))
        summary = {
            "format": "carla_online_rl_evaluation_v2",
            "algorithm": "SAC",
            "model_path": str(model),
            "model_sha256": _sha256(model),
            "model_trained_num_timesteps": steps,
            "config_sha256": "config-sha",
            "scenario_plan_sha256": "plan-sha",
            "split": split,
            "test_count": 3,
            "seed": 107,
            "evaluation_policy": {"selection_mode": "best_so_far"},
            "acceptance": {
                "status": "passed",
                "checks": {
                    name: {"passed": True}
                    for name in (
                        "baseline_strict_acceptance",
                        "candidate_condition_validity",
                        "candidate_runtime_strict_acceptance",
                        "candidate_evidence_completeness",
                    )
                },
            },
            "effect_summary": {
                "status": "descriptive_only",
                "row_count": 3,
                "delta_mean": delta,
                "delta_median": delta,
                "risk_increase_count": 2,
                "selected_candidate_mean": 70.0 + delta,
            },
        }
        path = root / f"dev_{steps}.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        return path

    def test_selects_highest_dev_delta_and_writes_auditable_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            low = self._summary(root, 256, 2.0)
            high = self._summary(root, 2000, 7.0)
            output = root / "selection.json"
            result = select_checkpoint([low, high], output)
            self.assertEqual(result["selected_trained_num_timesteps"], 2000)
            self.assertEqual(result["selection_split"], "dev")
            self.assertFalse(result["test_split_used_for_selection"])
            self.assertEqual([row["rank"] for row in result["candidates"]], [1, 2])
            self.assertEqual(result["promotion_gate"]["status"], "passed")
            self.assertTrue(output.is_file())

    def test_rejects_test_summary_for_model_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            summary = self._summary(root, 256, 2.0, split="test")
            with self.assertRaisesRegex(ValueError, "只允许 dev"):
                select_checkpoint([summary], root / "selection.json")

    def test_resume_rejects_legacy_checkpoint_without_continuity_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "checkpoint.zip"
            model.write_bytes(b"model")
            manifest = {
                "format": "carla_online_rl_checkpoint_manifest_v1",
                "algorithm": "SAC",
                "training_seed": 7,
                "checkpoints": [{"path": str(model)}],
            }
            with self.assertRaisesRegex(RuntimeError, "旧 checkpoint manifest"):
                _resume_entry(
                    manifest,
                    model,
                    algorithm="SAC",
                    training_seed=7,
                    scenario_plan=None,
                )

    def test_sac_checkpoint_entry_writes_all_continuity_artifacts(self):
        class FakeModel:
            num_timesteps = 256

            @staticmethod
            def save(path):
                Path(path).write_bytes(b"model")

            @staticmethod
            def save_replay_buffer(path):
                Path(path).write_bytes(b"replay")

        class FakeSampler:
            @staticmethod
            def state_dict():
                return {"format": "carla_online_rl_sampler_state_v2"}

        with tempfile.TemporaryDirectory() as temp:
            entry = _checkpoint_entry(
                FakeModel(),
                FakeSampler(),
                Path(temp),
                "sac_seed_7",
                "SAC",
                0,
                256,
            )
            self.assertTrue(entry["continuity_complete"])
            self.assertEqual(
                set(entry["artifacts"]),
                {"model", "replay_buffer", "sampler_state"},
            )
            self.assertTrue(
                all(
                    Path(artifact["path"]).is_file()
                    for artifact in entry["artifacts"].values()
                )
            )

    def test_p3_1_server_flow_is_isolated_and_never_selects_on_test(self):
        project_root = Path(__file__).resolve().parents[1]
        script = (
            project_root / "tools" / "server_jobs" / "carla_rl_p3_1_v1.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("configs/adversarial_loop_multistep_p3_1.json", script)
        self.assertIn("carla_rl_p3_1_v1", script)
        self.assertIn("--require-continuity", script)
        self.assertIn("--split dev", script)
        self.assertNotIn("--split test", script)
        self.assertIn("select_carla_rl_checkpoint.py", script)


if __name__ == "__main__":
    unittest.main()
