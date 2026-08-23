import json
import os
import tempfile
import unittest

from tools.calibrate_lhs_high_boundary import (
    build_independent_calibration,
    calibrate,
    summarize_repeat_direction,
)


def independent_row(sample_id, proxy, observed, level, probability, collision):
    return {
        "run_id": sample_id + "_run",
        "sample_id": sample_id,
        "selection_metadata": {
            "reason": "test",
            "robust_predicted_risk_score": proxy,
            "predicted_risk_mean": proxy + 1,
            "predicted_risk_std": 2,
            "predicted_collision_probability_mean": probability,
            "collision_boundary_score": probability,
        },
        "risk_score": observed,
        "observed_risk_level": level,
        "collision_count": 1 if collision else 0,
        "collision_observed": collision,
        "strict_acceptance_passed": True,
        "risk_method": "heuristic_v2",
        "carla_client_version": "0.9.16",
        "carla_server_version": "0.9.16",
    }


class LhsHighProxyCalibrationTests(unittest.TestCase):
    def test_independent_calibration_reports_bias_and_boundary_confusion(self):
        rows = [
            independent_row("a", 49.95, 46.417, "medium", 0.21, False),
            independent_row("b", 66.56, 79.118, "critical", 0.79, True),
            independent_row("c", 56.58, 79.856, "critical", 0.41, True),
        ]
        summary, table = build_independent_calibration(rows)
        self.assertEqual(summary["sample_count"], 3)
        self.assertAlmostEqual(summary["risk_score"]["spearman_rho"], 0.5)
        self.assertEqual(summary["risk_score"]["exact_level_match_count"], 1)
        self.assertEqual(summary["danger_threshold_high"]["true_positive"], 2)
        self.assertEqual(summary["collision_probability"]["false_negative"], 1)
        self.assertEqual(len(table), 3)

    def test_repeat_direction_is_separate_from_independent_count(self):
        proxy = [
            {"strategy": "sac_policy", "proxy_score_delta": "4.791188"},
            {"strategy": "rule_guided_lhs", "proxy_score_delta": "8.456418"},
        ]
        repeats = [
            {"strategy": "sac_policy", "risk_delta": "29.291", "collision_change": "introduced"},
            {"strategy": "sac_policy", "risk_delta": "29.143", "collision_change": "introduced"},
            {"strategy": "rule_guided_lhs", "risk_delta": "34.295", "collision_change": "introduced"},
            {"strategy": "rule_guided_lhs", "risk_delta": "33.541", "collision_change": "introduced"},
        ]
        summary = summarize_repeat_direction(proxy, repeats)
        self.assertTrue(summary["direction_consistent"])
        self.assertEqual(summary["strategies"][0]["repeat_measurement_count"], 2)
        self.assertEqual(summary["strategies"][1]["collision_introduced_count"], 2)

    def test_calibration_format_can_be_versioned_without_changing_metrics(self):
        rows = [
            independent_row("a", 49.95, 46.417, "medium", 0.21, False),
            independent_row("b", 66.56, 79.118, "critical", 0.79, True),
        ]
        repeat_proxy = [{"strategy": "sac_policy", "proxy_score_delta": "4.0"}]
        repeat_rows = [{"strategy": "sac_policy", "risk_delta": "10.0", "collision_change": "introduced"}]
        summary, _ = calibrate(
            rows,
            ranked_rows=None,
            proxy_rows=repeat_proxy,
            repeat_rows=repeat_rows,
            calibration_format="lhs_high_proxy_calibration_v2",
        )
        self.assertEqual(summary["format"], "lhs_high_proxy_calibration_v2")
        self.assertEqual(summary["independent_calibration"]["sample_count"], 2)


if __name__ == "__main__":
    unittest.main()
