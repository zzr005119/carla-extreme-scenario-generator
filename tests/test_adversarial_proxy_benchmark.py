import copy
import json
import os
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.benchmark_adversarial_sb3_proxy import (  # noqa: E402
    ExcludingScenarioSampler,
    aggregate_strategy_summaries,
    load_benchmark_config,
    pairwise_policy_comparisons,
    sample_evaluation_records,
    summarize_strategy_rows,
)
from tools.evaluate_adversarial_baselines import load_baseline_config  # noqa: E402


class AdversarialProxyBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_benchmark_config()
        cls.baseline_config = load_baseline_config(
            os.path.join(PROJECT_ROOT, cls.config["baseline_config_path"])
        )

    def test_evaluation_records_are_unique_and_cover_twelve_strata(self):
        rows = sample_evaluation_records(
            self.baseline_config,
            sample_count=24,
            sample_seed=123,
        )
        self.assertEqual(
            len({row["sampling"]["library_id"] for row in rows}),
            24,
        )
        self.assertEqual(
            len(
                {
                    (
                        row["sampling"]["generator"],
                        row["sampling"]["target_risk_level"],
                    )
                    for row in rows
                }
            ),
            12,
        )

    def test_training_sampler_excludes_frozen_evaluation_records(self):
        evaluation_rows = sample_evaluation_records(
            self.baseline_config,
            sample_count=24,
            sample_seed=321,
        )
        excluded = {
            row["sampling"]["library_id"] for row in evaluation_rows
        }
        sampler = ExcludingScenarioSampler(
            entries_path=os.path.join(
                PROJECT_ROOT,
                self.baseline_config["scenario_library_path"],
            ),
            manifest_path=os.path.join(
                PROJECT_ROOT,
                self.baseline_config["scenario_library_manifest_path"],
            ),
            seed=999,
            filters=self.baseline_config["filters"],
            excluded_library_ids=excluded,
            max_skips=256,
        )
        accepted = [
            sampler(999 if index == 0 else None)[1]
            for index in range(48)
        ]
        self.assertFalse(
            {row["library_id"] for row in accepted}.intersection(excluded)
        )
        self.assertFalse(sampler.snapshot()["excluded_entry_seen"])

    @staticmethod
    def make_row(strategy, seed, library_id, delta):
        return {
            "strategy": strategy,
            "replicate_seed": seed,
            "library_id": library_id,
            "candidate_proxy_evaluated": True,
            "proposal_valid": True,
            "candidate_proxy_score": 50.0 + delta,
            "proxy_score_delta": delta,
            "reward": delta / 100.0,
            "action_attempt_count": 1,
            "candidate_fingerprint": f"{strategy}-{seed}-{library_id}",
            "mean_absolute_action": 0.5,
            "normalized_parameter_shift": 0.04,
        }

    def test_summary_aggregation_keeps_replicate_variance(self):
        rows_a = [self.make_row("ppo_policy", 1, "a", 1.0)]
        rows_b = [self.make_row("ppo_policy", 2, "a", 3.0)]
        summaries = [
            summarize_strategy_rows(rows_a),
            summarize_strategy_rows(rows_b),
        ]
        aggregate = aggregate_strategy_summaries(summaries)["ppo_policy"]
        self.assertEqual(aggregate["replicate_count"], 2)
        self.assertEqual(
            aggregate["mean_proxy_score_delta"]["mean"],
            2.0,
        )
        self.assertGreater(
            aggregate["mean_proxy_score_delta"]["sample_std"],
            0.0,
        )

    def test_pairwise_comparison_uses_shared_seed_and_library_id(self):
        rows = []
        for seed in (1, 2):
            rows.append(self.make_row("ppo_policy", seed, "a", 3.0))
            rows.append(self.make_row("rule_guided_lhs", seed, "a", 1.0))
            rows.append(self.make_row("sac_policy", seed, "a", 0.0))
        comparisons = pairwise_policy_comparisons(rows)
        ppo = comparisons["ppo_policy_vs_rule_guided_lhs"]
        sac = comparisons["sac_policy_vs_rule_guided_lhs"]
        self.assertEqual(ppo["policy_win_count"], 2)
        self.assertEqual(sac["policy_loss_count"], 2)

    def test_incomplete_stratified_cycle_is_rejected(self):
        config = copy.deepcopy(self.config)
        config["evaluation"]["sample_count"] = 13
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "benchmark.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(config, file)
            with self.assertRaisesRegex(ValueError, "12 分层周期"):
                load_benchmark_config(path)


if __name__ == "__main__":
    unittest.main()
