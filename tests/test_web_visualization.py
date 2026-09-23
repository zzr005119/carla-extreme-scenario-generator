import tempfile
import time
import unittest
from pathlib import Path

from core.web_task_orchestrator import TaskManager
from core.web_visualization import build_svg


RUN_DIR = Path(r"F:\Carla\output-0.9.16\adapter_smoke\seed_v1_high_0165\20260818_222032")


class WebVisualizationTests(unittest.TestCase):
    def test_build_svg_contains_auditable_series(self):
        rows = [
            {"elapsed_seconds": "0.0", "ego_speed_kmh": "5", "lead_speed_kmh": "4", "ttc_seconds": "8", "lead_gap_distance_m": "10", "pedestrian_distance_m": "20"},
            {"elapsed_seconds": "1.0", "ego_speed_kmh": "8", "lead_speed_kmh": "4", "ttc_seconds": "2", "lead_gap_distance_m": "5", "pedestrian_distance_m": "12"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = build_svg(Path(directory) / "chart.svg", rows, {"level": "high", "score": 61, "method": "heuristic_v2"})
            text = output.read_text(encoding="utf-8")
            self.assertIn("<svg", text)
            self.assertIn("TTC s", text)
            self.assertIn("heuristic_v2", text)

    def test_risk_task_registers_chart_and_sensor_preview(self):
        if not (RUN_DIR / "metadata.json").is_file() or not (RUN_DIR / "telemetry.csv").is_file():
            self.skipTest("本机没有历史 CARLA 运行证据")
        with tempfile.TemporaryDirectory() as directory:
            manager = TaskManager(directory)
            try:
                task = manager.submit("risk_analysis", {"run_dir": str(RUN_DIR)})
                deadline = time.time() + 10
                completed = manager.get(task["task_id"])
                while time.time() < deadline and completed["status"] not in {"completed", "failed"}:
                    time.sleep(0.05)
                    completed = manager.get(task["task_id"])
                self.assertEqual(completed["status"], "completed")
                artifact_types = {item["type"] for item in completed["artifacts"]}
                self.assertIn("svg_visualization", artifact_types)
                self.assertIn("sensor_preview", artifact_types)
                self.assertEqual(completed["result"]["visualization"]["row_count"], 400)
            finally:
                manager.close()


if __name__ == "__main__":
    unittest.main()
