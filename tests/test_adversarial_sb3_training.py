import importlib.util
import os
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)

from core.scenario_validator import load_json  # noqa: E402
from tools.train_adversarial_sb3_smoke import (  # noqa: E402
    DeterministicMockRiskExecutor,
    run_algorithm,
    run_checks,
)


class DeterministicMockRiskExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_json(RECORD_PATH)

    def test_score_and_result_are_deterministic(self):
        executor = DeterministicMockRiskExecutor()
        first = executor(self.record, "baseline", -1)
        second = executor(self.record, "baseline", -1)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first["observed_risk_score"], 0.0)
        self.assertLessEqual(first["observed_risk_score"], 100.0)
        self.assertEqual(first["risk_method"], "deterministic_mock_v1")


@unittest.skipUnless(
    importlib.util.find_spec("stable_baselines3") is not None,
    "需要可选训练依赖 Stable-Baselines3",
)
class StableBaselines3TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_json(RECORD_PATH)

    def test_environment_check_and_ppo_model_round_trip(self):
        run_checks(self.record, max_steps=4)
        with tempfile.TemporaryDirectory() as output_root:
            result = run_algorithm(
                name="ppo",
                record=self.record,
                output_root=output_root,
                total_timesteps=16,
                seed=123,
                max_steps=4,
                device="cpu",
            )
            self.assertTrue(result["model_exists"])
            self.assertGreaterEqual(result["trained_num_timesteps"], 16)
            self.assertEqual(result["prediction"]["observation_shape"], [34])
            self.assertTrue(result["prediction"]["proposal_valid"])


if __name__ == "__main__":
    unittest.main()
