"""Read-only executor backed by the frozen physical risk proxy."""

import hashlib
import math
import os

import numpy as np

from core.physical_features import (
    PHYSICAL_FEATURE_VERSION,
    physical_feature_matrix,
    physical_feature_names,
)
from core.scenario_features import (
    FEATURE_DIM,
    FEATURE_NAMES,
    normalize_vector,
    parameter_vector,
)
from core.scenario_validator import (
    load_json,
    require_valid_scenario,
    validate_schema_value,
)


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_proxy_executor_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_proxy_executor_v1.schema.json",
)


class ProxyExecutorError(RuntimeError):
    """Raised when the frozen proxy cannot be trusted or evaluated."""


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_proxy_executor_config(
    path=DEFAULT_CONFIG_PATH,
    schema_path=DEFAULT_SCHEMA_PATH,
):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ProxyExecutorError("\n".join(errors))

    feature = config["feature_contract"]
    expected_names = list(FEATURE_NAMES) + list(physical_feature_names())
    if feature["physical_feature_version"] != PHYSICAL_FEATURE_VERSION:
        raise ProxyExecutorError("物理派生特征版本与当前代码不一致")
    if int(feature["baseline_feature_count"]) != FEATURE_DIM:
        raise ProxyExecutorError("代理原始特征数量与当前 15 维契约不一致")
    if int(feature["derived_feature_count"]) != len(physical_feature_names()):
        raise ProxyExecutorError("代理物理派生特征数量与当前代码不一致")
    if int(feature["feature_count"]) != len(expected_names):
        raise ProxyExecutorError("代理总特征数量与当前代码不一致")
    if feature["feature_names"] != expected_names:
        raise ProxyExecutorError("代理特征顺序与当前代码不一致")
    if config["reward_channels_available"] != ["risk"]:
        raise ProxyExecutorError("V1 冻结代理只允许 risk 奖励通道")
    return config


def resolve_model_path(config, override=None):
    if override:
        return os.path.abspath(override)
    model = config["model"]
    root_name = model["root_env"]
    root = os.environ.get(root_name)
    if not root:
        raise ProxyExecutorError(f"缺少模型根目录环境变量: {root_name}")
    return os.path.abspath(os.path.join(root, model["relative_path"]))


class FrozenRiskProxyExecutor:
    """Evaluate records with a hash-verified frozen risk regression model."""

    def __init__(self, config=None, model_path=None):
        self.config = config or load_proxy_executor_config()
        self.model_path = resolve_model_path(self.config, model_path)
        if not os.path.isfile(self.model_path):
            raise ProxyExecutorError(f"冻结代理模型不存在: {self.model_path}")

        actual_sha256 = file_sha256(self.model_path)
        expected_sha256 = self.config["model"]["sha256"]
        if actual_sha256 != expected_sha256:
            raise ProxyExecutorError(
                "冻结代理模型 SHA-256 不一致: "
                f"expected={expected_sha256}, actual={actual_sha256}"
            )

        try:
            import joblib
        except ImportError as exc:
            raise ProxyExecutorError(
                "加载冻结代理需要 requirements-models.txt 中的 joblib"
            ) from exc
        self.model = joblib.load(self.model_path)
        model_class = f"{type(self.model).__module__}.{type(self.model).__name__}"
        if model_class != self.config["model"]["class"]:
            raise ProxyExecutorError(
                "冻结代理模型类型不一致: "
                f"expected={self.config['model']['class']}, actual={model_class}"
            )
        feature_count = int(self.config["feature_contract"]["feature_count"])
        if int(getattr(self.model, "n_features_in_", -1)) != feature_count:
            raise ProxyExecutorError("冻结代理模型输入维度不是 27")

        self.model_sha256 = actual_sha256
        self.calls = []

    @staticmethod
    def feature_vector(record):
        require_valid_scenario(record)
        normalized = normalize_vector(parameter_vector(record), clip=True)
        derived = physical_feature_matrix(normalized)[0]
        vector = np.concatenate((normalized, derived)).astype(np.float64)
        expected = FEATURE_DIM + len(physical_feature_names())
        if vector.shape != (expected,) or not np.all(np.isfinite(vector)):
            raise ProxyExecutorError("代理输入特征必须是 27 维有限数值")
        return vector

    def predict_score(self, record):
        vector = self.feature_vector(record)
        prediction = np.asarray(self.model.predict(vector.reshape(1, -1))).reshape(-1)
        if prediction.shape != (1,) or not math.isfinite(float(prediction[0])):
            raise ProxyExecutorError("冻结代理返回了无效风险分")
        prediction_config = self.config["prediction"]
        raw_score = float(prediction[0])
        score = min(
            float(prediction_config["maximum_score"]),
            max(float(prediction_config["minimum_score"]), raw_score),
        )
        return round(score, 6), raw_score

    def _risk_level(self, score):
        levels = self.config["prediction"]["levels"]
        if score >= float(levels["critical"]):
            return "critical"
        if score >= float(levels["high"]):
            return "high"
        if score >= float(levels["medium"]):
            return "medium"
        return "low"

    def __call__(self, record, phase, step_index):
        score, raw_score = self.predict_score(record)
        call = {
            "sample_id": record["sample_id"],
            "phase": phase,
            "step_index": int(step_index),
            "score": score,
            "raw_score": raw_score,
        }
        self.calls.append(call)
        return {
            "status": "completed",
            "observed_risk_score": score,
            "observed_risk_level": self._risk_level(score),
            "risk_method": self.config["executor_id"],
            "collision_count": 0,
            "event_count": 0,
            "run_valid": True,
            "strict_acceptance_passed": True,
            "carla_service_healthy": False,
            "requires_carla_service": False,
            "evidence_kind": "frozen_risk_proxy_inference",
            "reward_channels_available": ["risk"],
            "run_dir": (
                f"proxy://{self.config['executor_id']}/{phase}/{int(step_index)}"
            ),
        }

    def metadata(self):
        return {
            "executor_id": self.config["executor_id"],
            "model_path": self.model_path,
            "model_sha256": self.model_sha256,
            "model_class": self.config["model"]["class"],
            "feature_contract": self.config["feature_contract"],
            "training_evidence": self.config["training_evidence"],
            "reward_channels_available": self.config[
                "reward_channels_available"
            ],
            "carla_connected": False,
        }
