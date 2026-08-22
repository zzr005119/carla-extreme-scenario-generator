import unittest

from tools.analyze_lhs_high_proxy_boundary import (
    canonical_sample_id,
    rank_rows,
    select_independent_candidates,
)


def scored(sample_id, score, boundary, probability, std):
    return {
        "sample_id": sample_id,
        "generator": "lhs",
        "target_risk_level": "high",
        "robust_predicted_risk_score": str(score),
        "predicted_risk_mean": str(score + 1),
        "predicted_risk_std": str(std),
        "bootstrap_top_k_frequency": "0.5",
        "collision_affinity": "0.4",
        "collision_boundary_score": str(boundary),
        "predicted_collision_probability_mean": str(probability),
        "predicted_collision_probability_std": "0.1",
        "collision_propensity_base": "0.5",
    }


class LhsHighProxyBoundaryTests(unittest.TestCase):
    def test_canonical_id_strips_policy_and_repeat_suffixes(self):
        self.assertEqual(
            canonical_sample_id("lhs_high_20260817_0223_apcv1_04_sac_s20260827"),
            "lhs_high_20260817_0223",
        )

    def test_rank_rows_is_descending(self):
        rows = [scored("a", 50, 0.1, 0.2, 1), scored("b", 60, 0.2, 0.3, 2)]
        ordered, ranks = rank_rows(rows, "robust_predicted_risk_score")
        self.assertEqual([row["sample_id"] for row in ordered], ["b", "a"])
        self.assertEqual(ranks["b"], 1)
        self.assertEqual(ranks["a"], 2)

    def test_selection_excludes_used_source_and_returns_three_reasons(self):
        scored_rows = [
            scored("lhs_high_20260817_0001", 49.9, 0.3, 0.2, 3),
            scored("lhs_high_20260817_0002", 66.5, 0.5, 0.8, 4),
            scored("lhs_high_20260817_0003", 56.5, 0.6, 0.5, 7),
            scored("lhs_high_20260817_0223", 58.8, 0.1, 0.5, 6),
        ]
        pool = [{"sample_id": row["sample_id"]} for row in scored_rows]
        selected = select_independent_candidates(
            scored_rows,
            pool,
            {"lhs_high_20260817_0223"},
        )
        self.assertEqual(len(selected), 3)
        self.assertNotIn("lhs_high_20260817_0223", {row["sample_id"] for row in selected})
        self.assertEqual(
            {row["reason"] for row in selected},
            {"near_high_threshold", "near_critical_boundary", "uncertain_collision_boundary"},
        )


if __name__ == "__main__":
    unittest.main()
