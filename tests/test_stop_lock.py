import unittest
import json
import tempfile
from pathlib import Path

from core.stop_lock import advance_stop_lock
from tools.prepare_scenario_runner_acceptance import prepare_config


class StopLockTests(unittest.TestCase):
    def test_requires_consecutive_low_speed_samples(self):
        state = advance_stop_lock(
            braking=True,
            speed_kmh=0.8,
            locked=False,
            below_threshold_steps=0,
            confirmation_steps=3,
        )
        self.assertFalse(state["locked"])
        self.assertEqual(state["below_threshold_steps"], 1)

        state = advance_stop_lock(
            braking=True,
            speed_kmh=0.2,
            locked=False,
            below_threshold_steps=state["below_threshold_steps"],
            confirmation_steps=3,
        )
        self.assertFalse(state["locked"])
        self.assertEqual(state["below_threshold_steps"], 2)

        state = advance_stop_lock(
            braking=True,
            speed_kmh=0.0,
            locked=False,
            below_threshold_steps=state["below_threshold_steps"],
            confirmation_steps=3,
        )
        self.assertTrue(state["locked"])
        self.assertTrue(state["just_locked"])
        self.assertEqual(state["below_threshold_steps"], 3)

    def test_threshold_sample_resets_confirmation(self):
        state = advance_stop_lock(
            braking=True,
            speed_kmh=0.5,
            locked=False,
            below_threshold_steps=1,
            confirmation_steps=3,
        )
        self.assertFalse(state["locked"])
        self.assertEqual(state["below_threshold_steps"], 2)

        state = advance_stop_lock(
            braking=True,
            speed_kmh=1.01,
            locked=False,
            below_threshold_steps=state["below_threshold_steps"],
            confirmation_steps=3,
        )
        self.assertFalse(state["locked"])
        self.assertEqual(state["below_threshold_steps"], 0)

    def test_lock_is_sticky_until_braking_ends(self):
        state = advance_stop_lock(
            braking=True,
            speed_kmh=0.0,
            locked=True,
            below_threshold_steps=3,
            confirmation_steps=3,
        )
        self.assertTrue(state["locked"])
        self.assertFalse(state["just_locked"])
        self.assertEqual(state["below_threshold_steps"], 3)

        state = advance_stop_lock(
            braking=False,
            speed_kmh=20.0,
            locked=True,
            below_threshold_steps=3,
            confirmation_steps=3,
        )
        self.assertFalse(state["locked"])
        self.assertEqual(state["below_threshold_steps"], 0)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            advance_stop_lock(
                braking=True,
                speed_kmh=0.0,
                locked=False,
                below_threshold_steps=0,
                speed_threshold_kmh=0.0,
            )
        with self.assertRaises(ValueError):
            advance_stop_lock(
                braking=True,
                speed_kmh=0.0,
                locked=False,
                below_threshold_steps=0,
                confirmation_steps=0,
            )

    def test_acceptance_config_carries_stop_lock_profile(self):
        project_root = Path(__file__).resolve().parents[1]
        base_config = project_root / "configs" / "multi_hazard_rainy_night.json"
        profile = project_root / "configs" / "route_control_profiles" / "waypoint_follower_v1.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            xosc = root / "sample.xosc"
            xosc.write_text(
                '<OpenSCENARIO><RoadNetwork><LogicFile filepath="Town10HD_Opt"/></RoadNetwork></OpenSCENARIO>',
                encoding="utf-8",
            )
            manifest_path, config_path = prepare_config(
                xosc,
                base_config,
                root / "out",
                profile,
                8100,
            )
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(config["traffic"]["lead_stop_lock_enabled"])
            self.assertEqual(config["traffic"]["lead_stop_lock_confirm_steps"], 3)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["status"], "prepared")


if __name__ == "__main__":
    unittest.main()
