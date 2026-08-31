"""阶段四对抗性测试代理 V1 的纯 Python 契约。

该模块只负责场景间迭代的候选变异、观测构造、奖励计算和安全终止。
CARLA 运行器通过 ``propose`` 取得候选场景，完成一次实机运行后再将
结构化结果交给 ``record_result``。因此本模块不依赖 gymnasium、Stable-Baselines3
或 CARLA Python API。
"""

import copy
import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass

from core.scenario_features import (
    CONDITION_DIM,
    FEATURE_DIM,
    FEATURE_NAMES,
    RISK_LEVELS,
    build_generated_record,
    encode_record_condition,
    normalize_vector,
    parameter_vector,
    project_requested_weather_constraints,
)
from core.scenario_validator import load_json, require_valid_scenario
from core.scenario_validator import validate_schema_value


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_agent_v1.json",
)
DEFAULT_CONFIG_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_agent_v1.schema.json",
)

OBSERVATION_FEEDBACK_FIELDS = (
    "observed_risk_score",
    "collision_count",
    "event_count",
    "run_valid",
    "strict_acceptance_passed",
    "repeat_count",
    "step_fraction",
)
OBSERVATION_DIM = FEATURE_DIM + CONDITION_DIM + len(OBSERVATION_FEEDBACK_FIELDS)


class AgentContractError(ValueError):
    """输入不符合对抗性代理 V1 契约。"""


