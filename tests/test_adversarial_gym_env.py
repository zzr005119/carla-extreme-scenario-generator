import copy
import importlib.util
import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.adversarial_gym_env import (  # noqa: E402
    AdversarialEnvCore,
    AdversarialEnvResetError,
    AdversarialGymEnv,
    GymnasiumDependencyError,
)
from core.scenario_validator import load_json  # noqa: E402


class SequenceExecutor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, record, phase, step_index):
        self.calls.append((record["sample_id"], phase, step_index))
        return self.results.pop(0)


def successful_result(score, level, run_dir):
    return {
        "status": "completed",
        "observed_risk_score": score,
        "observed_risk_level": level,
        "risk_method": "heuristic_v2",
        "collision_count": 0,
        "event_count": 2,
        "run_valid": True,
        "strict_acceptance_passed": True,
        "carla_service_healthy": True,
        "run_dir": run_dir,
    }


class AdversarialEnvCoreTests(unittest.TestCase):
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
        cls.config = load_agent_config()

    def test_reset_and_step_match_gymnasium_shapes(self):
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(42.0, "medium", "mock://candidate"),
            ]
        )
        env = AdversarialEnvCore(self.record, executor=executor, config=self.config)
        observation, reset_info = env.reset(seed=7)
        self.assertEqual(observation.shape, (34,))
        self.assertEqual(observation.dtype.name, "float32")
        self.assertTrue((observation >= 0.0).all())
        self.assertTrue((observation <= 1.0).all())
        self.assertEqual(reset_info["phase"], "baseline")

        result = env.step([0.01] * 15)
        next_observation, reward, terminated, truncated, info = result
        self.assertEqual(next_observation.shape, (34,))
        self.assertIsInstance(reward, float)
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertEqual(info["proposal_valid"], True)
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [("baseline", -1), ("candidate", 0)],
        )

    def test_invalid_candidate_can_recover_without_executor_call(self):
        config = copy.deepcopy(self.config)
        config["termination"]["terminate_on_invalid_candidate"] = False
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(42.0, "medium", "mock://candidate"),
            ]
        )
        env = AdversarialEnvCore(self.record, executor=executor, config=config)
        env.reset()
        _, reward, terminated, truncated, info = env.step([0.0] * 14)
        self.assertEqual(reward, -1.0)
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertFalse(info["proposal_valid"])
        self.assertEqual(len(executor.calls), 1)

        _, _, terminated, truncated, info = env.step([0.01] * 15)
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertTrue(info["proposal_valid"])
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [("baseline", -1), ("candidate", 1)],
        )

    def test_failed_baseline_is_a_reset_error(self):
        executor = SequenceExecutor(
            [
                {
                    "status": "failed",
                    "run_valid": False,
                    "strict_acceptance_passed": False,
                    "carla_service_healthy": False,
                    "failure_reason": "baseline_unhealthy",
                }
            ]
        )
        env = AdversarialEnvCore(self.record, executor=executor, config=self.config)
        with self.assertRaises(AdversarialEnvResetError) as context:
            env.reset()
        self.assertEqual(context.exception.result.failure_reason, "baseline_unhealthy")

    def test_step_after_terminal_transition_requires_reset(self):
        config = copy.deepcopy(self.config)
        config["termination"]["max_steps"] = 1
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(42.0, "medium", "mock://candidate"),
            ]
        )
        env = AdversarialEnvCore(self.record, executor=executor, config=config)
        env.reset()
        _, _, terminated, truncated, _ = env.step([0.01] * 15)
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        with self.assertRaises(RuntimeError):
            env.step([0.01] * 15)


@unittest.skipUnless(
    importlib.util.find_spec("gymnasium") is None,
    "当前环境已安装 Gymnasium 时跳过缺失依赖测试",
)
class OptionalGymnasiumDependencyTests(unittest.TestCase):
    def test_gymnasium_wrapper_is_explicitly_optional(self):
        with self.assertRaises(GymnasiumDependencyError):
            AdversarialGymEnv(
                record=load_json(
                    os.path.join(
                        PROJECT_ROOT,
                        "data",
                        "scenarios",
                        "seed_v1",
                        "example_record.json",
                    )
                ),
                executor=lambda *_: successful_result(
                    30.0,
                    "medium",
                    "mock://baseline",
                ),
            )


if __name__ == "__main__":
    unittest.main()
