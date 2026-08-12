"""多传感器异步写盘与完整性统计。"""

import queue
import threading
import time


class SensorWritePipeline:
    """用有界队列和后台线程保存传感器数据。"""

    _STOP = object()

    def __init__(self, queue_size=16, workers_per_sensor=2):
        if int(queue_size) <= 0:
            raise ValueError("queue_size 必须大于 0")
        if int(workers_per_sensor) <= 0:
            raise ValueError("workers_per_sensor 必须大于 0")
        self.queue_size = int(queue_size)
        self.workers_per_sensor = int(workers_per_sensor)
        self._condition = threading.Condition()
        self._sensors = {}
        self._closed = False

    def register(self, sensor_name, writer):
        with self._condition:
            if self._closed:
                raise RuntimeError("传感器写盘管线已关闭")
            if sensor_name in self._sensors:
                raise ValueError(f"传感器已注册: {sensor_name}")
            sensor_queue = queue.Queue(maxsize=self.queue_size)
            state = {
                "queue": sensor_queue,
                "writer": writer,
                "received": 0,
                "saved": 0,
                "failed": 0,
                "errors": [],
                "threads": [],
            }
            self._sensors[sensor_name] = state

        for worker_index in range(self.workers_per_sensor):
            thread = threading.Thread(
                target=self._worker,
                args=(sensor_name,),
                name=f"sensor-writer-{sensor_name}-{worker_index + 1}",
                daemon=True,
            )
            state["threads"].append(thread)
            thread.start()

    def _worker(self, sensor_name):
        state = self._sensors[sensor_name]
        sensor_queue = state["queue"]
        while True:
            data = sensor_queue.get()
            try:
                if data is self._STOP:
                    return
                state["writer"](data)
            except Exception as error:
                frame_id = getattr(data, "frame", None)
                with self._condition:
                    state["failed"] += 1
                    if len(state["errors"]) < 10:
                        state["errors"].append(
                            {
                                "frame": frame_id,
                                "error": f"{type(error).__name__}: {error}",
                            }
                        )
                    self._condition.notify_all()
            else:
                with self._condition:
                    state["saved"] += 1
                    self._condition.notify_all()
            finally:
                sensor_queue.task_done()

    def submit(self, sensor_name, data):
        with self._condition:
            if self._closed:
                raise RuntimeError("传感器写盘管线已关闭")
            state = self._sensors[sensor_name]
            state["received"] += 1
            self._condition.notify_all()
        state["queue"].put(data)

    def wait_for_received(self, expected_counts, timeout_seconds):
        deadline = time.monotonic() + float(timeout_seconds)
        with self._condition:
            while any(
                self._sensors[name]["received"] < expected
                for name, expected in expected_counts.items()
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
        return True

    def _wait_for_processed(self, timeout_seconds):
        deadline = time.monotonic() + float(timeout_seconds)
        with self._condition:
            while any(
                state["saved"] + state["failed"] < state["received"]
                for state in self._sensors.values()
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
        return True

    def close(self, timeout_seconds):
        drained = self._wait_for_processed(timeout_seconds)
        with self._condition:
            self._closed = True
        if not drained:
            return False

        for state in self._sensors.values():
            for _ in state["threads"]:
                state["queue"].put(self._STOP)
        for state in self._sensors.values():
            for thread in state["threads"]:
                thread.join(timeout=5.0)
        return True

    def snapshot(self, expected_counts=None):
        expected_counts = expected_counts or {}
        with self._condition:
            sensors = {}
            for sensor_name, state in self._sensors.items():
                expected = expected_counts.get(sensor_name)
                pending = max(
                    0,
                    state["received"] - state["saved"] - state["failed"],
                )
                complete = (
                    state["failed"] == 0
                    and pending == 0
                    and (expected is None or state["saved"] >= expected)
                )
                sensors[sensor_name] = {
                    "expected": expected,
                    "received": state["received"],
                    "saved": state["saved"],
                    "failed": state["failed"],
                    "pending": pending,
                    "complete": complete,
                    "errors": list(state["errors"]),
                }

        if any(item["failed"] > 0 for item in sensors.values()):
            status = "failed"
        elif sensors and all(item["complete"] for item in sensors.values()):
            status = "completed"
        elif sensors:
            status = "incomplete"
        else:
            status = "not_started"
        return {
            "status": status,
            "queue_size": self.queue_size,
            "workers_per_sensor": self.workers_per_sensor,
            "sensors": sensors,
        }
