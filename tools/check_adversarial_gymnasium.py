"""Run Gymnasium's checker against the optional adversarial environment wrapper."""

import os
import sys

import gymnasium
from gymnasium.utils.env_checker import check_env


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402


RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)


class InfiniteMockExecutor:
    """Deterministic executor for API validation; it never connects to CARLA."""

    def __init__(self):
        self.calls = []

    def __call__(self, record, phase, step_index):
        self.calls.append((record["sample_id"], phase, step_index))
        score = 30.0 if phase == "baseline" else 35.0
        return {
            "status": "completed",
            "observed_risk_score": score,
            "observed_risk_level": "medium",
            "risk_method": "heuristic_v2",
            "collision_count": 0,
            "event_count": 1,
            "run_valid": True,
            "strict_acceptance_passed": True,
            "carla_service_healthy": True,
            "run_dir": f"mock://{phase}/{step_index}",
        }


def main():
    record = load_json(RECORD_PATH)
    executor = InfiniteMockExecutor()
    env = AdversarialGymEnv(record=record, executor=executor)
    check_env(env)
    observation, info = env.reset(seed=123)
    next_observation, reward, terminated, truncated, step_info = env.step(
        env.action_space.sample()
    )
    print(f"gymnasium={gymnasium.__version__}")
    print(f"observation_shape={observation.shape}, dtype={observation.dtype}")
    print(f"action_shape={env.action_space.shape}, dtype={env.action_space.dtype}")
    print(f"reset_phase={info['phase']}, step_reward={reward:.6f}")
    print(f"step_flags=terminated:{terminated}, truncated:{truncated}")
    print(f"step_proposal_valid={step_info['proposal_valid']}")
    print(f"executor_calls={len(executor.calls)}")
    env.close()


if __name__ == "__main__":
    main()
