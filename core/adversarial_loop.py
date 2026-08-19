"""对抗性测试代理的场景间闭环编排。"""

import copy
from dataclasses import asdict, dataclass

from core.adversarial_agent import (
    AdversarialTestAgentV1,
    AgentContractError,
    EpisodeResult,
)
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
