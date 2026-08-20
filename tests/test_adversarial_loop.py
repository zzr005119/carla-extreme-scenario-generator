import copy
import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import AdversarialTestAgentV1, load_agent_config  # noqa: E402
from core.adversarial_loop import (  # noqa: E402
    AdversarialEpisodeRunner,
    FixedActionStrategy,
)
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_episode import (  # noqa: E402
    apply_route_profile,
    build_carla_config,
    load_loop_config,
)


class SequenceExecutor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, record, phase, step_index):
        self.calls.append((record["sample_id"], phase, step_index))
        return self.results.pop(0)


class SequenceActionStrategy:
    def __init__(self, actions):
        self.actions = [list(action) for action in actions]
        self.observations = []

    def select_action(self, step_index, observation):
        self.observations.append((step_index, copy.deepcopy(observation)))
        return self.actions.pop(0)


def successful_result(score, level, run_dir):
    return {
        "status": "completed",
        "observed_risk_score": score,
        "observed_risk_level": level,
        "risk_method": "heuristic_v2",
        "collision_count": 0,
        "event_count": 2,
        "run_valid": True,
        "strict_acceptance_passed": True,
        "carla_service_healthy": True,
        "run_dir": run_dir,
    }


def failed_result(reason):
    return {
        "status": "failed",
        "run_valid": False,
        "strict_acceptance_passed": False,
        "carla_service_healthy": False,
        "failure_reason": reason,
    }


