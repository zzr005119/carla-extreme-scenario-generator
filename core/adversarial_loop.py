"""对抗性测试代理的场景间闭环编排。"""

import copy
from dataclasses import asdict, dataclass

import numpy as np

from core.adversarial_agent import (
    AdversarialTestAgentV1,
    AgentContractError,
    EpisodeResult,
    propose_candidate,
)
from core.scenario_features import FEATURE_DIM
from core.scenario_validator import require_valid_scenario


class LoopContractError(ValueError):
    """闭环编排输入或执行结果不符合契约。"""


@dataclass(frozen=True)
class FixedActionStrategy:
    """用于闭环接口冒烟的确定性动作策略。"""

    action: tuple

    def __post_init__(self):
        if len(self.action) != 15:
            raise LoopContractError("固定动作必须为 15 维")

    def select_action(self, step_index, observation):
        del step_index, observation
        return list(self.action)


class RandomActionStrategy:
    """Reproducible uniform random actions for a non-learning baseline."""

    def __init__(self, seed=20260821):
        self.rng = np.random.default_rng(int(seed))

    def select_action(self, step_index, observation):
        del step_index, observation
        return self.rng.uniform(-1.0, 1.0, size=FEATURE_DIM).tolist()


class LatinHypercubeActionStrategy:
    """Dependency-free Latin-hypercube coverage of the normalized action box."""

    def __init__(self, seed=20260821, batch_size=32):
        if int(batch_size) <= 0:
            raise LoopContractError("LHS batch_size must be greater than 0")
        self.rng = np.random.default_rng(int(seed))
        self.batch_size = int(batch_size)
        self.actions = []
        self.cursor = 0

    def _append_batch(self):
        batch = np.empty((self.batch_size, FEATURE_DIM), dtype=np.float64)
        for column in range(FEATURE_DIM):
            permutation = self.rng.permutation(self.batch_size)
            batch[:, column] = (
                permutation + self.rng.random(self.batch_size)
            ) / self.batch_size
        self.actions.extend((batch * 2.0 - 1.0).tolist())

    def select_action(self, step_index, observation):
        del step_index, observation
        if self.cursor >= len(self.actions):
            self._append_batch()
        action = self.actions[self.cursor]
        self.cursor += 1
        return list(action)


class RuleGuidedLhsActionStrategy(LatinHypercubeActionStrategy):
    """Risk-directed signs with LHS magnitudes; still a static heuristic."""

    DIRECTIONS = np.asarray(
        [1, 1, 1, 1, 1, -1, -1, 1, -1, -1, 1, -1, -1, -1, 1],
        dtype=np.float64,
    )

    def __init__(self, seed=20260821, batch_size=32, minimum_magnitude=0.25):
        if not 0.0 <= float(minimum_magnitude) <= 1.0:
            raise LoopContractError("minimum_magnitude must be in [0, 1]")
        super().__init__(seed=seed, batch_size=batch_size)
        self.minimum_magnitude = float(minimum_magnitude)

    def _append_batch(self):
        start = len(self.actions)
        super()._append_batch()
        for index in range(start, len(self.actions)):
            unit = (np.asarray(self.actions[index]) + 1.0) / 2.0
            magnitude = self.minimum_magnitude + unit * (1.0 - self.minimum_magnitude)
            self.actions[index] = (magnitude * self.DIRECTIONS).tolist()


