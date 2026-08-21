"""Optional Gymnasium adapter for the scene-between-episodes agent.

The dependency-free core in this module keeps the existing agent contract
testable in the project's CARLA environment. ``AdversarialGymEnv`` is enabled
only when Gymnasium is installed in the caller's environment.
"""

import copy
import importlib.util
from dataclasses import asdict

import numpy as np

from core.adversarial_agent import (
    AdversarialTestAgentV1,
    EpisodeResult,
    FEATURE_DIM,
    OBSERVATION_DIM,
    load_agent_config,
)
from core.scenario_validator import require_valid_scenario


class GymnasiumDependencyError(ImportError):
    """Raised when the optional Gymnasium adapter is requested without Gymnasium."""


class AdversarialEnvResetError(RuntimeError):
    """Raised when the baseline cannot initialize a new environment episode."""

    def __init__(self, result):
        self.result = EpisodeResult.from_mapping(result)
        reason = self.result.failure_reason or "baseline_run_failure"
        super().__init__(f"无法初始化对抗性环境 episode: {reason}")


class AdversarialEnvCore:
    """Gymnasium-shaped environment core without a Gymnasium dependency."""

    def __init__(self, record=None, record_sampler=None, executor=None, config=None):
        if record is None and record_sampler is None:
            raise ValueError("必须提供 record 或 record_sampler")
        if record is not None:
            require_valid_scenario(record)
        if record_sampler is not None and not callable(record_sampler):
            raise TypeError("record_sampler 必须可调用")
        if not callable(executor):
            raise TypeError("executor 必须可调用")
        self.config = config or load_agent_config()
        self.initial_record = copy.deepcopy(record) if record is not None else None
        self.record_sampler = record_sampler
        self.executor = executor
        self.agent = None
        self.current_record = None
        self.baseline_result = None
        self.initial_observation = None
        self.last_transition = None
        self._done = False

    def _select_record(self, seed=None, options=None):
        options = dict(options or {})
        sampling_info = None
        if "record" in options:
            record = copy.deepcopy(options["record"])
        elif self.record_sampler is not None:
            selected = self.record_sampler(seed, options)
            if (
                isinstance(selected, tuple)
                and len(selected) == 2
                and isinstance(selected[1], dict)
            ):
                record, sampling_info = selected
            else:
                record = selected
        else:
            record = copy.deepcopy(self.initial_record)
        record = copy.deepcopy(record)
        require_valid_scenario(record)
        return record, copy.deepcopy(sampling_info)

    @staticmethod
    def _vector(observation):
        vector = np.asarray(observation["vector"], dtype=np.float32)
        if vector.shape != (OBSERVATION_DIM,):
            raise RuntimeError(
                f"观测维度错误，应为 {(OBSERVATION_DIM,)}，实际为 {vector.shape}"
            )
        if not np.all(np.isfinite(vector)):
            raise RuntimeError("观测包含非有限值")
        if np.any(vector < 0.0) or np.any(vector > 1.0):
            raise RuntimeError("观测超出 [0, 1] 范围")
        return vector

    @staticmethod
    def _action_list(action):
        try:
            values = np.asarray(action, dtype=np.float32).reshape(-1)
        except (TypeError, ValueError):
            return action
        return values.tolist()

    def reset(self, seed=None, options=None):
        record, sampling_info = self._select_record(seed=seed, options=options)
        baseline_payload = self.executor(record, "baseline", -1)
        baseline_result = EpisodeResult.from_mapping(baseline_payload)
        if not baseline_result.successful:
            self.agent = None
            self.current_record = record
            self.baseline_result = baseline_result
            self.initial_observation = None
            self.last_transition = None
            self._done = True
            raise AdversarialEnvResetError(asdict(baseline_result))

        agent = AdversarialTestAgentV1(self.config)
        initial_observation = agent.reset(record, baseline_result=baseline_result)
        self.agent = agent
        self.current_record = copy.deepcopy(record)
        self.baseline_result = baseline_result
        self.initial_observation = initial_observation
        self.last_transition = None
        self._done = False
        info = {
            "phase": "baseline",
            "sample_id": record["sample_id"],
            "baseline_result": asdict(baseline_result),
        }
        if sampling_info is not None:
            info["sampling"] = sampling_info
        return self._vector(initial_observation), info

    def step(self, action):
        if self.agent is None:
            raise RuntimeError("必须先调用 reset")
        if self._done:
            raise RuntimeError("episode 已结束，必须先调用 reset")

        proposal = self.agent.propose(self._action_list(action))
        if proposal["valid"]:
            result_payload = self.executor(
                proposal["candidate"],
                "candidate",
                proposal["step_index"],
            )
        else:
            result_payload = {}
        transition = self.agent.record_result(result_payload).to_dict()
        self.last_transition = transition
        self.current_record = copy.deepcopy(self.agent.current_record)
        self._done = bool(transition["terminated"] or transition["truncated"])

        proposal_candidate = proposal.get("candidate")
        info = {
            "phase": "candidate",
            "sample_id": (
                proposal_candidate.get("sample_id")
                if proposal_candidate is not None
                else None
            ),
            "step_index": transition["info"]["step_index"],
            "proposal_valid": bool(proposal["valid"]),
            "action_clipped": bool(proposal.get("clipped", False)),
            "duplicate_count": transition["info"]["duplicate_count"],
            "failure_reason": transition["info"].get("failure_reason"),
            "reward_breakdown": transition["reward_breakdown"],
            "termination_reason": transition["reason"],
        }
        return (
            self._vector(transition["observation"]),
            float(transition["reward"]),
            bool(transition["terminated"]),
            bool(transition["truncated"]),
            info,
        )

    def close(self):
        close = getattr(self.executor, "close", None)
        if callable(close):
            close()


_GYMNASIUM_AVAILABLE = importlib.util.find_spec("gymnasium") is not None
_GymEnvBase = object
if _GYMNASIUM_AVAILABLE:
    import gymnasium as gym

    _GymEnvBase = gym.Env


class AdversarialGymEnv(_GymEnvBase):
    """Optional Gymnasium wrapper around :class:`AdversarialEnvCore`."""

    metadata = {"render_modes": []}

    def __init__(self, record=None, record_sampler=None, executor=None, config=None):
        if not _GYMNASIUM_AVAILABLE:
            raise GymnasiumDependencyError(
                "AdversarialGymEnv 需要可选依赖 gymnasium；"
                "先完成依赖隔离安装，再运行环境检查。"
            )
        super().__init__()
        self.core = AdversarialEnvCore(
            record=record,
            record_sampler=record_sampler,
            executor=executor,
            config=config,
        )
        self.action_space = gym.spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(FEATURE_DIM,),
            dtype=np.float32,
        )
        self.observation_space = gym.spaces.Box(
            low=0.0,
            high=1.0,
            shape=(OBSERVATION_DIM,),
            dtype=np.float32,
        )

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return self.core.reset(seed=seed, options=options)

    def step(self, action):
        return self.core.step(action)

    def close(self):
        self.core.close()