class AdversarialLoopTests(unittest.TestCase):
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
        cls.agent_config = load_agent_config()
        cls.loop_config = load_loop_config()

    def test_baseline_and_candidate_form_one_closed_loop_transition(self):
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(55.0, "high", "mock://candidate"),
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(self.agent_config),
            FixedActionStrategy(tuple(self.loop_config["fixed_action"])),
            executor,
            max_agent_steps=1,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "completed")
        self.assertEqual(len(execution.transitions), 1)
        self.assertEqual([call[1] for call in executor.calls], ["baseline", "candidate"])
        self.assertAlmostEqual(
            execution.transitions[0]["reward_breakdown"]["risk_delta"],
            0.25,
        )
        self.assertEqual(execution.final_record["observed_risk"]["score"], 55.0)

    def test_baseline_failure_stops_before_candidate(self):
        executor = SequenceExecutor(
            [
                {
                    "status": "failed",
                    "run_valid": False,
                    "strict_acceptance_passed": False,
                    "carla_service_healthy": False,
                    "failure_reason": "baseline_server_unhealthy",
                }
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(self.agent_config),
            FixedActionStrategy(tuple(self.loop_config["fixed_action"])),
            executor,
            max_agent_steps=1,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.termination_reason, "baseline_server_unhealthy")
        self.assertEqual(len(execution.transitions), 0)
        self.assertEqual(len(executor.calls), 1)

    def test_three_step_loop_carries_each_result_into_next_candidate(self):
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(35.0, "medium", "mock://candidate-0"),
                successful_result(40.0, "medium", "mock://candidate-1"),
                successful_result(45.0, "medium", "mock://candidate-2"),
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(self.agent_config),
            FixedActionStrategy(tuple(self.loop_config["fixed_action"])),
            executor,
            max_agent_steps=3,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "completed")
        self.assertEqual(len(execution.transitions), 3)
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [("baseline", -1), ("candidate", 0), ("candidate", 1), ("candidate", 2)],
        )
        candidate_ids = [
            transition["candidate"]["sample_id"]
            for transition in execution.transitions
        ]
        self.assertEqual(len(set(candidate_ids)), 3)
        self.assertEqual(
            [
                transition["candidate"]["observed_risk"]["score"]
                for transition in execution.transitions
            ],
            [35.0, 40.0, 45.0],
        )
        self.assertEqual(
            [
                transition["observation"]["feedback"]["observed_risk_score"]
                for transition in execution.transitions
            ],
            [0.35, 0.4, 0.45],
        )

    def test_candidate_failure_stops_remaining_steps_and_preserves_last_success(self):
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(35.0, "medium", "mock://candidate-0"),
                failed_result("candidate_route_acceptance_failed"),
                successful_result(90.0, "critical", "mock://must-not-run"),
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(self.agent_config),
            FixedActionStrategy(tuple(self.loop_config["fixed_action"])),
            executor,
            max_agent_steps=3,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "failed")
        self.assertEqual(
            execution.termination_reason,
            "candidate_route_acceptance_failed",
        )
        self.assertEqual(len(execution.transitions), 2)
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [("baseline", -1), ("candidate", 0), ("candidate", 1)],
        )
        self.assertEqual(len(executor.results), 1)
        failed_transition = execution.transitions[-1]
        self.assertTrue(failed_transition["terminated"])
        self.assertFalse(failed_transition["truncated"])
        self.assertEqual(
            failed_transition["reward_breakdown"]["run_failure"],
            -1.0,
        )
        self.assertEqual(
            execution.final_record["observed_risk"]["run_dir"],
            "mock://candidate-0",
        )

    def test_invalid_candidate_can_skip_execution_and_recover_next_step(self):
        agent_config = copy.deepcopy(self.agent_config)
        agent_config["termination"]["terminate_on_invalid_candidate"] = False
        strategy = SequenceActionStrategy(
            [
                [0.0] * 14,
                self.loop_config["fixed_action"],
            ]
        )
        executor = SequenceExecutor(
            [
                successful_result(30.0, "medium", "mock://baseline"),
                successful_result(42.0, "medium", "mock://candidate-1"),
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(agent_config),
            strategy,
            executor,
            max_agent_steps=2,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "completed")
        self.assertIsNone(execution.termination_reason)
        self.assertEqual(len(execution.transitions), 2)
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [("baseline", -1), ("candidate", 1)],
        )
        invalid_transition, recovered_transition = execution.transitions
        self.assertIsNone(invalid_transition["candidate"])
        self.assertFalse(invalid_transition["terminated"])
        self.assertEqual(invalid_transition["reason"], "invalid_candidate")
        self.assertEqual(
            invalid_transition["reward_breakdown"]["invalid_candidate"],
            -1.0,
        )
        self.assertEqual(
            recovered_transition["candidate"]["sample_id"],
            f"{self.record['sample_id']}_adv_0001",
        )
        self.assertEqual(
            strategy.observations[1][1]["sample_id"],
            self.record["sample_id"],
        )
        self.assertEqual(execution.final_record["observed_risk"]["score"], 42.0)

    def test_repeated_candidates_truncate_episode_before_step_limit(self):
        executor = SequenceExecutor(
            [
                successful_result(20.0, "low", "mock://baseline"),
                successful_result(20.0, "low", "mock://repeat-0"),
                successful_result(20.0, "low", "mock://repeat-1"),
                successful_result(20.0, "low", "mock://repeat-2"),
                successful_result(90.0, "critical", "mock://must-not-run"),
            ]
        )
        runner = AdversarialEpisodeRunner(
            AdversarialTestAgentV1(self.agent_config),
            FixedActionStrategy(tuple([0.0] * 15)),
            executor,
            max_agent_steps=5,
        )
        execution = runner.run(copy.deepcopy(self.record))
        self.assertEqual(execution.status, "truncated")
        self.assertEqual(execution.termination_reason, "repeated_scene")
        self.assertEqual(len(execution.transitions), 3)
        self.assertEqual(
            [transition["info"]["duplicate_count"] for transition in execution.transitions],
            [1, 2, 3],
        )
        self.assertTrue(execution.transitions[-1]["truncated"])
        self.assertEqual(
            execution.transitions[-1]["reward_breakdown"]["duplicate"],
            -0.25,
        )
        self.assertEqual(
            [call[1:] for call in executor.calls],
            [
                ("baseline", -1),
                ("candidate", 0),
                ("candidate", 1),
                ("candidate", 2),
            ],
        )
        self.assertEqual(len(executor.results), 1)

    def test_loop_config_and_route_profile_compile_scene04_config(self):
        base_config = load_json(
            os.path.join(PROJECT_ROOT, "configs", "multi_hazard_rainy_night.json")
        )
        route_profile = load_json(
            os.path.join(
                PROJECT_ROOT,
                "configs",
                "route_control_profiles",
                "waypoint_follower_v1.json",
            )
        )
        profiled = apply_route_profile(base_config, route_profile)
        self.assertTrue(profiled["traffic"]["route_lock_enabled"])
        self.assertEqual(profiled["sensors"]["camera"]["width"], 640)
        compiled = build_carla_config(
            self.record,
            base_config,
            route_profile,
            "loop_smoke",
            os.path.join(PROJECT_ROOT, "output"),
            8100,
        )
        self.assertEqual(compiled["traffic"]["route_control_mode"], "waypoint_follower")
        self.assertEqual(compiled["scenario"]["traffic_manager_port"], 8100)
        self.assertTrue(compiled["sensors"]["rgb"]["enabled"])
        self.assertFalse(compiled["sensors"]["depth"]["enabled"])


if __name__ == "__main__":
    unittest.main()