def _finite_number(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AgentContractError(f"{name} 必须为有限数值") from exc
    if not math.isfinite(number):
        raise AgentContractError(f"{name} 必须为有限数值")
    return number


def _as_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_agent_config(
    path=DEFAULT_CONFIG_PATH,
    schema_path=DEFAULT_CONFIG_SCHEMA_PATH,
):
    """读取并校验代理配置，避免运行时悄悄发生维度漂移。"""
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    schema_errors = validate_schema_value(config, schema)
    if schema_errors:
        raise AgentContractError("\n".join(schema_errors))
    action = config.get("action_space", {})
    observation = config.get("observation_space", {})
    reward = config.get("reward", {})
    termination = config.get("termination", {})
    if action.get("dimension") != FEATURE_DIM:
        raise AgentContractError(
            f"动作维度必须为 {FEATURE_DIM}，实际为 {action.get('dimension')}"
        )
    if observation.get("dimension") != OBSERVATION_DIM:
        raise AgentContractError(
            f"观测维度必须为 {OBSERVATION_DIM}，实际为 {observation.get('dimension')}"
        )
    if tuple(action.get("feature_names", ())) != FEATURE_NAMES:
        raise AgentContractError("动作 feature_names 与项目 15 维参数顺序不一致")
    if tuple(observation.get("feedback_fields", ())) != OBSERVATION_FEEDBACK_FIELDS:
        raise AgentContractError("观测 feedback_fields 与代理契约不一致")
    if float(action.get("low", -1.0)) >= float(action.get("high", 1.0)):
        raise AgentContractError("动作空间 low 必须小于 high")
    if float(action.get("step_size", 0.0)) <= 0.0:
        raise AgentContractError("动作 step_size 必须大于 0")
    if int(termination.get("max_steps", 0)) <= 0:
        raise AgentContractError("termination.max_steps 必须大于 0")
    if int(termination.get("max_consecutive_duplicates", 0)) <= 0:
        raise AgentContractError(
            "termination.max_consecutive_duplicates 必须大于 0"
        )
    required_rewards = (
        "comparison_mode",
        "risk_delta_weight",
        "collision_event_reward",
        "event_reward",
        "invalid_candidate_penalty",
        "duplicate_penalty",
        "run_failure_penalty",
        "event_types",
    )
    missing = [name for name in required_rewards if name not in reward]
    if missing:
        raise AgentContractError(f"缺少奖励配置: {missing}")
    if reward["comparison_mode"] != "relative_capped_delta":
        raise AgentContractError("reward.comparison_mode 必须为 relative_capped_delta")
    return config


def count_reward_events(events, config=None):
    """Count distinct configured safety-event signatures for reward input."""
    config = config or load_agent_config()
    allowed_types = set(config["reward"]["event_types"])
    signatures = set()
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type not in allowed_types:
            continue
        reason = str(event.get("reason") or "").strip()
        signatures.add((event_type, reason))
    return len(signatures)


def action_space_spec(config=None):
    config = config or load_agent_config()
    action = config["action_space"]
    return {
        "type": action.get("type", "normalized_delta"),
        "shape": [FEATURE_DIM],
        "low": float(action["low"]),
        "high": float(action["high"]),
        "step_size": float(action["step_size"]),
        "feature_names": list(FEATURE_NAMES),
        "clip_out_of_range": bool(action.get("clip_out_of_range", True)),
    }


def observation_space_spec(config=None):
    config = config or load_agent_config()
    observation = config["observation_space"]
    return {
        "type": observation.get("type", "box"),
        "shape": [OBSERVATION_DIM],
        "low": float(observation.get("low", 0.0)),
        "high": float(observation.get("high", 1.0)),
        "segments": {
            "parameter_vector": FEATURE_DIM,
            "condition_vector": CONDITION_DIM,
            "feedback": list(OBSERVATION_FEEDBACK_FIELDS),
        },
    }


def _validate_action(action, config):
    if not isinstance(action, (list, tuple)):
        raise AgentContractError("action 必须是长度为 15 的数组")
    if len(action) != FEATURE_DIM:
        raise AgentContractError(
            f"action 长度必须为 {FEATURE_DIM}，实际为 {len(action)}"
        )
    low = float(config["action_space"].get("low", -1.0))
    high = float(config["action_space"].get("high", 1.0))
    clip = bool(config["action_space"].get("clip_out_of_range", True))
    values = []
    clipped = False
    for index, value in enumerate(action):
        number = _finite_number(value, f"action[{index}]")
        if number < low or number > high:
            if not clip:
                raise AgentContractError(
                    f"action[{index}] 超出 [{low}, {high}]"
                )
            number = min(high, max(low, number))
            clipped = True
        values.append(number)
    return values, clipped


def canonical_parameter_fingerprint(record, precision=6):
    """基于 15 维参数生成稳定指纹，用于重复候选检测。"""
    values = parameter_vector(record).tolist()
    payload = json.dumps(
        [round(float(value), precision) for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _base_sample_id(sample_id):
    return str(sample_id).split("_adv_", 1)[0]


def propose_candidate(record, action, step_index=0, config=None):
    """将归一化增量动作映射为候选场景。

    返回值始终是可序列化字典；参数或语义校验失败时不会抛出 CARLA
    相关异常，而是返回 ``valid=False``，由上层按安全终止处理。
    """
    config = config or load_agent_config()
    require_valid_scenario(record)
    try:
        normalized_action, clipped = _validate_action(action, config)
    except AgentContractError as exc:
        return {
            "valid": False,
            "candidate": None,
            "action": list(action) if isinstance(action, (list, tuple)) else action,
            "clipped": False,
            "fingerprint": None,
            "error": str(exc),
            "step_index": int(step_index),
        }

    current = normalize_vector(parameter_vector(record), clip=True).tolist()
    step_size = float(config["action_space"].get("step_size", 0.08))
    proposed = [
        min(1.0, max(0.0, current[index] + normalized_action[index] * step_size))
        for index in range(FEATURE_DIM)
    ]
    constraints = config.get("candidate_constraints", {})
    projection = {
        "enabled": bool(constraints.get("project_requested_weather", False)),
        "applied": False,
        "requested_tags": list(record["conditions"]["weather_tags"]),
        "before_tags": None,
        "raw_satisfied": None,
        "after_tags": None,
        "changed_fields": [],
        "satisfied": None,
    }
    candidate_values = proposed
    if projection["enabled"]:
        candidate_values, projection = project_requested_weather_constraints(
            proposed,
            record["conditions"]["weather_tags"],
        )
    sample_suffix = f"_adv_{int(step_index):04d}"
    sample_id = f"{_base_sample_id(record['sample_id'])[:64 - len(sample_suffix)]}{sample_suffix}"
    try:
        candidate = build_generated_record(
            candidate_values,
            record["conditions"]["target_risk_level"],
            record["conditions"]["weather_tags"],
            sample_id=sample_id,
            generator="adversarial_agent_v1",
            generator_seed=record["provenance"]["generator_seed"],
            source_kind="model_generated",
            duration_seconds=record["scenario"]["duration_seconds"],
            traffic_manager_seed=record["scenario"]["traffic_manager_seed"],
        )
        require_valid_scenario(candidate)
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "valid": False,
            "candidate": None,
            "action": normalized_action,
            "clipped": clipped,
            "fingerprint": None,
            "error": str(exc),
            "step_index": int(step_index),
            "constraint_projection": projection,
        }
    return {
        "valid": True,
        "candidate": candidate,
        "action": normalized_action,
        "clipped": clipped,
        "fingerprint": canonical_parameter_fingerprint(candidate),
        "error": None,
        "step_index": int(step_index),
        "constraint_projection": projection,
    }


def build_observation(record, feedback=None, config=None):
    """构造固定 34 维、范围为 [0, 1] 的观测。"""
    config = config or load_agent_config()
    require_valid_scenario(record)
    feedback = dict(feedback or {})
    collision_cap = max(
        1.0,
        float(config["reward"].get("collision_event_cap", 1.0)),
    )
    event_cap = max(1.0, float(config["reward"].get("event_cap", 4.0)))
    max_steps = max(1.0, float(config["termination"].get("max_steps", 1)))
    observed = record.get("observed_risk", {})
    score = feedback.get("observed_risk_score", observed.get("score"))
    score = 0.0 if score is None else min(100.0, max(0.0, _finite_number(score, "observed_risk_score"))) / 100.0
    collision_count = min(
        collision_cap,
        max(0.0, _finite_number(feedback.get("collision_count", 0), "collision_count")),
    ) / collision_cap
    event_count = min(
        event_cap,
        max(0.0, _finite_number(feedback.get("event_count", 0), "event_count")),
    ) / event_cap
    run_valid = 1.0 if _as_bool(feedback.get("run_valid"), observed.get("status") == "completed") else 0.0
    strict = 1.0 if _as_bool(feedback.get("strict_acceptance_passed"), observed.get("status") == "completed") else 0.0
    repeat_count = min(
        1.0,
        max(0.0, _finite_number(feedback.get("repeat_count", 0), "repeat_count"))
        / max(1.0, float(config["termination"].get("max_consecutive_duplicates", 1))),
    )
    step_fraction = min(
        1.0,
        max(0.0, _finite_number(feedback.get("step_index", 0), "step_index")) / max_steps,
    )
    parameter_values = normalize_vector(parameter_vector(record), clip=True).tolist()
    condition_values = encode_record_condition(record).tolist()
    feedback_values = [
        score,
        collision_count,
        event_count,
        run_valid,
        strict,
        repeat_count,
        step_fraction,
    ]
    vector = [round(float(value), 6) for value in parameter_values + condition_values + feedback_values]
    if len(vector) != OBSERVATION_DIM:
        raise AgentContractError(f"观测维度错误，应为 {OBSERVATION_DIM}")
    return {
        "vector": vector,
        "parameter_vector": [round(float(value), 6) for value in parameter_values],
        "condition_vector": [round(float(value), 6) for value in condition_values],
        "feedback": {
            name: vector[FEATURE_DIM + CONDITION_DIM + index]
            for index, name in enumerate(OBSERVATION_FEEDBACK_FIELDS)
        },
        "sample_id": record["sample_id"],
    }


@dataclass(frozen=True)
class EpisodeResult:
    """一次外部执行器评估的最小结构化结果。"""

    status: str = "completed"
    observed_risk_score: float | None = None
    observed_risk_level: str | None = None
    risk_method: str | None = "heuristic_v2"
    collision_count: int = 0
    event_count: int = 0
    run_valid: bool = True
    strict_acceptance_passed: bool = True
    carla_service_healthy: bool = True
    run_dir: str | None = None
    failure_reason: str | None = None
    evidence_kind: str = "carla_runtime"
    requires_carla_service: bool = True
    reward_channels_available: tuple[str, ...] = (
        "risk",
        "collision",
        "event",
    )

    @classmethod
    def from_mapping(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise AgentContractError("episode_result 必须是对象")
        status = str(value.get("status", "completed"))
        if status not in {"completed", "failed"}:
            raise AgentContractError("episode_result.status 必须为 completed 或 failed")
        score = value.get("observed_risk_score", value.get("score"))
        if score is not None:
            score = _finite_number(score, "observed_risk_score")
            if not 0.0 <= score <= 100.0:
                raise AgentContractError("observed_risk_score 必须位于 [0, 100]")
        try:
            collision_count = int(value.get("collision_count", 0))
            event_count = int(value.get("event_count", 0))
        except (TypeError, ValueError) as exc:
            raise AgentContractError("事件计数必须为整数") from exc
        if collision_count < 0 or event_count < 0:
            raise AgentContractError("事件计数不能为负数")
        observed_level = value.get("observed_risk_level", value.get("level"))
        if observed_level is not None and observed_level not in RISK_LEVELS:
            raise AgentContractError(f"未知 observed_risk_level: {observed_level}")
        risk_method = value.get("risk_method", value.get("method", "heuristic_v2"))
        if risk_method is not None:
            risk_method = str(risk_method).strip() or None
        evidence_kind = str(value.get("evidence_kind", "carla_runtime")).strip()
        if not evidence_kind:
            raise AgentContractError("episode_result.evidence_kind 不能为空")
        reward_channels = value.get(
            "reward_channels_available",
            ["risk", "collision", "event"],
        )
        if not isinstance(reward_channels, (list, tuple)):
            raise AgentContractError("reward_channels_available 必须是数组")
        reward_channels = tuple(str(item).strip() for item in reward_channels)
        allowed_channels = {"risk", "collision", "event"}
        if (
            not reward_channels
            or any(not item for item in reward_channels)
            or len(set(reward_channels)) != len(reward_channels)
            or not set(reward_channels).issubset(allowed_channels)
        ):
            raise AgentContractError(
                "reward_channels_available 只能包含 risk/collision/event 且不能重复"
            )
        return cls(
            status=status,
            observed_risk_score=score,
            observed_risk_level=observed_level,
            risk_method=risk_method,
            collision_count=collision_count,
            event_count=event_count,
            run_valid=_as_bool(value.get("run_valid"), status == "completed"),
            strict_acceptance_passed=_as_bool(
                value.get("strict_acceptance_passed"),
                status == "completed",
            ),
            carla_service_healthy=_as_bool(
                value.get("carla_service_healthy"),
                True,
            ),
            run_dir=value.get("run_dir"),
            failure_reason=value.get("failure_reason"),
            evidence_kind=evidence_kind,
            requires_carla_service=_as_bool(
                value.get("requires_carla_service"),
                True,
            ),
            reward_channels_available=reward_channels,
        )

    @property
    def successful(self):
        return (
            self.status == "completed"
            and self.run_valid
            and self.strict_acceptance_passed
            and (
                not self.requires_carla_service
                or self.carla_service_healthy
            )
            and self.observed_risk_score is not None
            and self.observed_risk_level is not None
            and self.risk_method is not None
            and bool(self.run_dir)
        )


@dataclass
class AgentTransition:
    observation: dict
    action: list
    reward: float
    reward_breakdown: dict
    candidate: dict | None
    terminated: bool
    truncated: bool
    reason: str | None
    info: dict

    def to_dict(self):
        return asdict(self)


class AdversarialTestAgentV1:
    """场景间对抗性代理，不在单次 CARLA 仿真内部接管车辆控制。"""

    def __init__(self, config=None):
        self.config = config or load_agent_config()
        self._reset_state()

    def _reset_state(self):
        self.current_record = None
        self.step_index = 0
        self.last_result = None
        self.last_feedback = {}
        self.last_fingerprint = None
        self.consecutive_duplicate_count = 0
        self.pending = None
        self.terminated = False
        self.truncated = False

    def reset(self, record, baseline_result=None):
        require_valid_scenario(record)
        self._reset_state()
        self.current_record = copy.deepcopy(record)
        self.last_fingerprint = canonical_parameter_fingerprint(record)
        if baseline_result is not None:
            result = EpisodeResult.from_mapping(baseline_result)
            if not result.successful:
                raise AgentContractError("baseline_result 必须通过严格运行验收")
            self.current_record["observed_risk"] = {
                "status": "completed",
                "method": result.risk_method,
                "score": result.observed_risk_score,
                "level": result.observed_risk_level,
                "run_dir": result.run_dir,
            }
            require_valid_scenario(self.current_record)
            self.last_result = result
            self.last_feedback = {
                "observed_risk_score": result.observed_risk_score,
                "collision_count": result.collision_count,
                "event_count": result.event_count,
                "run_valid": result.run_valid,
                "strict_acceptance_passed": result.strict_acceptance_passed,
                "repeat_count": 0,
                "step_index": 0,
            }
        else:
            self.last_feedback = {"step_index": 0}
        return build_observation(self.current_record, self.last_feedback, self.config)

    def propose(self, action):
        if self.current_record is None:
            raise AgentContractError("必须先调用 reset")
        if self.terminated or self.truncated:
            raise AgentContractError("episode 已结束，不能继续 propose")
        if self.pending is not None:
            raise AgentContractError("上一个候选尚未提交 episode_result")
        proposal = propose_candidate(
            self.current_record,
            action,
            step_index=self.step_index,
            config=self.config,
        )
        if proposal["valid"]:
            if proposal["fingerprint"] == self.last_fingerprint:
                self.consecutive_duplicate_count += 1
            else:
                self.consecutive_duplicate_count = 0
            self.last_fingerprint = proposal["fingerprint"]
        proposal["duplicate_count"] = self.consecutive_duplicate_count
        self.pending = proposal
        return proposal

    def _reward_for_result(self, result, proposal):
        reward_config = self.config["reward"]
        breakdown = {
            "risk_delta": 0.0,
            "collision_event": 0.0,
            "event": 0.0,
            "invalid_candidate": 0.0,
            "duplicate": 0.0,
            "run_failure": 0.0,
        }
        if not proposal["valid"]:
            breakdown["invalid_candidate"] = float(
                reward_config["invalid_candidate_penalty"]
            )
            return breakdown
        if proposal.get("duplicate_count", 0) > 0:
            breakdown["duplicate"] = float(reward_config["duplicate_penalty"])
        if not result.successful:
            breakdown["run_failure"] = float(reward_config["run_failure_penalty"])
            return breakdown
        if result.observed_risk_score is not None:
            previous_score = (
                self.last_result.observed_risk_score
                if self.last_result is not None
                else None
            )
            if previous_score is not None:
                breakdown["risk_delta"] = (
                    (result.observed_risk_score - previous_score) / 100.0
                    * float(reward_config["risk_delta_weight"])
                )
        collision_cap = max(1, int(reward_config.get("collision_event_cap", 1)))
        event_cap = max(1, int(reward_config.get("event_cap", 4)))
        previous_collision_count = (
            self.last_result.collision_count if self.last_result is not None else 0
        )
        previous_event_count = (
            self.last_result.event_count if self.last_result is not None else 0
        )
        collision_delta = (
            min(result.collision_count, collision_cap)
            - min(previous_collision_count, collision_cap)
        )
        event_delta = (
            min(result.event_count, event_cap)
            - min(previous_event_count, event_cap)
        )
        breakdown["collision_event"] = collision_delta * float(
            reward_config["collision_event_reward"]
        )
        breakdown["event"] = event_delta * float(reward_config["event_reward"])
        return breakdown

    def record_result(self, episode_result):
        if self.pending is None:
            raise AgentContractError("没有待提交的候选")
        proposal = self.pending
        self.pending = None
        if proposal["valid"]:
            result = EpisodeResult.from_mapping(episode_result)
        else:
            result = None
        breakdown = self._reward_for_result(result, proposal) if result else self._reward_for_result(None, proposal)
        reward = round(sum(breakdown.values()), 6)
        terminated = False
        truncated = False
        reason = None
        candidate = proposal.get("candidate")
        termination_config = self.config["termination"]
        if not proposal["valid"]:
            terminated = bool(
                termination_config.get("terminate_on_invalid_candidate", True)
            )
            reason = "invalid_candidate"
        elif not result.successful:
            terminated = bool(
                termination_config.get("terminate_on_run_failure", True)
            )
            reason = result.failure_reason or "run_failure"
        else:
            candidate = copy.deepcopy(candidate)
            candidate["observed_risk"] = {
                "status": "completed",
                "method": result.risk_method,
                "score": result.observed_risk_score,
                "level": result.observed_risk_level,
                "run_dir": result.run_dir,
            }
            self.current_record = candidate
            self.last_result = result
            self.last_feedback = {
                "observed_risk_score": result.observed_risk_score,
                "collision_count": result.collision_count,
                "event_count": result.event_count,
                "run_valid": result.run_valid,
                "strict_acceptance_passed": result.strict_acceptance_passed,
                "repeat_count": self.consecutive_duplicate_count,
                "step_index": self.step_index + 1,
            }
            if (
                termination_config.get("truncate_on_repeated_scene", True)
                and
                self.consecutive_duplicate_count
                >= int(termination_config["max_consecutive_duplicates"])
            ):
                truncated = True
                reason = "repeated_scene"
        self.step_index += 1
        if (
            not terminated
            and not truncated
            and termination_config.get("truncate_on_max_steps", True)
            and self.step_index >= int(termination_config["max_steps"])
        ):
            truncated = True
            reason = "max_steps"
        self.terminated = terminated
        self.truncated = truncated
        observation = build_observation(
            self.current_record,
            self.last_feedback,
            self.config,
        )
        info = {
            "step_index": self.step_index,
            "fingerprint": proposal.get("fingerprint"),
            "duplicate_count": proposal.get("duplicate_count", 0),
            "action_clipped": proposal.get("clipped", False),
            "failure_reason": result.failure_reason if result else proposal.get("error"),
            "evidence_kind": result.evidence_kind if result else None,
            "requires_carla_service": (
                result.requires_carla_service if result else None
            ),
            "reward_channels_available": (
                list(result.reward_channels_available) if result else []
            ),
            "run_valid": result.run_valid if result else None,
            "strict_acceptance_passed": (
                result.strict_acceptance_passed if result else None
            ),
            "carla_service_healthy": (
                result.carla_service_healthy if result else None
            ),
            "risk_method": result.risk_method if result else None,
            "run_dir": result.run_dir if result else None,
            "constraint_projection": proposal.get("constraint_projection"),
        }
        return AgentTransition(
            observation=observation,
            action=proposal.get("action", []),
            reward=reward,
            reward_breakdown={name: round(value, 6) for name, value in breakdown.items()},
            candidate=candidate,
            terminated=terminated,
            truncated=truncated,
            reason=reason,
            info=info,
        )

    def step(self, action, episode_result):
        self.propose(action)
        return self.record_result(episode_result)
