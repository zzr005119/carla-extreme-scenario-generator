import json
import tempfile
import unittest
from pathlib import Path

from core.carla_rl_plan import (
    SAMPLER_STATE_FORMAT,
    PlannedScenarioSampler,
    build_multiscene_plan,
    load_multiscene_plan,
)
from tools.train_carla_rl import build_training_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRIES = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
MANIFEST = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "manifest.json"
CONFIG = PROJECT_ROOT / "configs" / "adversarial_loop_multistep_v1.json"


class CarlaRLPlanTests(unittest.TestCase):
    def test_plan_is_deterministic_and_leak_free(self):
        with tempfile.TemporaryDirectory() as temp:
            first_path = Path(temp) / "first.json"
            second_path = Path(temp) / "second.json"
            first = build_multiscene_plan(ENTRIES, MANIFEST, first_path, seed=7)
            second = build_multiscene_plan(ENTRIES, MANIFEST, second_path, seed=7)
            self.assertEqual(first["plan_sha256"], second["plan_sha256"])
            self.assertEqual(first["counts"], {"train": 66, "dev": 27, "test": 24})
            ids = [
                row["canonical_sample_id"]
                for split in ("train", "dev", "test")
                for row in first["splits"][split]
            ]
            self.assertEqual(len(ids), len(set(ids)))
            loaded = load_multiscene_plan(first_path)
            self.assertEqual(loaded["plan_sha256"], first["plan_sha256"])

    def test_sampler_cycles_only_its_declared_split(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            plan = build_multiscene_plan(ENTRIES, MANIFEST, plan_path, seed=9)
            sampler = PlannedScenarioSampler(plan["splits"]["train"], seed=9)
            selected = [sampler(9 if index == 0 else None)[1] for index in range(20)]
            self.assertEqual({row["plan_split"] for row in selected}, {"train"})
            self.assertEqual(
                len({row["canonical_sample_id"] for row in selected[:66]}),
                min(20, 66),
            )

    def test_sampler_state_restores_exact_next_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            plan = build_multiscene_plan(ENTRIES, MANIFEST, plan_path, seed=13)
            rows = plan["splits"]["train"]
            original = PlannedScenarioSampler(rows, seed=13)
            for index in range(70):
                original(13 if index == 0 else None)
            state = json.loads(json.dumps(original.state_dict()))
            self.assertEqual(state["format"], SAMPLER_STATE_FORMAT)
            expected_record, expected_info = original()

            restored = PlannedScenarioSampler(rows, seed=13)
            restored.load_state_dict(state)
            actual_record, actual_info = restored()
            self.assertEqual(actual_record, expected_record)
            self.assertEqual(actual_info, expected_info)

    def test_training_plan_keeps_legacy_smoke_and_adds_multiscene_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            build_multiscene_plan(ENTRIES, MANIFEST, plan_path, seed=11)
            plan = build_training_plan(
                CONFIG,
                None,
                Path(temp) / "output",
                algorithm="SAC",
                steps=10000,
                scenario_plan_path=plan_path,
                checkpoint_every=1000,
            )
            self.assertEqual(plan["carla_episode_budget"], 10625)
            self.assertEqual(plan["split_counts"], {"train": 66, "dev": 27, "test": 24})
            self.assertEqual(plan["checkpoint_every"], 1000)
            self.assertEqual(plan["format"], "carla_online_rl_training_plan_v2")
            self.assertEqual(plan["sac_replay_buffer_capacity"], 10000)
            self.assertEqual(
                plan["checkpoint_continuity"],
                {
                    "model": "required",
                    "replay_buffer": "required",
                    "sampler_state": "required",
                },
            )


if __name__ == "__main__":
    unittest.main()
