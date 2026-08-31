import unittest

from tools.evaluate_carla_rl_multiscene import _evaluation_acceptance


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


if __name__ == "__main__":
    unittest.main()
