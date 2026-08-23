import importlib.util
import tempfile
import unittest
from pathlib import Path


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(TORCH_AVAILABLE, "本机缺少可选 PyTorch")
class ConditionalTabularDiffusionTests(unittest.TestCase):
    def test_forward_and_sampling_contract(self):
        import torch

        from core.scenario_features import CONDITION_DIM, FEATURE_DIM
        from models.conditional_tabular_diffusion import ConditionalTabularDiffusion

        model = ConditionalTabularDiffusion(
            feature_dim=FEATURE_DIM,
            condition_dim=CONDITION_DIM,
            timesteps=8,
            hidden_dim=24,
            time_dim=8,
        )
        features = torch.rand(3, FEATURE_DIM)
        conditions = torch.zeros(3, CONDITION_DIM)
        timesteps = torch.tensor([0, 1, 7], dtype=torch.long)
        loss = model.diffusion_loss(features, conditions)
        prediction = model.predict_noise(features, conditions, timesteps)
        samples = model.sample(conditions, generator=torch.Generator().manual_seed(7))

        self.assertEqual(tuple(prediction.shape), (3, FEATURE_DIM))
        self.assertTrue(torch.isfinite(loss))
        self.assertEqual(tuple(samples.shape), (3, FEATURE_DIM))
        self.assertGreaterEqual(float(samples.min()), 0.0)
        self.assertLessEqual(float(samples.max()), 1.0)

    def test_checkpoint_loader_preserves_format_contract(self):
        import torch

        from core.scenario_features import FEATURE_NAMES
        from models.conditional_tabular_diffusion import ConditionalTabularDiffusion
        from tools.generate_with_model import load_diffusion

        model = ConditionalTabularDiffusion(timesteps=8, hidden_dim=24, time_dim=8)
        with tempfile.TemporaryDirectory() as output_dir:
            checkpoint = Path(output_dir) / "best.pt"
            torch.save(
                {
                    "format": "conditional_tabular_diffusion_v1",
                    "model_config": model.config(),
                    "model_state": model.state_dict(),
                    "feature_names": list(FEATURE_NAMES),
                },
                checkpoint,
            )
            _, loaded = load_diffusion(checkpoint)
            self.assertEqual(loaded.config(), model.config())


if __name__ == "__main__":
    unittest.main()
