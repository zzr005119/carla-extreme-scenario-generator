"""Small, auditable task orchestration contract for the local Web app.

The manager deliberately keeps the execution surface narrow: offline generation,
static validation, post-run risk analysis, and an explicitly requested local
CARLA client run can execute in worker threads. The Web process never launches
the CARLA server itself; remote execution remains an explicit compatibility path.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASK_DIR = Path(
    os.environ.get(
        "CARLA_WEB_TASK_DIR",
        r"F:\Carla\output-0.9.16\web_tasks",
    )
)
DEFAULT_CARLA_OUTPUT_DIR = Path(
    os.environ.get(
        "CARLA_WEB_CARLA_OUTPUT_DIR",
        r"F:\Carla\output-0.9.16\web_tasks",
    )
)
TASK_KINDS = ("generation", "validation", "risk_analysis", "carla")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "confirmed_manual")


class TaskError(ValueError):
    """Invalid task request or an unsupported task transition."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_records(path):
    """Load one JSON record or every non-empty record from a JSONL file."""
    path = Path(path)
    if path.suffix.lower() != ".jsonl":
        return [_load_json(path)]
    records = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append((line_number, json.loads(line)))
            except json.JSONDecodeError as error:
                raise TaskError(f"JSONL 第 {line_number} 行无法解析: {error}") from error
    if not records:
        raise TaskError(f"记录文件为空: {path}")
    return records


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path, *, artifact_type, role, source_task_id):
    path = Path(path).resolve()
    if not path.is_file():
        raise TaskError(f"任务产物不存在: {path}")
    sha256 = _file_sha256(path)
    return {
        "artifact_id": f"artifact_{sha256[:16]}",
        "type": artifact_type,
        "role": role,
        "path": str(path),
        "sha256": sha256,
        "size_bytes": path.stat().st_size,
        "source_task_id": source_task_id,
    }


def _as_path(value, field):
    if not isinstance(value, str) or not value.strip():
        raise TaskError(f"{field} 必须是非空路径")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise TaskError(f"{field} 不存在: {path}")
    return path


