import copy
import os
import sys
import tempfile
import unittest

import joblib
import numpy as np
from sklearn.dummy import DummyRegressor


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import EpisodeResult, load_agent_config  # noqa: E402
from core.adversarial_gym_env import AdversarialEnvCore  # noqa: E402
from core.adversarial_proxy_executor import (  # noqa: E402
    FrozenRiskProxyExecutor,
    ProxyExecutorError,
    file_sha256,
    load_proxy_executor_config,
)
from core.scenario_validator import load_json  # noqa: E402


RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)
AGENT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_agent_proxy_training_v1.json",
)


class FrozenRiskProxyExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_json(RECORD_PATH)
        cls.base_config = load_proxy_executor_config()

    def build_executor(self, directory):
        model = DummyRegressor(strategy="constant", constant=42.5)
        model.fit(np.zeros((2, 27)), np.asarray([42.5, 42.5]))
        model_path = os.path.join(directory, "selected_model.joblib")
        joblib.dump(model, model_path)
        config = copy.deepcopy(self.base_config)
        config["model"]["sha256"] = file_sha256(model_path)
        config["model"]["class"] = "sklearn.dummy.DummyRegressor"
        return FrozenRiskProxyExecutor(config=config, model_path=model_path), config

    def test_feature_contract_and_proxy_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self.build_executor(directory)
            self.assertEqual(executor.feature_vector(self.record).shape, (27,))
            payload = executor(self.record, "baseline", -1)
            self.assertEqual(payload["observed_risk_score"], 42.5)
            self.assertEqual(payload["reward_channels_available"], ["risk"])
            self.assertFalse(payload["requires_carla_service"])
            self.assertFalse(payload["carla_service_healthy"])
            self.assertTrue(EpisodeResult.from_mapping(payload).successful)

    def test_model_hash_mismatch_stops_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, config = self.build_executor(directory)
            config["model"]["sha256"] = "0" * 64
            with self.assertRaises(ProxyExecutorError):
                FrozenRiskProxyExecutor(
                    config=config,
                    model_path=executor.model_path,
                )

    def test_proxy_agent_uses_only_risk_reward_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self.build_executor(directory)
            agent_config = load_agent_config(AGENT_CONFIG_PATH)
            self.assertEqual(agent_config["reward"]["collision_event_reward"], 0.0)
            self.assertEqual(agent_config["reward"]["event_reward"], 0.0)
            env = AdversarialEnvCore(
                record=self.record,
                executor=executor,
                config=agent_config,
            )
            env.reset(seed=7)
            _, _, _, _, info = env.step([0.01] * 15)
            self.assertEqual(info["reward_breakdown"]["collision_event"], 0.0)
            self.assertEqual(info["reward_breakdown"]["event"], 0.0)
            self.assertEqual(info["evidence_kind"], "frozen_risk_proxy_inference")


if __name__ == "__main__":
    unittest.main()
