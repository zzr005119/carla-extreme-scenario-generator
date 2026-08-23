import unittest

from tools.select_lhs_high_calibration_batch import STRATA, select_batch


def scored(sample_id, score, probability, std=3.0, rank=1):
    return {
        "sample_id": sample_id,
        "generator": "lhs",
        "target_risk_level": "high",
        "robust_rank": str(rank),
        "robust_predicted_risk_score": str(score),
        "predicted_risk_mean": str(score + 1),
        "predicted_risk_std": str(std),
        "predicted_collision_probability_mean": str(probability),
        "predicted_collision_probability_std": "0.1",
        "collision_boundary_score": str(probability),
        "bootstrap_top_k_frequency": "0.5",
    }


class LhsHighCalibrationBatchTests(unittest.TestCase):
    def test_selects_one_candidate_per_supported_joint_stratum(self):
        rows = {}
        for index, spec in enumerate(STRATA):
            score = (spec["risk_min"] + spec["risk_max"]) / 2.0
            probability = (spec["prob_min"] + min(spec["prob_max"], 1.0)) / 2.0
            sample_id = f"candidate_{index:02d}"
            rows[sample_id] = scored(sample_id, score, probability, rank=index + 1)
        pool = {sample_id: {"sample_id": sample_id} for sample_id in rows}
        selected = select_batch(rows, pool, [], seed=20260823)
        self.assertEqual(len(selected), 6)
        self.assertEqual({row["stratum"] for row in selected}, {spec["stratum"] for spec in STRATA})
        self.assertEqual(sorted(row["selection_order"] for row in selected), list(range(1, 7)))

    def test_excludes_previous_ids_and_is_reproducible(self):
        rows = {}
        pool = {}
        for index, spec in enumerate(STRATA):
            sample_id = f"candidate_{index:02d}"
            score = (spec["risk_min"] + spec["risk_max"]) / 2.0
            probability = (spec["prob_min"] + min(spec["prob_max"], 1.0)) / 2.0
            rows[sample_id] = scored(sample_id, score, probability, rank=index + 1)
            pool[sample_id] = {"sample_id": sample_id}
        with self.assertRaisesRegex(ValueError, "No candidate available"):
            select_batch(rows, pool, ["candidate_00", "candidate_01", "candidate_02", "candidate_03", "candidate_04", "candidate_05"])
        first = select_batch(rows, pool, [], seed=7)
        second = select_batch(rows, pool, [], seed=7)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
