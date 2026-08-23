import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.scenario_dashboard import load_dashboard_data
from tools.web_app import WebAppHandler
from core.web_task_orchestrator import TaskManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"
RECORD_PATH = PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "example_record.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"
RUN_DIR = Path(r"F:\Carla\output-0.9.16\adapter_smoke\seed_v1_high_0165\20260818_222032")


class WebTaskOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="web-task-test-")
        handler_class = type("TestTaskHandler", (WebAppHandler,), {})
        handler_class.dashboard_data = load_dashboard_data(LIBRARY_DIR)
        handler_class.task_manager = TaskManager(cls.temp_dir.name)
        cls.handler_class = handler_class
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.handler_class.task_manager.close()
        cls.temp_dir.cleanup()

    @classmethod
    def request_json(cls, method, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(cls.base_url + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    @classmethod
    def wait_for(cls, task_id, *statuses):
        deadline = time.time() + 10
        while time.time() < deadline:
            task = cls.handler_class.task_manager.get(task_id)
            if task and task["status"] in statuses:
                return task
            time.sleep(0.05)
        raise AssertionError(f"任务未进入 {statuses}: {task_id}")

    def test_validation_task_returns_static_result(self):
        status, task = self.request_json(
            "POST",
            "/api/tasks",
            {
                "kind": "validation",
                "payload": {
                    "record_path": str(RECORD_PATH),
                    "base_config_path": str(CONFIG_PATH),
                    "compile": True,
                },
            },
        )
        self.assertEqual(status, 202)
        completed = self.wait_for(task["task_id"], "completed")
        self.assertTrue(completed["result"]["valid"])
        self.assertTrue(Path(completed["result"]["compiled_config_path"]).is_file())
        restored = TaskManager(self.temp_dir.name)
        try:
            self.assertEqual(restored.get(task["task_id"])["status"], "completed")
        finally:
            restored.close()
        result_status, result = self.request_json("GET", f"/api/tasks/{task['task_id']}/result")
        self.assertEqual(result_status, 200)
        self.assertTrue(result["valid"])

    def test_validation_jsonl_returns_per_record_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
            path.write_text(json.dumps(record, ensure_ascii=False) + "\n" + json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            status, task = self.request_json(
                "POST", "/api/tasks", {"kind": "validation", "payload": {"record_path": str(path)}}
            )
            self.assertEqual(status, 202)
            completed = self.wait_for(task["task_id"], "completed")
            self.assertEqual(completed["result"]["record_count"], 2)
            self.assertEqual(len(completed["result"]["items"]), 2)
            self.assertTrue(completed["result"]["valid"])

    def test_generation_task_runs_cpu_lhs(self):
        status, task = self.request_json(
            "POST",
            "/api/tasks",
            {"kind": "generation", "payload": {"model": "lhs", "risk": "low", "count": 1, "seed": 20260823}},
        )
        self.assertEqual(status, 202)
        completed = self.wait_for(task["task_id"], "completed")
        self.assertEqual(completed["result"]["summary"]["accepted_count"], 1)
        self.assertEqual(completed["result"]["execution_mode"], "offline_cpu")

    def test_cancelled_worker_cannot_overwrite_terminal_status(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TaskManager(directory, max_workers=1)
            started = threading.Event()
            release = threading.Event()

            def delayed_generation(_task):
                started.set()
                release.wait(timeout=3)
                return {"execution_mode": "offline_cpu"}

            manager._run_generation = delayed_generation
            try:
                task = manager.submit(
                    "generation",
                    {"model": "lhs", "risk": "low", "count": 1, "seed": 1},
                )
                self.assertTrue(started.wait(timeout=3))
                cancelled = manager.cancel(task["task_id"])
                self.assertEqual(cancelled["status"], "cancelled")
                release.set()
                deadline = time.time() + 3
                while time.time() < deadline and manager.get(task["task_id"])["status"] == "running":
                    time.sleep(0.01)
                self.assertEqual(manager.get(task["task_id"])["status"], "cancelled")
            finally:
                release.set()
                manager.close()

    def test_worker_failure_is_persisted_as_structured_error(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TaskManager(directory, max_workers=1)

            def failing_generation(_task):
                raise RuntimeError("P0 failure visibility")

            manager._run_generation = failing_generation
            try:
                task = manager.submit(
                    "generation",
                    {"model": "lhs", "risk": "low", "count": 1, "seed": 1},
                )
                deadline = time.time() + 3
                failed = manager.get(task["task_id"])
                while time.time() < deadline and failed["status"] not in ("failed", "completed"):
                    time.sleep(0.01)
                    failed = manager.get(task["task_id"])
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["error"]["type"], "RuntimeError")
                self.assertIn("P0 failure visibility", failed["error"]["message"])
            finally:
                manager.close()

    def test_carla_task_requires_explicit_confirmation(self):
        status, task = self.request_json(
            "POST",
            "/api/tasks",
            {"kind": "carla", "payload": {"config_path": str(CONFIG_PATH)}},
        )
        self.assertEqual(status, 202)
        self.assertEqual(task["status"], "awaiting_confirmation")
        with self.assertRaises(HTTPError) as context:
            self.request_json("GET", f"/api/tasks/{task['task_id']}/result")
        self.assertEqual(context.exception.code, 409)
        confirm_status, confirmed = self.request_json(
            "POST",
            f"/api/tasks/{task['task_id']}/confirm",
            {"confirmed": True},
        )
        self.assertEqual(confirm_status, 200)
        self.assertEqual(confirmed["status"], "confirmed_manual")
        self.assertFalse(confirmed["result"]["carla_connected"])
        self.assertFalse(confirmed["result"]["execution_started"])

    def test_carla_task_can_be_cancelled_without_execution(self):
        status, task = self.request_json(
            "POST",
            "/api/tasks",
            {"kind": "carla", "payload": {"config_path": str(CONFIG_PATH)}},
        )
        self.assertEqual(status, 202)
        cancel_status, cancelled = self.request_json(
            "POST", f"/api/tasks/{task['task_id']}/cancel"
        )
        self.assertEqual(cancel_status, 200)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertFalse(cancelled["result"]["execution_started"])
        self.assertFalse(cancelled["result"]["carla_connected"])

    def test_risk_analysis_task_uses_existing_evidence(self):
        if not (RUN_DIR / "metadata.json").is_file() or not (RUN_DIR / "telemetry.csv").is_file():
            self.skipTest("本机没有阶段四历史风险证据")
        status, task = self.request_json(
            "POST",
            "/api/tasks",
            {"kind": "risk_analysis", "payload": {"run_dir": str(RUN_DIR)}},
        )
        self.assertEqual(status, 202)
        completed = self.wait_for(task["task_id"], "completed")
        self.assertEqual(completed["result"]["observed_risk"]["method"], "heuristic_v2")
        self.assertGreater(completed["result"]["source_row_count"], 0)

    def test_invalid_task_payload_returns_bad_request(self):
        with self.assertRaises(HTTPError) as context:
            self.request_json("POST", "/api/tasks", {"kind": "carla", "payload": {}})
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
