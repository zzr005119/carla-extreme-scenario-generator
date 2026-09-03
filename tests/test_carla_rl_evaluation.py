import unittest

from tools.evaluate_carla_rl_multiscene import (
    _better_candidate,
    _early_stop_reason,
    _effect_summary,
    _evaluation_acceptance,
    _evaluation_policy,
    _materially_improved,
    _select_candidate,
)


def _row(*, invalid=0, strict=2, failed=0, complete=True):
    return {
        "baseline": {"strict_acceptance_passed": True},
        "candidate_stats": {
            "proposal_count": invalid + 2,
            "valid_proposal_count": 2,
            "invalid_proposal_count": invalid,
            "execution_count": 2,
            "strict_execution_count": strict,
            "failed_execution_count": failed,
        },
        "candidate_coverage": {"candidate_run_completed": complete},
        "candidate_acceptance": {
            "run_dir": "runtime/candidate" if complete else None,
            "observed_risk_score": 42.0 if complete else None,
            "observed_risk_level": "medium" if complete else None,
            "risk_method": "heuristic_v2" if complete else None,
            "run_valid": complete,
            "carla_service_healthy": complete,
            "strict_acceptance_passed": complete,
        },
    }


class CarlaRLEvaluationAcceptanceTests(unittest.TestCase):
    def test_all_four_gates_pass_for_complete_rows(self):
        result = _evaluation_acceptance([_row(), _row()])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["passed_check_count"], 4)
        self.assertEqual(result["checks"]["candidate_condition_validity"]["actual"], 2)

    def test_invalid_candidate_fails_condition_and_downstream_evidence_gates(self):
        result = _evaluation_acceptance([_row(invalid=1, strict=1, failed=1, complete=False)])
        self.assertEqual(result["status"], "failed")
        self.assertIn("candidate_condition_validity", result["checks"])
        self.assertFalse(result["checks"]["candidate_condition_validity"]["passed"])
        self.assertFalse(result["checks"]["candidate_runtime_strict_acceptance"]["passed"])
        self.assertFalse(result["checks"]["candidate_evidence_completeness"]["passed"])

    def test_p3_1_selects_best_strict_candidate_and_stops_on_patience(self):
        policy = _evaluation_policy(
            {
                "evaluation": {
                    "selection_mode": "best_so_far",
                    "early_stop": {
                        "enabled": True,
                        "target_score": 95.0,
                        "patience_steps": 3,
                        "min_improvement": 0.5,
                    },
                }
            }
        )
        first = {
            "score": 72.0,
            "run_dir": "runtime/first",
            "risk_method": "heuristic_v2",
            "run_valid": True,
            "strict_acceptance_passed": True,
            "carla_service_healthy": True,
        }
        lower = dict(first, score=60.0, run_dir="runtime/lower")
        best = _better_candidate(first, None)
        best = _better_candidate(lower, best)
        self.assertIs(best, first)
        self.assertIs(_select_candidate(best, lower, policy), first)
        self.assertTrue(_materially_improved(None, 72.0, 0.5))
        self.assertFalse(_materially_improved(72.0, 72.0, 0.5))
        self.assertEqual(
            _early_stop_reason(best, 3, policy),
            "no_material_improvement",
        )

    def test_v1_default_uses_last_successful_without_early_stop(self):
        policy = _evaluation_policy({})
        best = {"score": 80.0}
        last = {"score": 50.0}
        self.assertEqual(policy["selection_mode"], "last_successful")
        self.assertFalse(policy["early_stop"]["enabled"])
        self.assertIs(_select_candidate(best, last, policy), last)
        self.assertIsNone(_early_stop_reason(best, 999, policy))

    def test_effect_summary_reports_selection_gain_over_last(self):
        result = _effect_summary(
            [
                {
                    "generator": "lhs",
                    "target_risk_level": "high",
                    "baseline": {"score": 40.0},
                    "selected_candidate": {"score": 70.0},
                    "last_candidate": {"score": 50.0},
                }
            ]
        )
        self.assertEqual(result["delta_mean"], 30.0)
        self.assertEqual(result["selection_gain_over_last_mean"], 20.0)
        self.assertEqual(result["risk_increase_count"], 1)


if __name__ == "__main__":
    unittest.main()