def propose_with_retries(
    record,
    strategy,
    observation=None,
    max_attempts=1,
    step_index=0,
    config=None,
    initial_action=None,
):
    """Draw baseline actions until one satisfies the scenario constraints."""
    if int(max_attempts) <= 0:
        raise LoopContractError("max_attempts must be greater than 0")
    if not hasattr(strategy, "select_action"):
        raise LoopContractError("strategy must provide select_action")
    observation = observation or {}
    attempts = []
    selected = None
    for attempt_index in range(int(max_attempts)):
        action = (
            initial_action
            if attempt_index == 0 and initial_action is not None
            else strategy.select_action(step_index, observation)
        )
        proposal = propose_candidate(
            record,
            action,
            step_index=step_index,
            config=config,
        )
        attempts.append(
            {
                "attempt_index": attempt_index,
                "action": proposal.get("action"),
                "valid": bool(proposal["valid"]),
                "clipped": bool(proposal.get("clipped", False)),
                "fingerprint": proposal.get("fingerprint"),
                "error": proposal.get("error"),
            }
        )
        if proposal["valid"]:
            selected = proposal
            break
    return {
        "valid": selected is not None,
        "proposal": selected,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "invalid_attempt_count": sum(not item["valid"] for item in attempts),
        "first_attempt_valid": bool(attempts and attempts[0]["valid"]),
        "retry_exhausted": selected is None,
    }


@dataclass
class EpisodeExecution:
    initial_record: dict
    baseline_result: dict
    initial_observation: dict
    transitions: list
    final_record: dict
    status: str
    termination_reason: str | None

    def to_dict(self):
        return asdict(self)


class AdversarialEpisodeRunner:
    """执行“基线 → 候选 → 反馈”的单 episode 闭环。"""

    def __init__(self, agent, strategy, executor, max_agent_steps=1):
        if not isinstance(agent, AdversarialTestAgentV1):
            raise LoopContractError("agent 必须是 AdversarialTestAgentV1")
        if int(max_agent_steps) <= 0:
            raise LoopContractError("max_agent_steps 必须大于 0")
        if not callable(executor):
            raise LoopContractError("executor 必须可调用")
        self.agent = agent
        self.strategy = strategy
        self.executor = executor
        self.max_agent_steps = int(max_agent_steps)

    def run(self, initial_record, on_update=None):
        require_valid_scenario(initial_record)
        source_record = copy.deepcopy(initial_record)
        baseline_payload = self.executor(source_record, "baseline", -1)
        baseline_result = EpisodeResult.from_mapping(baseline_payload)
        if not baseline_result.successful:
            reason = baseline_result.failure_reason or "baseline_run_failure"
            execution = EpisodeExecution(
                initial_record=source_record,
                baseline_result=asdict(baseline_result),
                initial_observation={},
                transitions=[],
                final_record=source_record,
                status="failed",
                termination_reason=reason,
            )
            if on_update:
                on_update(execution.to_dict())
            return execution

        try:
            initial_observation = self.agent.reset(
                source_record,
                baseline_result=baseline_result,
            )
        except AgentContractError as exc:
            raise LoopContractError(str(exc)) from exc

        transitions = []
        status = "completed"
        termination_reason = None
        for step_index in range(self.max_agent_steps):
            action = self.strategy.select_action(
                step_index,
                initial_observation if not transitions else transitions[-1]["observation"],
            )
            proposal = self.agent.propose(action)
            if proposal["valid"]:
                result_payload = self.executor(
                    proposal["candidate"],
                    "candidate",
                    step_index,
                )
            else:
                result_payload = {}
            transition = self.agent.record_result(result_payload).to_dict()
            transition["proposal"] = proposal
            transitions.append(transition)
            if transition["terminated"]:
                status = "failed"
                termination_reason = transition["reason"]
                break
            if transition["truncated"]:
                status = "truncated"
                termination_reason = transition["reason"]
                break
            if on_update:
                on_update(
                    EpisodeExecution(
                        initial_record=source_record,
                        baseline_result=asdict(baseline_result),
                        initial_observation=initial_observation,
                        transitions=transitions,
                        final_record=copy.deepcopy(self.agent.current_record),
                        status="running",
                        termination_reason=None,
                    ).to_dict()
                )

        execution = EpisodeExecution(
            initial_record=source_record,
            baseline_result=asdict(baseline_result),
            initial_observation=initial_observation,
            transitions=transitions,
            final_record=copy.deepcopy(self.agent.current_record),
            status=status,
            termination_reason=termination_reason,
        )
        if on_update:
            on_update(execution.to_dict())
        return execution
