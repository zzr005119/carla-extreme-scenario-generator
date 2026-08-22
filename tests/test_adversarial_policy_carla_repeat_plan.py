import json
import os
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in __import__("sys").path:
    __import__("sys").path.insert(0, PROJECT_ROOT)

from tools.prepare_adversarial_policy_carla_repeat_plan import (  # noqa: E402
    _group_source_runs,
    load_repeat_plan_config,
)


class AdversarialPolicyCarlaRepeatPlanTests(unittest.TestCase):
    def test_config_schema_and_seed_contract(self):
        config = load_repeat_plan_config()
        self.assertEqual(config["selected_pair_ids"], ["apcv1_pair_02", "apcv1_pair_07", "apcv1_pair_08"])
        self.assertEqual(config["traffic_manager_seeds"], [20260824, 20260825, 20260826])

    def test_source_pairs_must_have_one_baseline_and_two_candidates(self):
        plan = {"runs": [
            {"pair_id": "p", "phase": "baseline", "strategy": None},
            {"pair_id": "p", "phase": "candidate", "strategy": "sac_policy"},
            {"pair_id": "p", "phase": "candidate", "strategy": "rule_guided_lhs"},
        ]}
        grouped = _group_source_runs(plan, ["p"])
        self.assertEqual(len(grouped["p"]), 3)
        broken = {"runs": plan["runs"][:-1]}
        with self.assertRaises(ValueError):
            _group_source_runs(broken, ["p"])

    def test_config_rejects_duplicate_seed(self):
        config = load_repeat_plan_config()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            config["traffic_manager_seeds"] = [1, 1]
            with open(path, "w", encoding="utf-8") as file:
                json.dump(config, file)
            with self.assertRaises(ValueError):
                load_repeat_plan_config(path)


if __name__ == "__main__":
    unittest.main()