class TaskManager:
    """Persist task state and execute safe offline work in worker threads."""

    def __init__(self, storage_dir=None, *, max_workers=2):
        self.storage_dir = Path(storage_dir or DEFAULT_TASK_DIR).expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._tasks = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="scenario-web-task",
        )
        self._load_tasks()

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _task_path(self, task_id):
        return self.storage_dir / f"{task_id}.json"

    def _load_tasks(self):
        for path in sorted(self.storage_dir.glob("task_*.json")):
            try:
                task = _load_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            task_id = task.get("task_id")
            if task_id:
                task.setdefault("workflow_id", f"workflow_legacy_{task_id.removeprefix('task_')}")
                task.setdefault("workflow_step", 1)
                task.setdefault("parent_task_id", None)
                task.setdefault("artifacts", [])
                task.setdefault(
                    "evidence_level",
                    "external_unverified" if task.get("requires_carla") else "offline",
                )
                self._tasks[task_id] = task

    def _persist(self, task):
        _write_json(self._task_path(task["task_id"]), task)

    def _snapshot(self, task):
        return deepcopy(task)

    def _update(self, task_id, **changes):
        with self._lock:
            task = self._tasks[task_id]
            task.update(changes)
            self._persist(task)
            return self._snapshot(task)

    def list_tasks(self):
        with self._lock:
            tasks = [self._snapshot(task) for task in self._tasks.values()]
        return sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True)

    def get(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id))
            return self._snapshot(task) if task is not None else None

    def get_workflow(self, workflow_id):
        with self._lock:
            tasks = [
                self._snapshot(task)
                for task in self._tasks.values()
                if task.get("workflow_id") == str(workflow_id)
            ]
        if not tasks:
            return None
        tasks.sort(
            key=lambda item: (
                item.get("workflow_step", 1),
                item.get("created_at", ""),
                item.get("task_id", ""),
            )
        )
        latest = tasks[-1]
        artifacts = [artifact for task in tasks for artifact in task.get("artifacts", [])]
        timestamps = [
            task.get("finished_at") or task.get("started_at") or task.get("created_at")
            for task in tasks
        ]
        return {
            "workflow_id": str(workflow_id),
            "task_ids": [task["task_id"] for task in tasks],
            "current_stage": latest["kind"],
            "status": latest["status"],
            "scenario_ids": [],
            "artifacts": artifacts,
            "evidence_level": (
                "external_unverified"
                if any(task.get("requires_carla") for task in tasks)
                else "offline"
            ),
            "created_at": tasks[0].get("created_at"),
            "updated_at": max(value for value in timestamps if value),
            "tasks": tasks,
        }

    def submit(
        self,
        kind,
        payload=None,
        *,
        confirm_carla=False,
        workflow_id=None,
        parent_task_id=None,
    ):
        kind = str(kind or "").strip()
        if kind not in TASK_KINDS:
            raise TaskError(f"不支持的任务类型: {kind or '空'}")
        payload = deepcopy(payload or {})
        if not isinstance(payload, dict):
            raise TaskError("payload 必须是 JSON 对象")
        normalized = self._validate_payload(kind, payload)
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}"
        if parent_task_id is not None:
            parent = self.get(parent_task_id)
            if parent is None:
                raise TaskError(f"父任务不存在: {parent_task_id}")
            if workflow_id is not None and workflow_id != parent.get("workflow_id"):
                raise TaskError("workflow_id 与父任务不一致")
            workflow_id = parent.get("workflow_id")
        if workflow_id is None:
            workflow_id = f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}"
        workflow_tasks = self.get_workflow(workflow_id)
        workflow_step = max(
            (item.get("workflow_step", 1) for item in (workflow_tasks or {}).get("tasks", [])),
            default=0,
        ) + 1
        requires_carla = kind == "carla"
        local_carla = requires_carla and normalized.get("execution_target") == "local"
        task = {
            "task_id": task_id,
            "workflow_id": workflow_id,
            "workflow_step": workflow_step,
            "parent_task_id": parent_task_id,
            "kind": kind,
            "status": "queued" if local_carla else "awaiting_confirmation" if requires_carla else "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "requires_carla": requires_carla,
            "execution_mode": "local_carla" if local_carla else "manual_external" if requires_carla else "offline_cpu",
            "evidence_level": "external_unverified" if requires_carla else "offline",
            "payload": normalized,
            "result": None,
            "error": None,
            "artifacts": [],
        }
        with self._lock:
            self._tasks[task_id] = task
            self._persist(task)
        if requires_carla and not local_carla:
            if confirm_carla:
                return self.confirm(task_id, confirmed=True)
            return self._snapshot(task)
        self._executor.submit(self._run, task_id)
        return self._snapshot(task)

    def submit_validation_from_generation(self, source_task_id, payload=None):
        source = self.get(source_task_id)
        if source is None:
            raise KeyError(source_task_id)
        if source["kind"] != "generation":
            raise TaskError("只有生成任务可以直接创建校验任务")
        if source["status"] != "completed":
            raise TaskError(f"生成任务尚未完成: {source['status']}")
        output_path = (source.get("result") or {}).get("output_path")
        if not output_path:
            raise TaskError("生成任务缺少 JSONL 产物")
        validation_payload = deepcopy(payload or {})
        if not isinstance(validation_payload, dict):
            raise TaskError("payload 必须是 JSON 对象")
        validation_payload["record_path"] = output_path
        # A one-scenario generation is the primary product path: compile the
        # CARLA input immediately so the next task can expose the run action.
        # Batch generation remains validation-only because the CARLA adapter
        # accepts one concrete scenario at a time.
        accepted_count = ((source.get("result") or {}).get("summary") or {}).get("accepted_count")
        validation_payload.setdefault("compile", accepted_count == 1)
        return self.submit(
            "validation",
            validation_payload,
            workflow_id=source["workflow_id"],
            parent_task_id=source["task_id"],
        )

    def submit_carla_from_validation(self, source_task_id, payload=None):
        source = self.get(source_task_id)
        if source is None:
            raise KeyError(source_task_id)
        if source["kind"] != "validation" or source["status"] != "completed":
            raise TaskError("只有已完成的校验任务可以登记 CARLA 执行")
        result = source.get("result") or {}
        config_path = result.get("compiled_config_path")
        if not config_path:
            raise TaskError("校验任务没有编译配置；请先以 compile=true 重新校验")
        carla_payload = dict(payload or {})
        carla_payload["config_path"] = config_path
        carla_payload.setdefault("requested_by", "web")
        carla_payload.setdefault("execution_target", "local")
        return self.submit(
            "carla",
            carla_payload,
            workflow_id=source["workflow_id"],
            parent_task_id=source["task_id"],
        )

    def attach_carla_result(self, task_id, payload=None):
        payload = dict(payload or {})
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task["kind"] != "carla":
            raise TaskError("只有 CARLA 外部任务可以导入结果")
        if task["status"] not in {"awaiting_confirmation", "confirmed_manual"}:
            raise TaskError(f"CARLA 任务当前状态不能导入结果: {task['status']}")
        run_dir = Path(str(payload.get("run_dir", ""))).expanduser().resolve()
        if not run_dir.is_dir():
            raise TaskError(f"远端结果目录不存在: {run_dir}")
        metadata_path = run_dir / "metadata.json"
        telemetry_path = run_dir / "telemetry.csv"
        if not metadata_path.is_file() or not telemetry_path.is_file():
            raise TaskError("结果目录必须同时包含 metadata.json 和 telemetry.csv")
        metadata = _load_json(metadata_path)
        carla_connected = bool((metadata.get("server_health") or {}).get("status") == "healthy")
        result = {
            "execution_started": True,
            "carla_connected": carla_connected,
            "execution_mode": "remote_result_import",
            "remote_job_id": payload.get("remote_job_id"),
            "remote_path": payload.get("remote_path"),
            "run_dir": str(run_dir),
            "metadata_path": str(metadata_path),
            "telemetry_path": str(telemetry_path),
            "acceptance_status": (metadata.get("result") or {}).get("status"),
            "sensor_status": (metadata.get("sensor_pipeline") or {}).get("status"),
            "server_health": metadata.get("server_health"),
        }
        with self._lock:
            current = self._tasks[task_id]
            current.update(
                status="completed",
                finished_at=_now(),
                evidence_level="external_verified" if carla_connected else "external_unverified",
                result=result,
            )
            self._persist(current)
        risk_task = self.submit(
            "risk_analysis",
            {"run_dir": str(run_dir), "metadata_path": str(metadata_path), "telemetry_path": str(telemetry_path)},
            workflow_id=task["workflow_id"],
            parent_task_id=task_id,
        )
        return {"carla_task": self.get(task_id), "risk_task": risk_task}

    def run_local_carla(self, task_id):
        """Queue a CARLA task on the current machine.

        This is intentionally explicit: the Web process never starts the CARLA
        server itself, but it can run the local Scene 04 client when CARLA is
        already listening on localhost:2000.
        """
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task["kind"] != "carla":
                raise TaskError("只有 CARLA 任务可以切换为本机运行")
            if task["status"] not in {"awaiting_confirmation", "confirmed_manual"}:
                raise TaskError(f"任务当前状态不能切换为本机运行: {task['status']}")
            task["payload"]["execution_target"] = "local"
            task["status"] = "queued"
            task["execution_mode"] = "local_carla"
            task["result"] = None
            task["error"] = None
            task["started_at"] = None
            task["finished_at"] = None
            self._persist(task)
            snapshot = self._snapshot(task)
        self._executor.submit(self._run, task_id)
        return snapshot

    def retry_local_carla(self, task_id):
        """Create a new local CARLA attempt while preserving the failed task."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task["kind"] != "carla" or task.get("execution_mode") != "local_carla":
            raise TaskError("只有失败的本机 CARLA 任务可以重试")
        if task.get("status") != "failed":
            raise TaskError(f"任务当前状态不能重试: {task.get('status')}")
        payload = deepcopy(task.get("payload") or {})
        payload["execution_target"] = "local"
        payload.setdefault("requested_by", "web-retry")
        return self.submit(
            "carla",
            payload,
            workflow_id=task.get("workflow_id"),
            parent_task_id=task["task_id"],
        )

    def recompile_validation(self, task_id):
        """Re-run a completed single-record validation with CARLA compilation."""
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task["kind"] != "validation":
                raise TaskError("只有校验任务可以重新编译 CARLA 配置")
            if task["status"] != "completed":
                raise TaskError(f"校验任务当前状态不能重新编译: {task['status']}")
            result = task.get("result") or {}
            if not result.get("valid"):
                raise TaskError("校验未通过，不能编译 CARLA 配置")
            if int(result.get("record_count", 0)) != 1:
                raise TaskError("只有单条场景记录可以编译 CARLA 配置")
            if result.get("compiled_config_path"):
                return self._snapshot(task)
            task["payload"]["compile"] = True
            task["status"] = "queued"
            task["result"] = None
            task["error"] = None
            task["started_at"] = None
            task["finished_at"] = None
            self._persist(task)
            snapshot = self._snapshot(task)
        self._executor.submit(self._run, task_id)
        return snapshot

    def export_task(self, task_id):
        """Create a self-contained ZIP with both readable and raw evidence."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task["status"] in {"queued", "running"}:
            raise TaskError("任务仍在运行，完成后才能导出完整数据包")

        task_dir = self.storage_dir / task["task_id"]
        task_dir.mkdir(parents=True, exist_ok=True)
        archive_path = task_dir / f"{task['task_id']}_export.zip"
        temporary = archive_path.with_suffix(".zip.tmp")
        workflow = self.get_workflow(task["workflow_id"]) or {}
        seen = set()

        def add_file(archive, path, arcname):
            path = Path(path)
            if not path.is_file():
                return
            resolved = path.resolve()
            if resolved in seen or resolved == archive_path.resolve() or resolved == temporary.resolve():
                return
            seen.add(resolved)
            archive.write(resolved, arcname=arcname)

        def add_tree(archive, root, prefix):
            root = Path(root)
            if not root.is_dir():
                return
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(root).as_posix()
                    add_file(archive, path, f"{prefix}/{relative}")

        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
            archive.writestr("payload.json", json.dumps(task.get("payload", {}), ensure_ascii=False, indent=2) + "\n")
            archive.writestr("result.json", json.dumps(task.get("result"), ensure_ascii=False, indent=2) + "\n")
            archive.writestr("workflow.json", json.dumps(workflow, ensure_ascii=False, indent=2) + "\n")
            add_tree(archive, task_dir, "task_outputs")
            workflow_tasks = workflow.get("tasks", []) or [task]
            artifact_index = 1
            for workflow_task in workflow_tasks:
                workflow_task_id = workflow_task.get("task_id", task["task_id"])
                if workflow_task_id != task["task_id"]:
                    add_tree(
                        archive,
                        self.storage_dir / workflow_task_id,
                        f"task_outputs/{workflow_task_id}",
                    )
                result = workflow_task.get("result") or {}
                run_dir = result.get("run_dir")
                if run_dir:
                    add_tree(archive, run_dir, f"carla_run/{workflow_task_id}")
                for artifact in workflow_task.get("artifacts", []):
                    artifact_path = artifact.get("path")
                    if artifact_path:
                        add_file(
                            archive,
                            artifact_path,
                            f"artifacts/{artifact_index:03d}_{Path(artifact_path).name}",
                        )
                        artifact_index += 1
        temporary.replace(archive_path)
        export_artifact = _artifact(
            archive_path,
            artifact_type="export_bundle",
            role="complete_diagnostic_package",
            source_task_id=task["task_id"],
        )
        with self._lock:
            current = self._tasks[task_id]
            current.setdefault("artifacts", [])
            current["artifacts"] = [
                item for item in current["artifacts"]
                if item.get("type") != "export_bundle"
            ] + [export_artifact]
            current.setdefault("result", {})
            current["result"]["export_path"] = str(archive_path)
            current["result"]["export_sha256"] = export_artifact["sha256"]
            self._persist(current)
            return str(archive_path)

    def confirm(self, task_id, *, confirmed):
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task["kind"] != "carla":
                raise TaskError("只有 CARLA 任务需要显式确认")
            if task.get("payload", {}).get("execution_target") == "local":
                raise TaskError("本机 CARLA 任务无需远端确认，请直接等待运行结果")
            if task["status"] != "awaiting_confirmation":
                raise TaskError(f"任务当前状态不能确认: {task['status']}")
            if not confirmed:
                task["status"] = "cancelled"
                task["finished_at"] = _now()
                task["result"] = {
                    "execution_started": False,
                    "carla_connected": False,
                    "reason": "用户未确认 CARLA 外部执行",
                }
            else:
                task["status"] = "confirmed_manual"
                task["finished_at"] = _now()
                task["result"] = {
                    "execution_started": False,
                    "carla_connected": False,
                    "execution_mode": "manual_external",
                    "message": "已确认外部 CARLA 执行；Web 进程不会启动 CARLA，请使用服务器任务入口执行。",
                    "config_path": task["payload"].get("config_path"),
                }
            self._persist(task)
            return self._snapshot(task)

    def cancel(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task["status"] in TERMINAL_STATUSES:
                raise TaskError(f"任务已结束: {task['status']}")
            task["status"] = "cancelled"
            task["finished_at"] = _now()
            task["result"] = {"execution_started": False, "reason": "用户取消"}
            if task["kind"] == "carla":
                task["result"]["carla_connected"] = False
            self._persist(task)
            return self._snapshot(task)

    def _validate_payload(self, kind, payload):
        if kind == "generation":
            model = str(payload.get("model", "lhs")).strip().lower()
            risk = str(payload.get("risk", "medium")).strip().lower()
            if model not in ("lhs", "gmm", "cvae", "diffusion"):
                raise TaskError("generation.model 必须是 lhs/gmm/cvae/diffusion")
            if risk not in ("low", "medium", "high", "critical"):
                raise TaskError("generation.risk 必须是 low/medium/high/critical")
            try:
                count = int(payload.get("count", 1))
                seed = int(payload.get("seed", 20260823))
            except (TypeError, ValueError) as error:
                raise TaskError("generation.count 和 generation.seed 必须是整数") from error
            if not 1 <= count <= 64:
                raise TaskError("generation.count 必须在 1..64 内")
            normalized = {
                "model": model,
                "risk": risk,
                "count": count,
                "seed": seed,
                "weather_tags": payload.get("weather_tags", []),
            }
            if isinstance(normalized["weather_tags"], str):
                normalized["weather_tags"] = [
                    item.strip()
                    for item in normalized["weather_tags"].split(",")
                    if item.strip()
                ]
            if not isinstance(normalized["weather_tags"], list):
                raise TaskError("generation.weather_tags 必须是数组或逗号分隔字符串")
            if model != "lhs":
                normalized["artifact"] = str(_as_path(payload.get("artifact"), "generation.artifact"))
            return normalized
        if kind == "validation":
            if "record" not in payload and "record_path" not in payload:
                raise TaskError("validation 需要 record 或 record_path")
            normalized = {"compile": bool(payload.get("compile", False))}
            if "record" in payload:
                if not isinstance(payload["record"], dict):
                    raise TaskError("validation.record 必须是 JSON 对象")
                normalized["record"] = payload["record"]
            else:
                normalized["record_path"] = str(_as_path(payload["record_path"], "validation.record_path"))
            if payload.get("base_config_path"):
                normalized["base_config_path"] = str(_as_path(payload["base_config_path"], "validation.base_config_path"))
            return normalized
        if kind == "risk_analysis":
            if not payload.get("telemetry_rows") and not payload.get("telemetry_path") and not payload.get("run_dir"):
                raise TaskError("risk_analysis 需要 telemetry_rows、telemetry_path 或 run_dir")
            normalized = {}
            if payload.get("run_dir"):
                run_dir = Path(payload["run_dir"]).expanduser().resolve()
                if not run_dir.is_dir():
                    raise TaskError(f"risk_analysis.run_dir 不存在: {run_dir}")
                normalized["run_dir"] = str(run_dir)
            for name in ("telemetry_path", "metadata_path", "config_path"):
                if payload.get(name):
                    normalized[name] = str(_as_path(payload[name], f"risk_analysis.{name}"))
            if payload.get("telemetry_rows"):
                if not isinstance(payload["telemetry_rows"], list):
                    raise TaskError("risk_analysis.telemetry_rows 必须是数组")
                normalized["telemetry_rows"] = payload["telemetry_rows"]
            if payload.get("risk_config"):
                normalized["risk_config"] = payload["risk_config"]
            if payload.get("collision_count") is not None:
                normalized["collision_count"] = int(payload["collision_count"])
            return normalized
        config_path = _as_path(payload.get("config_path"), "carla.config_path")
        execution_target = str(payload.get("execution_target", "local")).strip().lower()
        if execution_target not in {"local", "remote"}:
            raise TaskError("carla.execution_target 必须是 local 或 remote")
        try:
            timeout_seconds = int(payload.get("timeout_seconds", 900))
        except (TypeError, ValueError) as error:
            raise TaskError("carla.timeout_seconds 必须是整数") from error
        if not 30 <= timeout_seconds <= 7200:
            raise TaskError("carla.timeout_seconds 必须在 30..7200 内")
        normalized = {
            "config_path": str(config_path),
            "execution_target": execution_target,
            "traffic_manager_seed": payload.get("traffic_manager_seed"),
            "requested_by": str(payload.get("requested_by", "web")),
            "timeout_seconds": timeout_seconds,
        }
        if payload.get("output_root"):
            normalized["output_root"] = str(Path(payload["output_root"]).expanduser().resolve())
        if payload.get("python_executable"):
            normalized["python_executable"] = str(payload["python_executable"])
        if payload.get("traffic_manager_port") is not None:
            try:
                port = int(payload["traffic_manager_port"])
            except (TypeError, ValueError) as error:
                raise TaskError("carla.traffic_manager_port 必须是整数") from error
            if not 1 <= port <= 65535:
                raise TaskError("carla.traffic_manager_port 必须在 1..65535 内")
            normalized["traffic_manager_port"] = port
        return normalized

    def _run(self, task_id):
        with self._lock:
            task = self._tasks[task_id]
            if task["status"] in TERMINAL_STATUSES:
                return
            task.update(status="running", started_at=_now())
            self._persist(task)
        try:
            task = self.get(task_id)
            if task["kind"] == "generation":
                result = self._run_generation(task)
            elif task["kind"] == "validation":
                result = self._run_validation(task)
            elif task["kind"] == "risk_analysis":
                result = self._run_risk_analysis(task)
            elif task["kind"] == "carla":
                result = self._run_carla(task)
            else:
                raise TaskError("CARLA 任务必须经过显式确认，不会进入离线 worker")
        except Exception as error:  # Persist a concise, user-visible failure.
            with self._lock:
                if self._tasks[task_id]["status"] == "cancelled":
                    return
                self._tasks[task_id].update(
                    status="failed",
                    finished_at=_now(),
                    error={"type": type(error).__name__, "message": str(error)},
                )
                self._persist(self._tasks[task_id])
            return
        risk_payload = None
        with self._lock:
            if self._tasks[task_id]["status"] == "cancelled":
                return
            artifacts = result.pop("_artifacts", [])
            self._tasks[task_id].update(
                status="completed",
                finished_at=_now(),
                result=result,
                artifacts=artifacts,
            )
            self._persist(self._tasks[task_id])
            if task["kind"] == "carla" and result.get("metadata_path") and result.get("telemetry_path"):
                risk_payload = {
                    "run_dir": result.get("run_dir"),
                    "metadata_path": result["metadata_path"],
                    "telemetry_path": result["telemetry_path"],
                    "config_path": result.get("config_path"),
                }
        if risk_payload:
            risk_task = self.submit(
                "risk_analysis",
                risk_payload,
                workflow_id=task["workflow_id"],
                parent_task_id=task_id,
            )
            with self._lock:
                current = self._tasks[task_id]
                current["result"]["risk_task_id"] = risk_task["task_id"]
                self._persist(current)

    def _task_output_dir(self, task):
        path = self.storage_dir / task["task_id"]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _run_generation(self, task):
        payload = task["payload"]
        output = self._task_output_dir(task) / "generated_scenarios.jsonl"
        command = [
            sys.executable,
            str(PROJECT_ROOT / "tools" / "generate_with_model.py"),
            "--model", payload["model"], "--risk", payload["risk"],
            "--count", str(payload["count"]), "--max-attempts", str(payload["count"] * 2),
            "--seed", str(payload["seed"]), "--output", str(output),
        ]
        if payload["weather_tags"]:
            command.extend(["--weather-tags", ",".join(payload["weather_tags"])])
        if payload.get("artifact"):
            command.extend(["--artifact", payload["artifact"]])
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["CUDA_VISIBLE_DEVICES"] = ""
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            raise TaskError(detail[-1] if detail else f"生成命令退出码 {completed.returncode}")
        summary_path = output.with_name("generated_scenarios_summary.json")
        summary = _load_json(summary_path) if summary_path.is_file() else {}
        artifacts = [
            _artifact(
                output,
                artifact_type="scenario_records",
                role="generated_candidates",
                source_task_id=task["task_id"],
            )
        ]
        if summary_path.is_file():
            artifacts.append(
                _artifact(
                    summary_path,
                    artifact_type="generation_summary",
                    role="task_summary",
                    source_task_id=task["task_id"],
                )
            )
        return {
            "kind": "generation",
            "execution_mode": "offline_cpu",
            "output_path": str(output),
            "summary_path": str(summary_path),
            "summary": summary,
            "_artifacts": artifacts,
        }

    def _find_run_directory(self, output_root, started_at):
        candidates = []
        for metadata_path in Path(output_root).rglob("metadata.json"):
            telemetry_path = metadata_path.parent / "telemetry.csv"
            if not telemetry_path.is_file():
                continue
            try:
                modified = metadata_path.stat().st_mtime
            except OSError:
                continue
            if modified >= started_at - 5:
                candidates.append((modified, metadata_path.parent))
        if not candidates:
            raise TaskError(f"CARLA 已结束但未找到完整运行目录: {output_root}")
        return max(candidates, key=lambda item: item[0])[1]

    def _run_carla(self, task):
        payload = task["payload"]
        output_root = Path(payload.get("output_root") or DEFAULT_CARLA_OUTPUT_DIR).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        python_executable = str(
            payload.get("python_executable")
            or os.environ.get("CARLA_WEB_PYTHON")
            or sys.executable
        )
        command = [
            python_executable,
            str(PROJECT_ROOT / "scenes" / "scene_04_parameterized.py"),
            "--config",
            payload["config_path"],
            "--output-root",
            str(output_root),
        ]
        if payload.get("traffic_manager_port") is not None:
            command.extend(["--traffic-manager-port", str(payload["traffic_manager_port"])])
        output_dir = self._task_output_dir(task)
        stdout_path = output_dir / "carla_stdout.log"
        stderr_path = output_dir / "carla_stderr.log"
        command_path = output_dir / "carla_command.json"
        _write_json(command_path, {"command": command, "output_root": str(output_root)})
        started_at = time.time()
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        timeout_seconds = int(payload.get("timeout_seconds", 900))
        try:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            stdout_path.write_text(str(error.stdout or ""), encoding="utf-8")
            stderr_path.write_text(
                f"本机 CARLA 任务超过 {timeout_seconds} 秒，已停止。\n{error.stderr or ''}",
                encoding="utf-8",
            )
            raise TaskError(f"本机 CARLA 运行超时（{timeout_seconds} 秒）") from error
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail = " | ".join(detail[-5:])
            combined = "\n".join(detail)
            if "No module named 'carla'" in combined or "No module named \"carla\"" in combined:
                raise TaskError(
                    "本机 Python 环境未安装 CARLA Python API；请使用 Carla666-0916 环境，或设置 CARLA_WEB_PYTHON"
                )
            if (
                "ConnectionRefusedError" in combined
                or "Failed to connect" in combined
                or "连接被拒绝" in combined
                or "waiting for the simulator" in combined
                or "localhost:2000" in combined
            ):
                raise TaskError(
                    "无法连接本机 CARLA；请先启动 CARLA 0.9.16 服务并确认 RPC 端口 2000"
                )
            raise TaskError(f"本机 CARLA 运行失败（退出码 {completed.returncode}）: {tail or '无日志'}")
        run_dir = self._find_run_directory(output_root, started_at)
        metadata_path = run_dir / "metadata.json"
        telemetry_path = run_dir / "telemetry.csv"
        metadata = _load_json(metadata_path)
        server_health = metadata.get("server_health") or {}
        result_meta = metadata.get("result") or {}
        artifacts = []
        for path, artifact_type, role in (
            (command_path, "execution_command", "local_carla_command"),
            (stdout_path, "execution_log", "local_carla_stdout"),
            (stderr_path, "execution_log", "local_carla_stderr"),
            (metadata_path, "carla_metadata", "runtime_metadata"),
            (telemetry_path, "telemetry", "runtime_telemetry"),
        ):
            artifacts.append(_artifact(path, artifact_type=artifact_type, role=role, source_task_id=task["task_id"]))
        for name in ("config_snapshot.json",):
            path = run_dir / name
            if path.is_file():
                artifacts.append(_artifact(path, artifact_type="config_snapshot", role="runtime_config", source_task_id=task["task_id"]))
        return {
            "kind": "carla",
            "execution_started": True,
            "execution_mode": "local_carla",
            "execution_target": "local",
            "carla_connected": server_health.get("status") == "healthy",
            "acceptance_status": result_meta.get("status"),
            "sensor_status": (metadata.get("sensor_pipeline") or {}).get("status"),
            "route_status": (metadata.get("route_control") or {}).get("status"),
            "server_health": server_health,
            "config_path": payload["config_path"],
            "run_dir": str(run_dir),
            "metadata_path": str(metadata_path),
            "telemetry_path": str(telemetry_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "command_path": str(command_path),
            "_artifacts": artifacts,
        }

    def _record_from_payload(self, payload):
        if "record" in payload:
            return [(1, payload["record"])], None
        path = Path(payload["record_path"])
        records = _load_records(path)
        if records and not isinstance(records[0], tuple):
            records = [(1, records[0])]
        return records, path

    def _run_validation(self, task):
        from core.physical_constraints import build_physical_constraint_report
        from core.scenario_validator import compile_carla_config, load_json, validate_scenario_record

        payload = task["payload"]
        records, source_path = self._record_from_payload(payload)
        validations = []
        for line_number, record in records:
            validations.append(
                {
                    "line": line_number,
                    "sample_id": record.get("sample_id"),
                    "result": validate_scenario_record(record),
                }
            )
        physical = build_physical_constraint_report(records, source=source_path)
        validation = validations[0]["result"] if len(validations) == 1 else {
            "valid": all(item["result"]["valid"] for item in validations),
            "errors": [
                {"line": item["line"], "errors": item["result"]["errors"]}
                for item in validations
                if item["result"]["errors"]
            ],
            "warnings": [
                {"line": item["line"], "warnings": item["result"]["warnings"]}
                for item in validations
                if item["result"]["warnings"]
            ],
        }
        result = {
            "kind": "validation",
            "execution_mode": "offline_cpu",
            "schema_semantic": validation,
            "record_count": len(records),
            "items": validations,
            "physical_constraints": physical,
            "valid": bool(validation["valid"] and physical["valid_count"] == len(records)),
        }
        if payload["compile"] and result["valid"] and len(records) != 1:
            raise TaskError("JSONL 批量校验不能直接编译单个 CARLA 配置，请提交单条 JSON 记录")
        if payload["compile"] and result["valid"]:
            base_path = Path(payload.get("base_config_path") or (PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"))
            compiled = compile_carla_config(records[0][1], load_json(base_path))
            output = self._task_output_dir(task) / "compiled_carla_config.json"
            _write_json(output, compiled)
            result["compiled_config_path"] = str(output)
        report_path = self._task_output_dir(task) / "validation_result.json"
        _write_json(report_path, result)
        artifacts = [
            _artifact(
                report_path,
                artifact_type="validation_report",
                role="quality_evidence",
                source_task_id=task["task_id"],
            )
        ]
        if result.get("compiled_config_path"):
            artifacts.append(
                _artifact(
                    result["compiled_config_path"],
                    artifact_type="carla_config",
                    role="compiled_execution_input",
                    source_task_id=task["task_id"],
                )
            )
        result["result_path"] = str(report_path)
        result["_artifacts"] = artifacts
        return result

    def _run_risk_analysis(self, task):
        from core.risk_metrics import evaluate_telemetry_risk

        payload = task["payload"]
        metadata = {}
        config = {}
        run_dir = Path(payload["run_dir"]) if payload.get("run_dir") else None
        if run_dir:
            payload.setdefault("telemetry_path", str(run_dir / "telemetry.csv"))
            payload.setdefault("metadata_path", str(run_dir / "metadata.json"))
        if payload.get("metadata_path"):
            metadata = _load_json(payload["metadata_path"])
        if not payload.get("config_path") and metadata.get("source_config"):
            candidate = Path(metadata["source_config"])
            if candidate.is_file():
                payload["config_path"] = str(candidate)
        if payload.get("config_path"):
            config = _load_json(payload["config_path"])
        if payload.get("telemetry_rows"):
            rows = payload["telemetry_rows"]
        else:
            telemetry_path = Path(payload.get("telemetry_path", ""))
            if not telemetry_path.is_file():
                raise TaskError(f"缺少 telemetry.csv: {telemetry_path}")
            with telemetry_path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
        risk_config = payload.get("risk_config") or config.get("risk_evaluation") or {"method": "heuristic_v2"}
        collision_count = payload.get("collision_count")
        if collision_count is None:
            collision_count = (metadata.get("result") or {}).get("collision_count", 0)
        risk = evaluate_telemetry_risk(
            rows,
            int(collision_count),
            risk_config,
            weather_config=config.get("weather"),
            pedestrian_config=config.get("pedestrian"),
            scenario_config=config.get("scenario"),
            events=metadata.get("events", []),
        )
        output_dir = self._task_output_dir(task)
        output = output_dir / "risk_result.json"
        _write_json(output, {"observed_risk": risk, "source_row_count": len(rows)})
        from core.web_visualization import build_run_visualization

        visualization = build_run_visualization(output_dir, run_dir, rows, risk)
        artifacts = [
            _artifact(
                output,
                artifact_type="risk_report",
                role="risk_evidence",
                source_task_id=task["task_id"],
            )
        ]
        chart_path = output_dir / visualization["chart_name"]
        artifacts.append(
            _artifact(
                chart_path,
                artifact_type="svg_visualization",
                role="trajectory_and_risk_chart",
                source_task_id=task["task_id"],
            )
        )
        preview_name = visualization.get("sensor_preview_name")
        if preview_name:
            artifacts.append(
                _artifact(
                    output_dir / preview_name,
                    artifact_type="sensor_preview",
                    role="first_sensor_frame_preview",
                    source_task_id=task["task_id"],
                )
            )
        return {
            "kind": "risk_analysis",
            "execution_mode": "offline_cpu",
            "observed_risk": risk,
            "source_row_count": len(rows),
            "collision_count": int(collision_count),
            "output_path": str(output),
            "visualization": visualization,
            "_artifacts": artifacts,
        }
