import copy
import json
import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    OBSERVATION_DIM,
    AdversarialTestAgentV1,
    action_space_spec,
    build_observation,
    canonical_parameter_fingerprint,
    count_reward_events,
    load_agent_config,
    observation_space_spec,
    propose_candidate,
)
from core.scenario_validator import load_json  # noqa: E402


class AdversarialAgentTests(unittest.TestCase):
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
        cls.config = load_agent_config()

    def test_contract_dimensions(self):
        self.assertEqual(action_space_spec(self.config)["shape"], [15])
        self.assertEqual(observation_space_spec(self.config)["shape"], [OBSERVATION_DIM])
        observation = build_observation(self.record, config=self.config)
        self.assertEqual(len(observation["vector"]), OBSERVATION_DIM)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in observation["vector"]))

    def test_reset_accepts_strict_baseline_result(self):
        agent = AdversarialTestAgentV1(self.config)
        observation = agent.reset(
            self.record,
            baseline_result={
                "status": "completed",
                "observed_risk_score": 35.0,
                "observed_risk_level": "medium",
                "risk_method": "heuristic_v2",
                "collision_count": 0,
                "event_count": 2,
                "run_valid": True,
                "strict_acceptance_passed": True,
                "carla_service_healthy": True,
                "run_dir": "F:\\Carla\\baseline",
            },
        )
        self.assertEqual(observation["feedback"]["observed_risk_score"], 0.35)
        self.assertEqual(agent.current_record["observed_risk"]["status"], "completed")

    def test_zero_action_produces_valid_candidate(self):
        proposal = propose_candidate(self.record, [0.0] * 15, config=self.config)
        self.assertTrue(proposal["valid"], proposal["error"])
        self.assertEqual(
            canonical_parameter_fingerprint(proposal["candidate"]),
            canonical_parameter_fingerprint(self.record),
        )
        self.assertEqual(proposal["candidate"]["observed_risk"]["status"], "not_simulated")

    def test_action_is_clipped_and_marked(self):
        action = [2.0] + [0.0] * 14
        proposal = propose_candidate(self.record, action, config=self.config)
        self.assertTrue(proposal["valid"], proposal["error"])
        self.assertTrue(proposal["clipped"])
        self.assertEqual(proposal["action"][0], 1.0)

    def test_risk_delta_collision_and_event_rewards(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(self.record)
        first = agent.step(
            [0.01] * 15,
            {
                "status": "completed",
                "observed_risk_score": 30.0,
                "observed_risk_level": "medium",
                "collision_count": 0,
                "event_count": 1,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\test-run-1",
            },
        )
        self.assertFalse(first.terminated)
        second = agent.step(
            [0.01] * 15,
            {
                "status": "completed",
                "observed_risk_score": 60.0,
                "observed_risk_level": "high",
                "collision_count": 1,
                "event_count": 2,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\test-run-2",
            },
        )
        self.assertAlmostEqual(second.reward_breakdown["risk_delta"], 0.3)
        self.assertAlmostEqual(second.reward_breakdown["collision_event"], 0.5)
        self.assertAlmostEqual(second.reward_breakdown["event"], 0.05)
        self.assertGreater(second.reward, 0.0)

    def test_existing_collision_and_events_are_not_rewarded_again(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(
            self.record,
            {
                "status": "completed",
                "observed_risk_score": 94.0,
                "observed_risk_level": "critical",
                "collision_count": 42,
                "event_count": 4,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\baseline",
            },
        )
        transition = agent.step(
            [0.01] * 15,
            {
                "status": "completed",
                "observed_risk_score": 87.0,
                "observed_risk_level": "critical",
                "collision_count": 309,
                "event_count": 4,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\candidate",
            },
        )
        self.assertAlmostEqual(transition.reward_breakdown["risk_delta"], -0.07)
        self.assertEqual(transition.reward_breakdown["collision_event"], 0.0)
        self.assertEqual(transition.reward_breakdown["event"], 0.0)
        self.assertAlmostEqual(transition.reward, -0.07)

    def test_removing_baseline_collision_is_penalized_symmetrically(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(
            self.record,
            {
                "status": "completed",
                "observed_risk_score": 50.0,
                "observed_risk_level": "high",
                "collision_count": 1,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\baseline",
            },
        )
        transition = agent.step(
            [0.01] * 15,
            {
                "status": "completed",
                "observed_risk_score": 50.0,
                "observed_risk_level": "high",
                "collision_count": 0,
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\candidate",
            },
        )
        self.assertEqual(transition.reward_breakdown["collision_event"], -0.5)
        self.assertEqual(transition.reward, -0.5)

    def test_reward_event_count_filters_planned_events_and_deduplicates_reason(self):
        events = [
            {"type": "pedestrian_started"},
            {"type": "lead_vehicle_brake"},
            {"type": "collision", "frame": 1},
            {"type": "ego_safety_brake", "reason": "ttc"},
            {"type": "ego_safety_brake", "reason": "ttc"},
            {"type": "ego_safety_brake", "reason": "pedestrian"},
        ]
        self.assertEqual(count_reward_events(events, self.config), 2)

    def test_failed_run_terminates(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(self.record)
        transition = agent.step(
            [0.0] * 15,
            {
                "status": "failed",
                "run_valid": False,
                "strict_acceptance_passed": False,
                "carla_service_healthy": False,
                "collision_count": 3,
                "event_count": 4,
                "failure_reason": "server_unhealthy",
            },
        )
        self.assertTrue(transition.terminated)
        self.assertFalse(transition.truncated)
        self.assertEqual(transition.reason, "server_unhealthy")
        self.assertEqual(transition.reward_breakdown["run_failure"], -1.0)
        self.assertEqual(transition.reward_breakdown["collision_event"], 0.0)
        self.assertEqual(transition.reward_breakdown["event"], 0.0)

    def test_incomplete_completed_result_is_not_accepted(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(self.record)
        transition = agent.step(
            [0.0] * 15,
            {
                "status": "completed",
                "observed_risk_score": 50.0,
                "observed_risk_level": "high",
                "strict_acceptance_passed": True,
            },
        )
        self.assertTrue(transition.terminated)
        self.assertEqual(transition.reason, "run_failure")
        self.assertEqual(transition.reward_breakdown["run_failure"], -1.0)

    def test_repeated_scene_is_truncated(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(self.record)
        transition = None
        for index in range(3):
            transition = agent.step(
                [0.0] * 15,
                {
                    "status": "completed",
                    "observed_risk_score": 20.0,
                    "observed_risk_level": "low",
                    "strict_acceptance_passed": True,
                    "run_dir": f"F:\\Carla\\repeat-{index}",
                },
            )
            if index < 2:
                self.assertFalse(transition.truncated)
        self.assertTrue(transition.truncated)
        self.assertEqual(transition.reason, "repeated_scene")

    def test_invalid_action_dimension_terminates(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(self.record)
        transition = agent.step([0.0] * 14, {})
        self.assertTrue(transition.terminated)
        self.assertEqual(transition.reason, "invalid_candidate")
        self.assertEqual(transition.reward_breakdown["invalid_candidate"], -1.0)

    def test_max_steps_truncates(self):
        config = copy.deepcopy(self.config)
        config["termination"]["max_steps"] = 1
        agent = AdversarialTestAgentV1(config)
        agent.reset(self.record)
        transition = agent.step(
            [0.01] * 15,
            {
                "status": "completed",
                "observed_risk_score": 30.0,
                "observed_risk_level": "medium",
                "strict_acceptance_passed": True,
                "run_dir": "F:\\Carla\\max-step",
            },
        )
        self.assertFalse(transition.terminated)
        self.assertTrue(transition.truncated)
        self.assertEqual(transition.reason, "max_steps")

    def test_cli_result_payload_is_json_serializable(self):
        agent = AdversarialTestAgentV1(self.config)
        agent.reset(copy.deepcopy(self.record))
        proposal = agent.propose([0.0] * 15)
        json.dumps(proposal, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
