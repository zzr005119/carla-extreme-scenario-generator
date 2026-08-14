"""按风险等级建模的轻量对角协方差高斯混合基线。"""

import json

import numpy as np

from core.scenario_features import FEATURE_NAMES, RISK_LEVELS, encode_record


def _logsumexp(values, axis):
    maximum = np.max(values, axis=axis, keepdims=True)
    result = maximum + np.log(np.sum(np.exp(values - maximum), axis=axis, keepdims=True))
    return np.squeeze(result, axis=axis)


class ConditionalDiagonalGMM:
    def __init__(
        self,
        n_components=2,
        random_seed=20260813,
        max_iterations=300,
        tolerance=1e-6,
        variance_floor=1e-4,
        n_init=5,
    ):
        self.n_components = int(n_components)
        self.random_seed = int(random_seed)
        self.max_iterations = int(max_iterations)
        self.tolerance = float(tolerance)
        self.variance_floor = float(variance_floor)
        self.n_init = int(n_init)
        self.models = {}

    def _component_log_probabilities(self, values, weights, means, variances):
        differences = values[:, None, :] - means[None, :, :]
        log_gaussian = -0.5 * np.sum(
            np.log(2.0 * np.pi * variances)[None, :, :]
            + differences * differences / variances[None, :, :],
            axis=2,
        )
        return np.log(np.maximum(weights, 1e-12))[None, :] + log_gaussian

    def _fit_one(self, values, rng):
        if len(values) < self.n_components:
            raise ValueError(
                f"样本数 {len(values)} 小于 GMM 分量数 {self.n_components}"
            )
        best = None
        for _ in range(self.n_init):
            indices = rng.choice(len(values), self.n_components, replace=False)
            means = values[indices].copy()
            global_variance = np.var(values, axis=0) + self.variance_floor
            variances = np.repeat(global_variance[None, :], self.n_components, axis=0)
            weights = np.full(self.n_components, 1.0 / self.n_components)
            previous_log_likelihood = None
            for iteration in range(1, self.max_iterations + 1):
                component_logs = self._component_log_probabilities(
                    values,
                    weights,
                    means,
                    variances,
                )
                normalizers = _logsumexp(component_logs, axis=1)
                responsibilities = np.exp(component_logs - normalizers[:, None])
                counts = np.maximum(responsibilities.sum(axis=0), 1e-8)
                weights = counts / len(values)
                means = responsibilities.T @ values / counts[:, None]
                differences = values[:, None, :] - means[None, :, :]
                variances = (
                    np.sum(
                        responsibilities[:, :, None] * differences * differences,
                        axis=0,
                    )
                    / counts[:, None]
                )
                variances = np.maximum(variances, self.variance_floor)
                log_likelihood = float(np.mean(normalizers))
                if (
                    previous_log_likelihood is not None
                    and abs(log_likelihood - previous_log_likelihood) <= self.tolerance
                ):
                    break
                previous_log_likelihood = log_likelihood
            candidate = {
                "weights": weights,
                "means": means,
                "variances": variances,
                "mean_log_likelihood": log_likelihood,
                "iterations": iteration,
            }
            if best is None or log_likelihood > best["mean_log_likelihood"]:
                best = candidate
        return best

    def fit(self, records):
        rng = np.random.default_rng(self.random_seed)
        self.models = {}
        for level in RISK_LEVELS:
            values = np.asarray(
                [
                    encode_record(record)
                    for record in records
                    if record["conditions"]["target_risk_level"] == level
                ],
                dtype=np.float64,
            )
            if not len(values):
                raise ValueError(f"训练数据缺少风险等级: {level}")
            self.models[level] = self._fit_one(values, rng)
        return self

    def score_samples(self, values, target_risk_level):
        if target_risk_level not in self.models:
            raise ValueError(f"模型未包含风险等级: {target_risk_level}")
        model = self.models[target_risk_level]
        values = np.asarray(values, dtype=np.float64)
        component_logs = self._component_log_probabilities(
            values,
            model["weights"],
            model["means"],
            model["variances"],
        )
        return _logsumexp(component_logs, axis=1)

    def mean_log_likelihood(self, records):
        scores = []
        for level in RISK_LEVELS:
            values = np.asarray(
                [
                    encode_record(record)
                    for record in records
                    if record["conditions"]["target_risk_level"] == level
                ],
                dtype=np.float64,
            )
            if len(values):
                scores.extend(self.score_samples(values, level).tolist())
        return float(np.mean(scores)) if scores else float("nan")

    def sample(self, target_risk_level, count, random_seed=None):
        if target_risk_level not in self.models:
            raise ValueError(f"模型未包含风险等级: {target_risk_level}")
        model = self.models[target_risk_level]
        rng = np.random.default_rng(
            self.random_seed if random_seed is None else random_seed
        )
        components = rng.choice(
            self.n_components,
            size=int(count),
            p=model["weights"],
        )
        samples = np.empty((int(count), len(FEATURE_NAMES)), dtype=np.float64)
        for index, component in enumerate(components):
            samples[index] = rng.normal(
                model["means"][component],
                np.sqrt(model["variances"][component]),
            )
        return np.clip(samples, 0.0, 1.0)

    def to_dict(self):
        if not self.models:
            raise ValueError("GMM 尚未训练")
        return {
            "format": "conditional_diagonal_gmm_v1",
            "n_components": self.n_components,
            "random_seed": self.random_seed,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
            "variance_floor": self.variance_floor,
            "n_init": self.n_init,
            "feature_names": list(FEATURE_NAMES),
            "models": {
                level: {
                    "weights": model["weights"].tolist(),
                    "means": model["means"].tolist(),
                    "variances": model["variances"].tolist(),
                    "mean_log_likelihood": model["mean_log_likelihood"],
                    "iterations": model["iterations"],
                }
                for level, model in self.models.items()
            },
        }

    @classmethod
    def from_dict(cls, payload):
        if payload.get("format") != "conditional_diagonal_gmm_v1":
            raise ValueError("不支持的 GMM 文件格式")
        if tuple(payload.get("feature_names", ())) != FEATURE_NAMES:
            raise ValueError("GMM 特征定义与当前代码不一致")
        model = cls(
            n_components=payload["n_components"],
            random_seed=payload["random_seed"],
            max_iterations=payload["max_iterations"],
            tolerance=payload["tolerance"],
            variance_floor=payload["variance_floor"],
            n_init=payload["n_init"],
        )
        model.models = {
            level: {
                "weights": np.asarray(values["weights"], dtype=np.float64),
                "means": np.asarray(values["means"], dtype=np.float64),
                "variances": np.asarray(values["variances"], dtype=np.float64),
                "mean_log_likelihood": float(values["mean_log_likelihood"]),
                "iterations": int(values["iterations"]),
            }
            for level, values in payload["models"].items()
        }
        return model

    def save(self, path, metadata=None):
        payload = self.to_dict()
        if metadata is not None:
            payload["metadata"] = metadata
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as file:
            return cls.from_dict(json.load(file))
