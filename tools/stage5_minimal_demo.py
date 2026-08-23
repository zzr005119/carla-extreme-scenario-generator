"""运行阶段五离线最小演示链路。

默认链路不连接 CARLA，只验证生成记录、配置编译、OpenSCENARIO 最小适配、
场景库查询和 Dashboard 数据加载，并写出可审计的演示清单。
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORD = PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "example_record.json"
DEFAULT_LIBRARY = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
DEFAULT_BASE_CONFIG = PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "stage5_minimal_demo_v1"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scenario_validator import compile_carla_config, load_json, require_valid_scenario  # noqa: E402
from tools.convert_scenario_to_openscenario import (  # noqa: E402
    _write_xml,
    convert_record,
    load_mapping,
)
from tools.query_scenario_library import flatten_entry, load_entries, sort_entries  # noqa: E402
from tools.scenario_dashboard import load_dashboard_data  # noqa: E402


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_or_absolute(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _static_scene_validation(config_path, output_root):
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scenes" / "scene_04_parameterized.py"),
        "--config",
        str(config_path),
        "--validate-only",
        "--output-root",
        str(output_root),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Scene 04 静态校验失败\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return {
        "status": "passed",
        "command": [str(item) for item in command],
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _library_snapshot(library_path):
    entries = load_entries(str(library_path))
    collision_entries = [
        entry for entry in entries if entry["observed_risk"]["collision_observed"]
    ]
    top_collision = sort_entries(collision_entries, "risk_desc")[:5]
    return {
        "entry_count": len(entries),
        "collision_entry_count": len(collision_entries),
        "top_collision_scenarios": [flatten_entry(entry) for entry in top_collision],
    }


def run_demo(record_path=DEFAULT_RECORD, library_path=DEFAULT_LIBRARY, base_config_path=DEFAULT_BASE_CONFIG, output_dir=DEFAULT_OUTPUT):
    """执行离线最小链路并返回机器可读清单。"""
    record_path = Path(record_path).resolve()
    library_path = Path(library_path).resolve()
    base_config_path = Path(base_config_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for required_path in (record_path, library_path, base_config_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"演示输入不存在: {required_path}")

    record = load_json(record_path)
    validation = require_valid_scenario(record)
    base_config = load_json(base_config_path)
    compiled = compile_carla_config(record, base_config)
    compiled["output"] = dict(compiled["output"])
    compiled["output"]["root"] = str(output_dir / "carla_runs")

    record_copy_path = output_dir / "input_record.json"
    compiled_path = output_dir / "compiled_carla_config.json"
    _write_json(record_copy_path, record)
    _write_json(compiled_path, compiled)
    static_validation = _static_scene_validation(compiled_path, output_dir / "carla_runs")

    mapping_path, mapping = load_mapping()
    xosc_root, adapted_config, adapter_manifest = convert_record(
        record,
        mapping,
        base_config,
        str(base_config_path),
    )
    adapted_config["output"] = dict(adapted_config["output"])
    adapted_config["output"]["root"] = str(output_dir / "carla_runs")
    xosc_path = output_dir / f"{record['sample_id']}.xosc"
    adapted_config_path = output_dir / f"{record['sample_id']}.carla.json"
    adapter_manifest_path = output_dir / f"{record['sample_id']}.adapter_manifest.json"
    _write_xml(str(xosc_path), xosc_root)
    _write_json(adapted_config_path, adapted_config)
    adapter_manifest.update(
        {
            "mapping_path": _relative_or_absolute(mapping_path),
            "xosc_path": str(xosc_path),
            "carla_config_path": str(adapted_config_path),
            "demo_execution_status": "static_only",
        }
    )
    _write_json(adapter_manifest_path, adapter_manifest)
    ET.parse(xosc_path)

    library_snapshot = _library_snapshot(library_path)
    dashboard_data = load_dashboard_data(library_path.parent)
    dashboard_snapshot = {
        "row_count": len(dashboard_data["rows"]),
        "entry_count": len(dashboard_data["entries"]),
        "summary_entry_count": dashboard_data["summary"]["entry_count"],
        "accepted_run_evidence_count": dashboard_data["summary"]["accepted_run_evidence_count"],
        "quality_summary_loaded": bool(dashboard_data["quality_summary"]),
    }
    if dashboard_snapshot["row_count"] != library_snapshot["entry_count"]:
        raise ValueError("场景库查询和 Dashboard 行数不一致")

    manifest = {
        "format": "stage5_minimal_demo_v1_manifest",
        "demo_version": "v1",
        "carla_connected": False,
        "execution_mode": "offline_static_and_evidence",
        "input": {
            "record": _relative_or_absolute(record_path),
            "library": _relative_or_absolute(library_path),
            "base_config": _relative_or_absolute(base_config_path),
        },
        "sample_id": record["sample_id"],
        "stages": {
            "M01_generation_record": {"status": "loaded", "source_kind": record["provenance"]["source_kind"]},
            "M02_validation_and_compile": {
                "status": "passed",
                "schema_valid": validation["valid"],
                "warnings": validation["warnings"],
            },
            "M03_library_query": {"status": "passed", **library_snapshot},
            "M04_static_simulation_adapter": {
                "status": "passed",
                "scene_config_validation": static_validation,
                "xosc_parse": "passed",
            },
            "M05_risk_evidence": {
                "status": "historical_evidence_loaded",
                "source": "scenario_library_v1.summary_and_entries",
                "new_carla_risk_evaluation": False,
            },
            "M06_reproducibility_manifest": {"status": "written"},
            "M07_dashboard_data": {"status": "passed", **dashboard_snapshot},
            "M08_demo_orchestrator": {"status": "passed"},
        },
        "outputs": {
            "input_record": str(record_copy_path),
            "compiled_carla_config": str(compiled_path),
            "openscenario": str(xosc_path),
            "adapted_carla_config": str(adapted_config_path),
            "adapter_manifest": str(adapter_manifest_path),
            "demo_manifest": str(output_dir / "demo_manifest.json"),
        },
        "limitations": [
            "默认模式不连接 CARLA，不产生新的 observed_risk。",
            "M05 读取场景库已有实测汇总，不把代理分或 target_risk_level 当作实测风险。",
            "OpenSCENARIO 产物属于最小交换子集，未证明 ScenarioRunner 直执行。",
            "场景库真实性仍为 not_assessed。",
        ],
    }
    manifest_path = output_dir / "demo_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description="阶段五离线一键最小演示链路")
    parser.add_argument("--record", default=str(DEFAULT_RECORD))
    parser.add_argument("--library", default=str(DEFAULT_LIBRARY))
    parser.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = run_demo(args.record, args.library, args.base_config, args.output_dir)
    print(f"[DEMO] mode={manifest['execution_mode']} carla_connected={manifest['carla_connected']}")
    print(f"[DEMO] sample_id={manifest['sample_id']}")
    print(f"[DEMO] output={Path(args.output_dir).resolve()}")
    print("[DEMO] M01-M08 离线最小链路通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
