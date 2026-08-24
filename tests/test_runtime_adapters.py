import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import torch

from core.differentiable_closed_loop import (
    DifferentiableLoopConfig,
    PyBulletValidationAdapter,
    differentiable_rollout,
)
from tools.run_scenario_runner import preflight, run
from tools.train_carla_rl import build_training_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORD = PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "example_record.json"
LOOP_CONFIG = PROJECT_ROOT / "configs" / "adversarial_loop_multistep_v1.json"


class RuntimeAdapterTests(unittest.TestCase):
    def test_differentiable_rollout_has_gradient(self):
        config = DifferentiableLoopConfig(horizon=4)
        actions = torch.zeros((1, config.horizon), requires_grad=True)
        result = differentiable_rollout(actions, config)
        result["loss"].backward()
        self.assertEqual(tuple(result["gap_m"].shape), (1, 4))
        self.assertIsNotNone(actions.grad)
        self.assertTrue(torch.isfinite(actions.grad).all())
        self.assertFalse(result["pybullet_differentiable"])

    def test_pybullet_check_reports_optional_boundary(self):
        result = PyBulletValidationAdapter().validate(
            differentiable_rollout(torch.zeros(4), DifferentiableLoopConfig(horizon=4))
        )
        self.assertIn(result["validated"], (True, False))
        self.assertIn("evidence_kind", result)

    def test_scenario_runner_dry_run_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            xosc = temp_dir / "sample.xosc"
            xosc.write_text("<OpenSCENARIO><FileHeader/><Storyboard/></OpenSCENARIO>", encoding="utf-8")
            runner = temp_dir / "scenario_runner.py"
            runner.write_text("print('stub')\n", encoding="utf-8")
            plan = preflight(temp_dir, xosc, port=2001)
            result = run(plan, output_path=temp_dir / "manifest.json", execute=False)
            self.assertEqual(result["status"], "dry_run")
            self.assertFalse(result["execution_started"])
            self.assertIn("--trafficManagerPort", result["command"])
            self.assertNotIn("--waitForEgo", result["command"])
            self.assertTrue((temp_dir / "manifest.json").is_file())
            self.assertEqual(json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))["status"], "dry_run")

    def test_scenario_runner_record_flag_has_directory_argument(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            xosc = temp_dir / "sample.xosc"
            xosc.write_text("<OpenSCENARIO><FileHeader/><Storyboard/></OpenSCENARIO>", encoding="utf-8")
            runner = temp_dir / "scenario_runner.py"
            runner.write_text("print('stub')\n", encoding="utf-8")
            plan = preflight(temp_dir, xosc, record=True)
            index = plan["command"].index("--record")
            self.assertEqual(plan["command"][index + 1], "records")

    def test_online_rl_plan_exposes_missing_optional_dependencies(self):
        with tempfile.TemporaryDirectory() as output_dir:
            plan = build_training_plan(LOOP_CONFIG, RECORD, output_dir, steps=2)
        self.assertEqual(plan["algorithm"], "PPO")
        self.assertEqual(plan["carla_episode_budget"], 3)
        self.assertFalse(plan["carla_server_started_by_script"])
        self.assertIn(plan["status"], ("ready", "blocked_optional_dependency"))


if __name__ == "__main__":
    unittest.main()
