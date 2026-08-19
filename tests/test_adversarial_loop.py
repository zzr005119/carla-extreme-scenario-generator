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
