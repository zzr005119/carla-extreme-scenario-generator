import json
import os
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.analyze_adversarial_baseline_carla_results import (  # noqa: E402
    analyze_results,
)
from tools.evaluate_adversarial_baselines import load_baseline_config  # noqa: E402
from tools.prepare_adversarial_policy_carla_plan import (  # noqa: E402
    load_excluded_library_ids,
    load_policy_plan_config,
    select_independent_samples,
)
from tools.run_adversarial_baseline_carla_plan import (  # noqa: E402
    load_run_plan,
)


class AdversarialPolicyCarlaPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan_config = load_policy_plan_config()
        cls.baseline_config = load_baseline_config(
            os.path.join(
                PROJECT_ROOT,
                cls.plan_config["baseline_config_path"],
            )
        )

    def test_excluded_manifest_requires_unique_expected_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "samples.jsonl")
            with open(path, "w", encoding="utf-8") as file:
                for value in ("a", "b"):
                    file.write(json.dumps({"sampling": {"library_id": value}}))
                    file.write("\n")
            self.assertEqual(load_excluded_library_ids(path, 2), {"a", "b"})
            with self.assertRaisesRegex(ValueError, "数量不符"):
                load_excluded_library_ids(path, 3)

    def test_independent_selection_covers_all_strata_without_overlap(self):
        first, _ = select_independent_samples(
            baseline_config=self.baseline_config,
            sample_count=12,
            sample_seed=100,
            excluded_library_ids=set(),
            max_attempts=256,
        )
        excluded = {row["sampling"]["library_id"] for row in first}
        second, audit = select_independent_samples(
            baseline_config=self.baseline_config,
            sample_count=12,
            sample_seed=101,
            excluded_library_ids=excluded,
            max_attempts=512,
        )
        selected = {row["sampling"]["library_id"] for row in second}
        strata = {
            (
                row["sampling"]["generator"],
                row["sampling"]["target_risk_level"],
            )
            for row in second
        }
        self.assertFalse(selected.intersection(excluded))
        self.assertEqual(len(selected), 12)
        self.assertEqual(len(strata), 12)
        self.assertEqual(audit["excluded_overlap_count"], 0)

    def test_runner_accepts_policy_plan_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "run_plan.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "format": "adversarial_policy_carla_run_plan_v1",
                        "summary": {
                            "strategy_order": [
                                "sac_policy",
                                "rule_guided_lhs",
                            ]
                        },
                        "runs": [{"run_order": 1, "pair_id": "pair_01"}],
                    },
                    file,
                )
            self.assertEqual(
                load_run_plan(path)["format"],
                "adversarial_policy_carla_run_plan_v1",
            )

    def test_analysis_infers_two_strategy_order(self):
        rows = []
        for pair_index in (1, 2):
            pair_id = f"pair_{pair_index:02d}"
            rows.append(
                {
                    "pair_id": pair_id,
                    "phase": "baseline",
                    "strategy": None,
                    "risk_score": 50.0,
                    "collision_observed": False,
                    "strict_acceptance_passed": True,
                }
            )
            for strategy, delta in (
                ("sac_policy", 1.0),
                ("rule_guided_lhs", 2.0),
            ):
                rows.append(
                    {
                        "pair_id": pair_id,
                        "phase": "candidate",
                        "strategy": strategy,
                        "generator": "lhs",
                        "target_risk_level": "high",
                        "risk_score": 50.0 + delta,
                        "risk_delta": delta,
                        "reward": delta / 100.0,
                        "collision_observed": False,
                        "collision_count": 0,
                        "strict_acceptance_passed": True,
                    }
                )
        summary, strategies, comparisons = analyze_results(rows)
        self.assertEqual(summary["total_run_count"], 6)
        self.assertEqual(
            [row["strategy"] for row in strategies],
            ["sac_policy", "rule_guided_lhs"],
        )
        self.assertEqual(len(comparisons), 4)


if __name__ == "__main__":
    unittest.main()
