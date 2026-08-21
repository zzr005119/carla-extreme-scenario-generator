import copy
import os
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from core.adversarial_agent import (  # noqa: E402
    AdversarialTestAgentV1,
    EpisodeResult,
    canonical_parameter_fingerprint,
    load_agent_config,
)
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_baseline_carla_plan import (  # noqa: E402
    _result_payload,
    build_candidate_comparison,
    select_pair_ids,
)


class AdversarialBaselineCarlaPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent_config = load_agent_config(
            os.path.join(PROJECT_ROOT, "configs", "adversarial_agent_v1.json")
        )
        cls.record = load_json(
            os.path.join(
                PROJECT_ROOT,
                "data",
                "scenarios",
                "seed_v1",
                "example_record.json",
            )
        )

    def test_pair_selection_defaults_to_first_pair(self):
        plan = {
            "runs": [
                {"run_order": 2, "pair_id": "pair_01"},
                {"run_order": 1, "pair_id": "pair_01"},
                {"run_order": 3, "pair_id": "pair_02"},
            ]
        }
        self.assertEqual(select_pair_ids(plan), ["pair_01"])
        self.assertEqual(select_pair_ids(plan, pair_count=2), ["pair_01", "pair_02"])
        self.assertEqual(
            select_pair_ids(plan, requested_pair_ids=["pair_02"]),
            ["pair_02"],
        )
        with self.assertRaisesRegex(ValueError, "Unknown pair_id"):
            select_pair_ids(plan, requested_pair_ids=["pair_03"])

    def test_result_payload_rejects_process_failure(self):
        row = {
            "status": "completed",
            "acceptance_status": "completed",
            "acceptance_failures": "",
            "risk_score": 50.0,
            "observed_risk_level": "high",
            "collision_count": 0,
            "runtime_verified": True,
            "server_status": "healthy",
            "run_dir": "/tmp/run",
        }
        metadata = {
            "result": {"risk_evaluation": {"method": "heuristic_v2"}},
            "events": [{"type": "ego_safety_brake", "reason": "ttc"}],
        }
        result = _result_payload(row, metadata, process_returncode=2)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["strict_acceptance_passed"])
        self.assertTrue(result["carla_service_healthy"])
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["failure_reason"], "scene_exit_2")

    def test_candidate_reward_is_independent_from_shared_baseline(self):
        action = [0.0] * 15
        action[4] = 0.25
        planner_agent = AdversarialTestAgentV1(self.agent_config)
        planner_agent.reset(self.record)
        proposal = planner_agent.propose(action)
        self.assertTrue(proposal["valid"])
        candidate_record = copy.deepcopy(proposal["candidate"])
        run = {
            "run_id": "pair_01_fixed",
            "selected_action": action,
            "candidate_fingerprint": canonical_parameter_fingerprint(candidate_record),
        }
        baseline = EpisodeResult(
            observed_risk_score=94.0,
            observed_risk_level="critical",
            collision_count=42,
            event_count=4,
            run_dir="/tmp/baseline",
        )
        candidate = EpisodeResult(
            observed_risk_score=87.0,
            observed_risk_level="critical",
            collision_count=309,
            event_count=4,
            run_dir="/tmp/candidate",
        )
        comparison = build_candidate_comparison(
            self.record,
            baseline,
            run,
            candidate_record,
            candidate,
            self.agent_config,
        )
        self.assertEqual(comparison["risk_delta"], -7.0)
        self.assertAlmostEqual(comparison["reward_breakdown"]["risk_delta"], -0.07)
        self.assertEqual(comparison["reward_breakdown"]["collision_event"], 0.0)
        self.assertEqual(comparison["reward_breakdown"]["event"], 0.0)
        self.assertAlmostEqual(comparison["reward"], -0.07)


if __name__ == "__main__":
    unittest.main()
