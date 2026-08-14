"""轻量条件表格 VAE。"""

import torch
from torch import nn
from torch.nn import functional as functional


class ConditionalTabularVAE(nn.Module):
    def __init__(
        self,
        feature_dim=15,
        condition_dim=12,
        latent_dim=6,
        encoder_hidden=(64, 32),
        decoder_hidden=(32, 64),
    ):
        super().__init__()
        self.feature_dim = int(feature_dim)
        self.condition_dim = int(condition_dim)
        self.latent_dim = int(latent_dim)
        self.encoder_hidden = tuple(int(value) for value in encoder_hidden)
        self.decoder_hidden = tuple(int(value) for value in decoder_hidden)

        encoder_layers = []
        input_dim = self.feature_dim + self.condition_dim
        for hidden_dim in self.encoder_hidden:
            encoder_layers.extend((nn.Linear(input_dim, hidden_dim), nn.SiLU()))
            input_dim = hidden_dim
        self.encoder = nn.Sequential(*encoder_layers)
        self.mu_head = nn.Linear(input_dim, self.latent_dim)
        self.log_variance_head = nn.Linear(input_dim, self.latent_dim)

        decoder_layers = []
        input_dim = self.latent_dim + self.condition_dim
        for hidden_dim in self.decoder_hidden:
            decoder_layers.extend((nn.Linear(input_dim, hidden_dim), nn.SiLU()))
            input_dim = hidden_dim
        decoder_layers.extend((nn.Linear(input_dim, self.feature_dim), nn.Sigmoid()))
        self.decoder = nn.Sequential(*decoder_layers)

    def encode(self, features, conditions):
        hidden = self.encoder(torch.cat((features, conditions), dim=-1))
        return self.mu_head(hidden), self.log_variance_head(hidden)

    def reparameterize(self, mu, log_variance):
        standard_deviation = torch.exp(0.5 * log_variance)
        noise = torch.randn_like(standard_deviation)
        return mu + noise * standard_deviation

    def decode(self, latent, conditions):
        return self.decoder(torch.cat((latent, conditions), dim=-1))

    def forward(self, features, conditions):
        mu, log_variance = self.encode(features, conditions)
        latent = self.reparameterize(mu, log_variance)
        reconstruction = self.decode(latent, conditions)
        return reconstruction, mu, log_variance

    def sample(self, conditions, generator=None):
        latent = torch.randn(
            (conditions.shape[0], self.latent_dim),
            device=conditions.device,
            dtype=conditions.dtype,
            generator=generator,
        )
        return self.decode(latent, conditions)

    def config(self):
        return {
            "feature_dim": self.feature_dim,
            "condition_dim": self.condition_dim,
            "latent_dim": self.latent_dim,
            "encoder_hidden": list(self.encoder_hidden),
            "decoder_hidden": list(self.decoder_hidden),
        }


def cvae_loss(reconstruction, features, mu, log_variance, beta):
    reconstruction_loss = functional.smooth_l1_loss(
        reconstruction,
        features,
        reduction="mean",
    )
    kl_loss = -0.5 * torch.mean(
        torch.sum(1.0 + log_variance - mu.pow(2) - log_variance.exp(), dim=1)
    )
    total_loss = reconstruction_loss + float(beta) * kl_loss
    return total_loss, reconstruction_loss, kl_loss
