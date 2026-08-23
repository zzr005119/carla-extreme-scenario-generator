"""轻量条件表格 Diffusion 生成器。

该实现面向 15 维连续场景参数的小规模离线对照，不试图替代当前
C-TabCVAE 主线，也不包含 CARLA 或真实风险标签。
"""

import math

import torch
from torch import nn
from torch.nn import functional as functional


class ConditionalTabularDiffusion(nn.Module):
    """A compact DDPM denoiser conditioned on risk and weather one-hot values."""

    def __init__(
        self,
        feature_dim=15,
        condition_dim=12,
        timesteps=32,
        hidden_dim=96,
        time_dim=32,
        beta_start=1e-4,
        beta_end=0.02,
    ):
        super().__init__()
        if timesteps < 2:
            raise ValueError("timesteps 必须至少为 2")
        self.feature_dim = int(feature_dim)
        self.condition_dim = int(condition_dim)
        self.timesteps = int(timesteps)
        self.hidden_dim = int(hidden_dim)
        self.time_dim = int(time_dim)
        self.beta_start = float(beta_start)
        self.beta_end = float(beta_end)

        betas = torch.linspace(self.beta_start, self.beta_end, self.timesteps)
        alphas = 1.0 - betas
        alpha_cumprod = torch.cumprod(alphas, dim=0)
        self.register_buffer("betas", betas)
        self.register_buffer("alphas", alphas)
        self.register_buffer("alpha_cumprod", alpha_cumprod)
        self.register_buffer("sqrt_alpha_cumprod", torch.sqrt(alpha_cumprod))
        self.register_buffer(
            "sqrt_one_minus_alpha_cumprod",
            torch.sqrt(1.0 - alpha_cumprod),
        )

        input_dim = self.feature_dim + self.condition_dim + self.time_dim
        self.denoiser = nn.Sequential(
            nn.Linear(input_dim, self.hidden_dim),
            nn.SiLU(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
            nn.SiLU(),
            nn.Linear(self.hidden_dim, self.feature_dim),
        )

    def config(self):
        return {
            "feature_dim": self.feature_dim,
            "condition_dim": self.condition_dim,
            "timesteps": self.timesteps,
            "hidden_dim": self.hidden_dim,
            "time_dim": self.time_dim,
            "beta_start": self.beta_start,
            "beta_end": self.beta_end,
        }

    def time_embedding(self, timesteps):
        timesteps = timesteps.to(dtype=torch.float32)
        half = self.time_dim // 2
        if half == 0:
            return timesteps[:, None]
        frequencies = torch.exp(
            -math.log(10000.0)
            * torch.arange(half, device=timesteps.device, dtype=torch.float32)
            / max(1, half - 1)
        )
        angles = timesteps[:, None] * frequencies[None, :]
        embedding = torch.cat((torch.sin(angles), torch.cos(angles)), dim=-1)
        if embedding.shape[-1] < self.time_dim:
            embedding = functional.pad(embedding, (0, self.time_dim - embedding.shape[-1]))
        return embedding

    def predict_noise(self, noisy_features, conditions, timesteps):
        if noisy_features.shape[-1] != self.feature_dim:
            raise ValueError("输入特征维度与模型不一致")
        if conditions.shape[-1] != self.condition_dim:
            raise ValueError("条件维度与模型不一致")
        time = self.time_embedding(timesteps)
        return self.denoiser(torch.cat((noisy_features, conditions, time), dim=-1))

    def q_sample(self, features, timesteps, noise=None):
        if noise is None:
            noise = torch.randn_like(features)
        sqrt_alpha = self.sqrt_alpha_cumprod[timesteps].unsqueeze(-1)
        sqrt_one_minus = self.sqrt_one_minus_alpha_cumprod[timesteps].unsqueeze(-1)
        return sqrt_alpha * features + sqrt_one_minus * noise, noise

    def diffusion_loss(self, features, conditions, generator=None):
        batch_size = features.shape[0]
        timesteps = torch.randint(
            0,
            self.timesteps,
            (batch_size,),
            device=features.device,
            generator=generator,
        )
        noise = torch.randn(
            features.shape,
            device=features.device,
            dtype=features.dtype,
            generator=generator,
        )
        noisy, noise = self.q_sample(features, timesteps, noise)
        prediction = self.predict_noise(noisy, conditions, timesteps)
        return functional.mse_loss(prediction, noise)

    def forward(self, noisy_features, conditions, timesteps):
        return self.predict_noise(noisy_features, conditions, timesteps)

    def sample(self, conditions, generator=None):
        """Sample normalized parameter vectors with the full reverse schedule."""
        if conditions.ndim != 2 or conditions.shape[-1] != self.condition_dim:
            raise ValueError("条件数组形状与模型不一致")
        features = torch.randn(
            (conditions.shape[0], self.feature_dim),
            device=conditions.device,
            dtype=conditions.dtype,
            generator=generator,
        )
        was_training = self.training
        self.eval()
        with torch.no_grad():
            for index in range(self.timesteps - 1, -1, -1):
                timestep = torch.full(
                    (conditions.shape[0],),
                    index,
                    device=conditions.device,
                    dtype=torch.long,
                )
                prediction = self.predict_noise(features, conditions, timestep)
                beta = self.betas[index]
                alpha = self.alphas[index]
                cumulative = self.alpha_cumprod[index]
                mean = (features - beta * prediction / torch.sqrt(1.0 - cumulative)) / torch.sqrt(alpha)
                if index:
                    noise = torch.randn(
                        features.shape,
                        device=features.device,
                        dtype=features.dtype,
                        generator=generator,
                    )
                    features = mean + torch.sqrt(beta) * noise
                else:
                    features = mean
        if was_training:
            self.train()
        return torch.clamp(features, 0.0, 1.0)


def diffusion_loss(model, features, conditions, generator=None):
    """Functional wrapper kept parallel to the CVAE training API."""
    return model.diffusion_loss(features, conditions, generator=generator)
