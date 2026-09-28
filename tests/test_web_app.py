import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from tools.scenario_dashboard import load_dashboard_data
from tools.web_app import WebAppHandler, _task_detail_page


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"


class WebAppHttpTests(unittest.TestCase):
    def test_risk_detail_offers_replay_and_relative_view(self):
        task = {
            "task_id": "task_replay",
            "kind": "risk_analysis",
            "status": "completed",
            "workflow_id": "workflow_replay",
            "payload": {"run_dir": "F:\\Carla\\run"},
            "result": {"observed_risk": {"level": "medium", "score": 42}, "visualization": {}},
            "artifacts": [],
        }
        page = _task_detail_page(task, {"tasks": []})
        for marker in ('id="replay-player"', 'id="replay-scrubber"', 'id="relative-road"', '/static/replay.js'):
            self.assertIn(marker, page)
        self.assertIn("相对位置示意", page)
        self.assertIn("按帧序近似对齐", page)

    def test_replay_endpoints_serve_only_frames_from_task_run(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            run_dir = Path(directory)
            (run_dir / "rgb").mkdir()
            (run_dir / "rgb" / "frame_000100.png").write_bytes(b"frame")
            (run_dir / "telemetry.csv").write_text(
                "elapsed_seconds,ego_speed_kmh,lead_gap_distance_m\n0.05,12,8\n",
                encoding="utf-8",
            )
            task = {"task_id": "task_replay", "kind": "risk_analysis", "status": "completed", "payload": {"run_dir": str(run_dir)}}

            class ReplayManager:
                def get(self, task_id):
                    return task if task_id == "task_replay" else None

            handler = type("ReplayWebHandler", (WebAppHandler,), {})
            handler.dashboard_data = self.server.RequestHandlerClass.dashboard_data
            handler.task_manager = ReplayManager()
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/tasks/task_replay/replay", timeout=5) as response:
                    manifest = json.load(response)
                self.assertEqual(manifest["channels"]["rgb"][0]["name"], "frame_000100.png")
                with urlopen(base + "/api/tasks/task_replay/replay/frame/rgb/frame_000100.png", timeout=5) as response:
                    self.assertEqual(response.read(), b"frame")
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                for path in (
                    "/api/tasks/task_replay/replay/frame/other/frame_000100.png",
                    "/api/tasks/task_replay/replay/frame/rgb/secret.png",
                ):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as context:
                        urlopen(base + path, timeout=5)
                    self.assertEqual(context.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    @classmethod
    def setUpClass(cls):
        dashboard_data = load_dashboard_data(LIBRARY_DIR)
        handler_class = type("TestWebAppHandler", (WebAppHandler,), {})
        handler_class.dashboard_data = dashboard_data
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.first_library_id = dashboard_data["rows"][0]["library_id"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @classmethod
    def get_bytes(cls, path):
        with urlopen(cls.base_url + path, timeout=5) as response:
            return response.status, response.headers, response.read()

    @classmethod
    def get_json(cls, path):
        _, _, body = cls.get_bytes(path)
        return json.loads(body.decode("utf-8"))

    def test_web_pages_and_navigation(self):
        for path in ("/", "/dashboard", "/scenarios", "/generation", "/validation", "/tasks", "/risk"):
            status, headers, body = self.get_bytes(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers.get_content_type(), "text/html", path)
            self.assertIn("/scenarios", body.decode("utf-8"), path)

    def test_beginner_workbench_pages_explain_the_product(self):
        home = self.get_bytes("/dashboard")[2].decode("utf-8")
        for marker in ("hero-grid", "把驾驶参数变成看得懂", "THE WORKFLOW", "开始设计一个场景", "本机优先运行"):
            self.assertIn(marker, home)
        library = self.get_bytes("/scenarios")[2].decode("utf-8")
        for marker in ("SCENARIO LIBRARY", "library-rows", "普通用户先看什么", "查看详情"):
            self.assertIn(marker, library)
        self.assertIn("escLibrary", library)
        self.assertIn("&quot;", library)
        self.assertIn("AbortController", library)
        self.assertIn("场景库暂时不可用", library)
        validation = self.get_bytes("/validation")[2].decode("utf-8")
        for marker in ("workflow-sidebar", "测试流程总控", "validation-table", "启动本机 CARLA", "/carla", "/compile"):
            self.assertIn(marker, validation)

    def test_workflow_pages_are_operational_forms(self):
        expected = {
            "/generation": ("/api/tasks", "生成数量", "提交任务"),
            "/validation": ("/api/tasks", "记录路径", "编译 CARLA 配置"),
            "/risk": ("/api/tasks", "运行目录", "遥测 CSV"),
        }
        for path, markers in expected.items():
            body = self.get_bytes(path)[2].decode("utf-8")
            for marker in markers:
                self.assertIn(marker, body, f"{path} 缺少 {marker}")

    def test_tasks_page_uses_cancel_endpoint(self):
        body = self.get_bytes("/tasks")[2].decode("utf-8")
        self.assertIn('transition(button.dataset.cancel, "cancel")', body)
        self.assertNotIn('transition(button.dataset.cancel, "confirm"', body)
        self.assertIn('.table-wrap { overflow-x: auto;', body)
        self.assertIn('class="task-table"', body)
        self.assertIn('class="task-result"', body)
        self.assertIn('text-overflow: ellipsis;', body)
        self.assertIn("'" + '"' + "':\"" + "&quot;" + '"', body)
        self.assertNotIn('"":', body)

    def test_detail_page_and_health_contract(self):
        status, headers, body = self.get_bytes(f"/scenarios/{self.first_library_id}")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "text/html")
        self.assertIn("场景详情", body.decode("utf-8"))
        health = self.get_json("/healthz")
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["carla_connected"])
        self.assertEqual(health["entry_count"], 117)
        self.assertEqual(health["accepted_run_evidence_count"], 351)

    def test_task_detail_action_script_has_valid_braces(self):
        task = {
            "task_id": "task_test_compile",
            "kind": "validation",
            "status": "completed",
            "result": {"valid": True, "record_count": 1},
            "artifacts": [],
            "payload": {},
            "workflow_id": "workflow_test",
        }
        body = _task_detail_page(task, {"tasks": []})
        script_start = body.rfind("<script>")
        script_end = body.find("</script>", script_start)
        script = body[script_start:script_end]
        self.assertIn('fetch(taskPath + "/compile"', script)
        self.assertIn("async () => {", script)
        self.assertNotIn("{{", script)
        self.assertNotIn("}}", script)

    def test_failed_local_carla_detail_exposes_retry_action(self):
        task = {
            "task_id": "task_failed_carla",
            "kind": "carla",
            "status": "failed",
            "execution_mode": "local_carla",
            "result": None,
            "error": {"type": "TaskError", "message": "CARLA RPC timeout"},
            "artifacts": [],
            "payload": {"config_path": "F:\\Carla\\compiled.json"},
            "workflow_id": "workflow_test",
        }
        body = _task_detail_page(task, {"tasks": []})
        self.assertIn('id="retry-local-carla"', body)
        self.assertIn('taskPath + "/retry"', body)
        self.assertIn("重试本机 CARLA", body)

    def test_existing_api_contract_is_unchanged(self):
        summary = self.get_json("/api/summary")
        scenarios = self.get_json("/api/scenarios")
        self.assertEqual(summary["entry_count"], 117)
        self.assertEqual(summary["accepted_run_evidence_count"], 351)
        self.assertEqual(scenarios["count"], 117)
        record = self.get_json(f"/api/scenarios/{self.first_library_id}")
        self.assertEqual(record["library_id"], self.first_library_id)

    def test_unknown_page_returns_not_found(self):
        with self.assertRaises(HTTPError) as context:
            self.get_bytes("/missing")
        self.assertEqual(context.exception.code, 404)

    def test_browser_tracker_probe_is_ignored(self):
        status, _, body = self.get_bytes(
            "/hybridaction/zybTrackerStatisticsAction?data=%7B%7D&__callback=test"
        )
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")


if __name__ == "__main__":
    unittest.main()
