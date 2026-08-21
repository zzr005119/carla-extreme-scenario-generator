import os
import sys
import unittest

import numpy as np


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_loop import (  # noqa: E402
    LatinHypercubeActionStrategy,
    RandomActionStrategy,
    RuleGuidedLhsActionStrategy,
    propose_with_retries,
)
from core.adversarial_sampling import (  # noqa: E402
    ScenarioLibrarySampler,
    ScenarioSamplingError,
)
from core.adversarial_agent import load_agent_config  # noqa: E402
from core.scenario_validator import load_json, require_valid_scenario  # noqa: E402


LIBRARY_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "scenario_library_v1",
    "entries.jsonl",
)
MANIFEST_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "scenario_library_v1",
    "manifest.json",
)


class ScenarioLibrarySamplerTests(unittest.TestCase):
    def make_sampler(self):
        return ScenarioLibrarySampler(
            entries_path=LIBRARY_PATH,
            manifest_path=MANIFEST_PATH,
            seed=20260821,
        )

    def sample_sequence(self, count, seed=20260821, options=None):
        sampler = self.make_sampler()
        rows = []
        for index in range(count):
            rows.append(sampler(seed if index == 0 else None, options))
        return rows

    def test_first_cycle_covers_all_generator_risk_strata(self):
        rows = self.sample_sequence(12)
        strata = {
            (info["generator"], info["target_risk_level"])
            for _, info in rows
        }
        self.assertEqual(
            strata,
            {
                (generator, risk)
                for generator in ("lhs", "gmm", "cvae")
                for risk in ("low", "medium", "high", "critical")
            },
        )
        self.assertEqual(len({info["library_id"] for _, info in rows}), 12)

    def test_same_seed_reproduces_records_and_traffic_seeds(self):
        first = self.sample_sequence(24, seed=99)
        second = self.sample_sequence(24, seed=99)
        first_keys = [
            (info["library_id"], info["traffic_manager_seed"])
            for _, info in first
        ]
        second_keys = [
            (info["library_id"], info["traffic_manager_seed"])
            for _, info in second
        ]
        self.assertEqual(first_keys, second_keys)

    def test_filters_and_runtime_contract_are_preserved(self):
        options = {
            "generators": ["lhs"],
            "target_risk_levels": ["critical"],
            "weather_tags": ["night", "wet_road"],
            "hazard_tags": ["lead_vehicle_braking", "pedestrian_crossing"],
            "weather_match": "all",
            "hazard_match": "all",
        }
        for record, info in self.sample_sequence(6, options=options):
            require_valid_scenario(record)
            self.assertEqual(info["generator"], "lhs")
            self.assertEqual(info["target_risk_level"], "critical")
            self.assertTrue({"night", "wet_road"}.issubset(info["weather_tags"]))
            self.assertIn(
                record["scenario"]["traffic_manager_seed"],
                (20260821, 20260822, 20260823),
            )

    def test_empty_filter_result_is_explicit(self):
        sampler = self.make_sampler()
        with self.assertRaises(ScenarioSamplingError):
            sampler(
                1,
                {
                    "generators": ["lhs"],
                    "weather_tags": ["day", "night"],
                    "weather_match": "all",
                },
            )


class BaselineStrategyTests(unittest.TestCase):
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
        cls.agent_config = load_agent_config()

    def test_random_actions_are_reproducible_and_bounded(self):
        first = RandomActionStrategy(seed=7)
        second = RandomActionStrategy(seed=7)
        actions_a = [first.select_action(index, {}) for index in range(5)]
        actions_b = [second.select_action(index, {}) for index in range(5)]
        self.assertEqual(actions_a, actions_b)
        values = np.asarray(actions_a)
        self.assertTrue((values >= -1.0).all())
        self.assertTrue((values <= 1.0).all())

    def test_lhs_uses_every_bin_once_per_dimension(self):
        size = 8
        strategy = LatinHypercubeActionStrategy(seed=11, batch_size=size)
        actions = np.asarray(
            [strategy.select_action(index, {}) for index in range(size)]
        )
        bins = np.floor((actions + 1.0) * 0.5 * size).astype(int)
        bins = np.clip(bins, 0, size - 1)
        for column in range(actions.shape[1]):
            self.assertEqual(set(bins[:, column]), set(range(size)))

    def test_rule_guided_lhs_keeps_declared_directions(self):
        strategy = RuleGuidedLhsActionStrategy(
            seed=13,
            batch_size=4,
            minimum_magnitude=0.25,
        )
        actions = np.asarray(
            [strategy.select_action(index, {}) for index in range(4)]
        )
        expected_signs = np.sign(RuleGuidedLhsActionStrategy.DIRECTIONS)
        self.assertTrue((np.sign(actions) == expected_signs).all())
        self.assertTrue((np.abs(actions) >= 0.25).all())
        self.assertTrue((np.abs(actions) <= 1.0).all())

    def test_constraint_retry_preserves_failed_attempt_before_recovery(self):
        class SequenceStrategy:
            def __init__(self):
                self.actions = [[0.0] * 14, [0.0] * 15]

            def select_action(self, step_index, observation):
                del step_index, observation
                return self.actions.pop(0)

        result = propose_with_retries(
            self.record,
            SequenceStrategy(),
            max_attempts=2,
            config=self.agent_config,
        )
        self.assertTrue(result["valid"])
        self.assertFalse(result["first_attempt_valid"])
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["invalid_attempt_count"], 1)
        self.assertFalse(result["attempts"][0]["valid"])
        self.assertTrue(result["attempts"][1]["valid"])

    def test_constraint_retry_reports_exhausted_budget(self):
        class InvalidStrategy:
            def select_action(self, step_index, observation):
                del step_index, observation
                return [0.0] * 14

        result = propose_with_retries(
            self.record,
            InvalidStrategy(),
            max_attempts=3,
            config=self.agent_config,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["retry_exhausted"])
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["invalid_attempt_count"], 3)
        self.assertIsNone(result["proposal"])


if __name__ == "__main__":
    unittest.main()
