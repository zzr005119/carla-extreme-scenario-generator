"""运行对抗性测试代理 V1 的单 episode 闭环。"""

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    AdversarialTestAgentV1,
    load_agent_config,
)
from core.adversarial_loop import (  # noqa: E402
    AdversarialEpisodeRunner,
    FixedActionStrategy,
)
from core.scenario_features import load_jsonl  # noqa: E402
from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    load_json,
    require_valid_scenario,
    validate_schema_value,
)
from tools.collect_carla_repeatability import collect_row  # noqa: E402


DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_loop_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_loop_v1.schema.json",
)
DEFAULT_RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)
SCENE_RUNNER = os.path.join(
    PROJECT_ROOT,
    "scenes",
    "scene_04_parameterized.py",
)


def _project_path(path):
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(PROJECT_ROOT, path))


def _safe_name(value):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")
    if not name:
        raise ValueError("名称不能为空")
    return name


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_loop_config(path=DEFAULT_CONFIG_PATH):
    config = load_json(os.path.abspath(path))
    schema = load_json(DEFAULT_SCHEMA_PATH)
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    if len(config["fixed_action"]) != 15:
        raise ValueError("fixed_action 必须为 15 维")
    for index, value in enumerate(config["fixed_action"]):
        if not -1.0 <= float(value) <= 1.0:
            raise ValueError(f"fixed_action[{index}] 必须位于 [-1, 1]")
    for field in (
        "agent_config_path",
        "base_carla_config_path",
        "route_profile_path",
    ):
        resolved = _project_path(config[field])
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"找不到 {field}: {resolved}")
    return config


def load_record(path, sample_id=None):
    path = os.path.abspath(path)
    if path.lower().endswith(".jsonl"):
        records = load_jsonl(path)
        if sample_id is None:
            if len(records) != 1:
                raise ValueError("JSONL 含多条记录时必须提供 --sample-id")
            record = records[0]
        else:
            matches = [record for record in records if record["sample_id"] == sample_id]
            if len(matches) != 1:
                raise ValueError(f"--sample-id 匹配数量应为 1，实际为 {len(matches)}")
            record = matches[0]
    else:
        record = load_json(path)
        if sample_id is not None and record.get("sample_id") != sample_id:
            raise ValueError("JSON 记录的 sample_id 与 --sample-id 不一致")
    require_valid_scenario(record)
    return record


def apply_route_profile(config, profile):
    configured = copy.deepcopy(config)
    sensor = profile["sensor_profile"]
    configured["sensors"]["camera"].update(
        {
            "width": int(sensor["width"]),
            "height": int(sensor["height"]),
            "sensor_tick": float(sensor["sensor_tick"]),
            "writer_workers": int(sensor["writer_workers"]),
            "writer_queue_size": int(sensor["writer_queue_size"]),
        }
    )
    configured["sensors"]["rgb"]["enabled"] = bool(sensor["rgb_enabled"])
    configured["sensors"]["depth"]["enabled"] = bool(sensor["depth_enabled"])
    configured["sensors"]["semantic"]["enabled"] = bool(
        sensor["semantic_enabled"]
    )
    configured["traffic"].update(copy.deepcopy(profile["route"]))
    configured["traffic"]["route_controller"] = copy.deepcopy(
        profile["controller"]
    )
    return configured


def build_carla_config(
    record,
    base_config,
    route_profile,
    scenario_name,
    runtime_output_root,
    traffic_manager_port,
):
    config = compile_carla_config(record, base_config)
    config = apply_route_profile(config, route_profile)
    config["scenario"]["name"] = _safe_name(scenario_name)
    config["scenario"]["traffic_manager_port"] = int(traffic_manager_port)
    config["output"]["root"] = os.path.abspath(runtime_output_root)
    return config


