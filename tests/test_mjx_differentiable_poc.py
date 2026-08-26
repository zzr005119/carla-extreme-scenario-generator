import json
import os
from pathlib import Path
import subprocess
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MJX_PYTHON = PROJECT_ROOT / "tmp" / "mjx_jax_env" / "Scripts" / "python.exe"


RUN_MJX_POC_TESTS = os.environ.get("RUN_MJX_POC_TESTS") == "1"


@unittest.skipUnless(
    RUN_MJX_POC_TESTS and MJX_PYTHON.exists(),
    "可选 MJX-JAX PoC 测试默认关闭；设置 RUN_MJX_POC_TESTS=1 后运行",
)
class MJXDifferentiablePoCTests(unittest.TestCase):
    def _run(self, horizon=16, compare_workarounds=False):
        output = PROJECT_ROOT / "tmp" / f"mjx_test_manifest_{horizon}.json"
        args = [
            str(MJX_PYTHON),
            "tools/run_mjx_differentiable_poc.py",
            "--horizon",
            str(horizon),
            "--output",
            str(output),
        ]
        if compare_workarounds:
            args.append("--compare-workarounds")
        result = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_forward_gradient_and_native_alignment(self):
        manifest = self._run()
        self.assertEqual(manifest["quality_gate"], "pass_forward_mode_only")
        self.assertTrue(manifest["gradient_check"]["finite"])
        self.assertLess(manifest["gradient_check"]["relative_error"], 1e-2)
        self.assertTrue(manifest["native_mujoco_comparison"]["within_tolerance"])

    def test_fixed_solver_iteration_enables_reverse_mode_probe(self):
        manifest = self._run(horizon=8, compare_workarounds=True)
        rows = manifest["workaround_probe"]
        self.assertTrue(rows[0]["reverse_mode_available"])
        self.assertFalse(rows[1]["reverse_mode_available"])

    def test_custom_vjp_matches_forward_jacfwd(self):
        output = PROJECT_ROOT / "tmp" / "mjx_test_manifest_custom_vjp.json"
        result = subprocess.run(
            [
                str(MJX_PYTHON),
                "tools/run_mjx_differentiable_poc.py",
                "--horizon",
                "8",
                "--output",
                str(output),
                "--probe-custom-vjp",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        probe = json.loads(output.read_text(encoding="utf-8"))["custom_vjp_probe"]
        self.assertTrue(probe["finite"])
        self.assertLess(probe["max_abs_difference_to_jacfwd"], 1e-10)

    def test_cli_writes_manifest(self):
        manifest = self._run(horizon=8)
        self.assertEqual(manifest["format"], "p4_1_mjx_differentiable_poc_manifest_v1")
        self.assertEqual(manifest["device"], "cpu:0")


if __name__ == "__main__":
    unittest.main()
