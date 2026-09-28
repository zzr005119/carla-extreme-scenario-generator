import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from core.web_task_orchestrator import TaskManager
from core.web_visualization import build_replay_manifest, build_svg, resolve_replay_frame


RUN_DIR = Path(r"F:\Carla\output-0.9.16\adapter_smoke\seed_v1_high_0165\20260818_222032")


class WebVisualizationTests(unittest.TestCase):
    def test_replay_manifest_aligns_saved_frames_with_telemetry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            run_dir = Path(directory)
            (run_dir / "rgb").mkdir()
            (run_dir / "semantic").mkdir()
            for frame in (100, 102, 104):
                (run_dir / "rgb" / f"frame_{frame:06d}.png").write_bytes(b"png")
            (run_dir / "semantic" / "frame_000100.png").write_bytes(b"png")
            (run_dir / "telemetry.csv").write_text(
                "elapsed_seconds,ego_speed_kmh,lead_gap_distance_m,ttc_seconds,lead_braking\n"
                "0.05,10,30,,False\n0.10,12,20,5,False\n"
                "0.15,14,12,2,True\n0.20,15,8,1,True\n",
                encoding="utf-8",
            )
            (run_dir / "metadata.json").write_text(
                '{"events":[{"type":"lead_vehicle_brake","elapsed_seconds":0.15}]}',
                encoding="utf-8",
            )
            manifest = build_replay_manifest(run_dir)
        self.assertEqual([item["sample_index"] for item in manifest["channels"]["rgb"]], [0, 2, 3])
        self.assertEqual(len(manifest["channels"]["semantic"]), 1)
        self.assertEqual(manifest["telemetry"][2]["lead_gap_distance_m"], 12.0)
        self.assertTrue(manifest["telemetry"][2]["lead_braking"])
        self.assertEqual(manifest["events"][0]["type"], "lead_vehicle_brake")
        self.assertEqual(manifest["alignment"], "frame_order_estimate")

    def test_replay_frame_rejects_invalid_channel_and_path(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            run_dir = Path(directory)
            (run_dir / "rgb").mkdir()
            frame = run_dir / "rgb" / "frame_000100.png"
            frame.write_bytes(b"png")
            self.assertEqual(resolve_replay_frame(run_dir, "rgb", frame.name), frame.resolve())
            for channel, filename in (("other", frame.name), ("rgb", "../secret.png"), ("rgb", "secret.png")):
                with self.subTest(channel=channel, filename=filename):
                    with self.assertRaises(ValueError):
                        resolve_replay_frame(run_dir, channel, filename)

    def test_replay_works_without_valid_metadata_events(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            run_dir = Path(directory)
            (run_dir / "rgb").mkdir()
            (run_dir / "rgb" / "frame_000100.png").write_bytes(b"png")
            (run_dir / "telemetry.csv").write_text("elapsed_seconds,ego_speed_kmh\n0.05,10\n", encoding="utf-8")
            (run_dir / "metadata.json").write_text("{invalid", encoding="utf-8")
            manifest = build_replay_manifest(run_dir)
        self.assertEqual(len(manifest["channels"]["rgb"]), 1)
        self.assertEqual(manifest["events"], [])

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

    def test_chart_panels_have_room_for_titles_and_legends(self):
        rows = [
            {"elapsed_seconds": "0", "ego_speed_kmh": "10", "lead_speed_kmh": "8", "ttc_seconds": "5", "lead_gap_distance_m": "12", "pedestrian_distance_m": "20"},
            {"elapsed_seconds": "1", "ego_speed_kmh": "20", "lead_speed_kmh": "6", "ttc_seconds": "2", "lead_gap_distance_m": "8", "pedestrian_distance_m": "10"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            chart = build_svg(Path(directory) / "chart.svg", rows)
            root = ET.parse(chart).getroot()
        texts = root.findall("{http://www.w3.org/2000/svg}text")
        first_legend_bottom = max(
            float(item.attrib["y"]) + 3
            for item in texts
            if item.attrib.get("class") == "legend" and float(item.attrib["y"]) < 400
        )
        second_title_top = next(
            float(item.attrib["y"]) - 18
            for item in texts
            if item.text == "安全时间与间距"
        )
        canvas_height = float(root.attrib["viewBox"].split()[3])
        last_legend_bottom = max(
            float(item.attrib["y"]) + 3
            for item in texts
            if item.attrib.get("class") == "legend"
        )
        self.assertGreaterEqual(second_title_top - first_legend_bottom, 20)
        self.assertGreaterEqual(canvas_height - last_legend_bottom, 24)

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