def validate_carla_config(config_path, timeout_seconds=60):
    result = subprocess.run(
        [sys.executable, SCENE_RUNNER, "--config", config_path, "--validate-only"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


class MockSceneExecutor:
    """只用于离线接口回归，不构成 CARLA 运行证据。"""

    def __init__(self, artifact_dir):
        self.artifact_dir = artifact_dir

    def __call__(self, record, phase, step_index):
        score = 40.0 if phase == "baseline" else 55.0
        level = "medium" if score < 50.0 else "high"
        result = {
            "status": "completed",
            "observed_risk_score": score,
            "observed_risk_level": level,
            "risk_method": "heuristic_v2",
            "collision_count": 0,
            "event_count": 2,
            "run_valid": True,
            "strict_acceptance_passed": True,
            "carla_service_healthy": True,
            "run_dir": f"mock://{phase}/{step_index}",
            "failure_reason": None,
        }
        _write_json(
            os.path.join(self.artifact_dir, f"mock_{phase}_{step_index}.json"),
            {"record": record, "result": result, "evidence_kind": "mock"},
        )
        return result


class CarlaSceneExecutor:
    def __init__(
        self,
        artifact_dir,
        runtime_output_root,
        base_config,
        route_profile,
        acceptance_requirements,
        traffic_manager_port,
        timeout_seconds,
        episode_id,
    ):
        self.artifact_dir = artifact_dir
        self.runtime_output_root = runtime_output_root
        self.base_config = base_config
        self.route_profile = route_profile
        self.acceptance_requirements = acceptance_requirements
        self.traffic_manager_port = int(traffic_manager_port)
        self.timeout_seconds = int(timeout_seconds)
        self.episode_id = _safe_name(episode_id)

    def __call__(self, record, phase, step_index):
        phase_index = 0 if phase == "baseline" else int(step_index) + 1
        scenario_name = f"{self.episode_id}_{phase}_{phase_index:02d}"
        step_dir = os.path.join(
            self.artifact_dir,
            "steps",
            f"{phase_index:02d}_{phase}",
        )
        os.makedirs(step_dir, exist_ok=False)
        record_path = os.path.join(step_dir, "scenario_record.json")
        config_path = os.path.join(step_dir, "carla_config.json")
        log_path = os.path.join(step_dir, "scene.log")
        _write_json(record_path, record)
        config = build_carla_config(
            record,
            self.base_config,
            self.route_profile,
            scenario_name,
            self.runtime_output_root,
            self.traffic_manager_port,
        )
        _write_json(config_path, config)
        validate_output = validate_carla_config(config_path)
        with open(os.path.join(step_dir, "validate.log"), "w", encoding="utf-8") as file:
            file.write(validate_output)

        environment = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.Popen(
            [sys.executable, "-u", SCENE_RUNNER, "--config", config_path],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
        timed_out = False
        run_dir = None
        try:
            output, _ = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            timed_out = True
            output += f"[LOOP] scene timeout after {self.timeout_seconds} seconds\n"
        output_lines = output.splitlines(keepends=True)
        for line in output_lines:
            print(f"[{phase.upper()}] {line}", end="")
            if line.startswith("[OUTPUT]") and ": " in line:
                run_dir = line.strip().split(": ", 1)[1]
        with open(log_path, "w", encoding="utf-8") as file:
            file.writelines(output_lines)

        if not run_dir:
            result = {
                "status": "failed",
                "observed_risk_score": None,
                "observed_risk_level": None,
                "risk_method": None,
                "collision_count": 0,
                "event_count": 0,
                "run_valid": False,
                "strict_acceptance_passed": False,
                "carla_service_healthy": False,
                "run_dir": None,
                "failure_reason": (
                    "scene_timeout_without_output"
                    if timed_out
                    else f"scene_exit_{process.returncode}_without_output"
                ),
            }
            _write_json(os.path.join(step_dir, "execution_result.json"), result)
            return result

        run = {
            "run_id": scenario_name,
            "sample_id": record["sample_id"],
            "target_risk_level": record["conditions"]["target_risk_level"],
            "traffic_manager_seed": record["scenario"]["traffic_manager_seed"],
            "repeat_round": phase_index + 1,
            "source": "adversarial_loop_v1",
            "expected_run_root": os.path.join(
                os.path.abspath(self.runtime_output_root),
                scenario_name,
            ),
        }
        row = collect_row(
            run,
            route_lock_required=True,
            acceptance_requirements=self.acceptance_requirements,
        )
        metadata = {}
        metadata_path = row.get("metadata_path")
        if metadata_path and os.path.isfile(metadata_path):
            metadata = load_json(metadata_path)
        risk = (metadata.get("result") or {}).get("risk_evaluation") or {}
        strict_passed = (
            process.returncode == 0
            and row.get("acceptance_status") == "completed"
        )
        failures = [value for value in (row.get("acceptance_failures") or "").split(";") if value]
        if process.returncode != 0:
            failures.append(f"scene_exit_{process.returncode}")
        if timed_out:
            failures.append("scene_timeout")
        result = {
            "status": "completed" if row.get("status") == "completed" else "failed",
            "observed_risk_score": row.get("risk_score"),
            "observed_risk_level": row.get("observed_risk_level"),
            "risk_method": risk.get("method"),
            "collision_count": int(row.get("collision_count") or 0),
            "event_count": len(metadata.get("events") or []),
            "run_valid": bool(row.get("runtime_verified")),
            "strict_acceptance_passed": strict_passed,
            "carla_service_healthy": row.get("server_status") == "healthy",
            "run_dir": row.get("run_dir"),
            "failure_reason": ";".join(failures) or None,
        }
        _write_json(
            os.path.join(step_dir, "execution_result.json"),
            {
                "result": result,
                "acceptance": row,
                "metadata_path": metadata_path,
                "process_returncode": process.returncode,
                "evidence_kind": "carla_runtime",
            },
        )
        return result


def _default_output_root(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    return os.path.join(root, config["runtime"]["output_subdirectory"])


def _create_episode_dir(output_root, sample_id):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    episode_id = _safe_name(f"{sample_id}_{timestamp}")
    episode_dir = os.path.join(output_root, "episodes", episode_id)
    os.makedirs(episode_dir, exist_ok=False)
    return episode_id, episode_dir


def prepare_validation(
    record,
    config,
    episode_id,
    episode_dir,
    runtime_output_root,
    base_config,
    route_profile,
    traffic_manager_port,
):
    agent = AdversarialTestAgentV1(
        load_agent_config(_project_path(config["agent_config_path"]))
    )
    initial_observation = agent.reset(record)
    proposal = agent.propose(config["fixed_action"])
    if not proposal["valid"]:
        raise ValueError(proposal["error"])
    prepared = []
    for phase, phase_record, phase_index in (
        ("baseline", record, 0),
        ("candidate", proposal["candidate"], 1),
    ):
        step_dir = os.path.join(episode_dir, "steps", f"{phase_index:02d}_{phase}")
        os.makedirs(step_dir, exist_ok=False)
        scenario_name = f"{episode_id}_{phase}_{phase_index:02d}"
        scenario_path = os.path.join(step_dir, "scenario_record.json")
        config_path = os.path.join(step_dir, "carla_config.json")
        _write_json(scenario_path, phase_record)
        carla_config = build_carla_config(
            phase_record,
            base_config,
            route_profile,
            scenario_name,
            runtime_output_root,
            traffic_manager_port,
        )
        _write_json(config_path, carla_config)
        validate_output = validate_carla_config(config_path)
        with open(os.path.join(step_dir, "validate.log"), "w", encoding="utf-8") as file:
            file.write(validate_output)
        prepared.append(
            {
                "phase": phase,
                "sample_id": phase_record["sample_id"],
                "scenario_record": scenario_path,
                "carla_config": config_path,
                "validation_status": "completed",
            }
        )
    summary = {
        "format": "adversarial_episode_validation_v1",
        "mode": "validate",
        "evidence_kind": "static_validation",
        "episode_id": episode_id,
        "initial_observation": initial_observation,
        "fixed_action": config["fixed_action"],
        "proposal": proposal,
        "prepared_runs": prepared,
        "status": "completed",
    }
    _write_json(os.path.join(episode_dir, "episode_summary.json"), summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="运行对抗性代理 V1 单 episode 闭环")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--record", default=DEFAULT_RECORD_PATH)
    parser.add_argument("--sample-id")
    parser.add_argument("--mode", choices=("validate", "mock", "carla"), default="validate")
    parser.add_argument("--output-root")
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_loop_config(args.config)
    record = load_record(args.record, args.sample_id)
    output_root = os.path.abspath(args.output_root or _default_output_root(config))
    episode_id, episode_dir = _create_episode_dir(output_root, record["sample_id"])
    runtime_output_root = os.path.abspath(
        args.runtime_output_root
        or os.path.join(output_root, "runtime", episode_id)
    )
    traffic_manager_port = (
        args.traffic_manager_port
        or int(os.environ.get("CARLA_TRAFFIC_MANAGER_PORT", 0))
        or int(config["runtime"]["traffic_manager_port"])
    )
    base_config = load_json(_project_path(config["base_carla_config_path"]))
    route_profile = load_json(_project_path(config["route_profile_path"]))

    if args.mode == "validate":
        summary = prepare_validation(
            record,
            config,
            episode_id,
            episode_dir,
            runtime_output_root,
            base_config,
            route_profile,
            traffic_manager_port,
        )
        print(f"[LOOP] 静态校验完成: {os.path.join(episode_dir, 'episode_summary.json')}")
        print(f"[RESULT_DIR] {episode_dir}")
        return 0 if summary["status"] == "completed" else 1

    agent = AdversarialTestAgentV1(
        load_agent_config(_project_path(config["agent_config_path"]))
    )
    strategy = FixedActionStrategy(tuple(config["fixed_action"]))
    if args.mode == "mock":
        executor = MockSceneExecutor(episode_dir)
        evidence_kind = "mock"
    else:
        executor = CarlaSceneExecutor(
            episode_dir,
            runtime_output_root,
            base_config,
            route_profile,
            config["acceptance_requirements"],
            traffic_manager_port,
            config["runtime"]["scene_timeout_seconds"],
            episode_id,
        )
        evidence_kind = "carla_runtime"

    summary_path = os.path.join(episode_dir, "episode_summary.json")

    def persist(execution):
        execution.update(
            {
                "format": "adversarial_episode_v1",
                "mode": args.mode,
                "evidence_kind": evidence_kind,
                "episode_id": episode_id,
                "fixed_action": config["fixed_action"],
                "runtime_output_root": runtime_output_root,
            }
        )
        _write_json(summary_path, execution)

    runner = AdversarialEpisodeRunner(
        agent,
        strategy,
        executor,
        max_agent_steps=config["max_agent_steps"],
    )
    execution = runner.run(record, on_update=persist)
    print(f"[LOOP] episode_status={execution.status}")
    print(f"[LOOP] summary={summary_path}")
    print(f"[RESULT_DIR] {episode_dir}")
    return 0 if execution.status in {"completed", "truncated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
