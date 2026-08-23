"""Run the static preflight checks for the stage-five V1.0 freeze."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"D:\ANACONDA\envs\Carla666-0916\python.exe")
CARLA_ROOT = Path(r"F:\Carla\carla-0.9.16")
MANIFEST = PROJECT_ROOT / "artifacts" / "stage5_minimal_demo_v1" / "demo_manifest.json"
INDEX = PROJECT_ROOT / "docs" / "stage5_material_index_v1.md"
QUALITY_GATE = PROJECT_ROOT / "configs" / "scenario_library_quality_gate_v1.json"


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state():
    result = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip()


def _check_python_api():
    if not PYTHON.is_file():
        return False, f"missing {PYTHON}"
    result = subprocess.run(
        [str(PYTHON), "-c", "import carla; print('carla_api_imported')"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1]
        return False, detail
    return True, result.stdout.strip()


def _result(results, name, passed, detail):
    status = "PASS" if passed else "FAIL"
    results.append((status, name, detail))


def run_checks(require_clean=False):
    results = []
    required_docs = [
        "docs/stage5_material_index_v1.md",
        "docs/stage5_freeze_preflight_v1.md",
        "docs/stage5_minimal_demo_and_interface_catalog_v1.md",
        "docs/stage5_user_operation_guide_v1.md",
        "docs/software_copyright_material_ledger_v1.md",
        "docs/software_copyright_module_mapping_v1.md",
        "docs/software_copyright_interface_spec_v1.md",
        "docs/stage4_quality_gate_and_experiment_closure_v1.md",
        "tools/stage5_demo.cmd",
        "tools/stage5_minimal_demo.py",
        "tools/check_stage5_freeze.cmd",
        "tools/check_stage5_freeze.py",
        "configs/scenario_library_quality_gate_v1.json",
    ]
    for relative in required_docs:
        path = PROJECT_ROOT / relative
        _result(results, f"file:{relative}", path.is_file(), "present" if path.is_file() else "missing")

    project_text = (PROJECT_ROOT / "PROJECT.md").read_text(encoding="utf-8")
    mapping_text = (PROJECT_ROOT / "docs" / "software_copyright_module_mapping_v1.md").read_text(encoding="utf-8")
    interface_text = (PROJECT_ROOT / "docs" / "software_copyright_interface_spec_v1.md").read_text(encoding="utf-8")
    _result(
        results,
        "software_name_and_version",
        "基于CARLA的自动驾驶极端场景生成与仿真测试系统 V1.0" in project_text
        and "基于 CARLA 的自动驾驶极端场景生成与仿真测试系统 V1.0" in mapping_text,
        "V1.0 name present",
    )
    _result(
        results,
        "module_and_interface_scope",
        all(token in mapping_text and token in interface_text for token in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08")),
        "M01-M08 present",
    )
    _result(
        results,
        "no_stale_current_status",
        "M01–M07 离线组合" not in mapping_text
        and "- 阶段三已完成收口并进入阶段四；" not in project_text.splitlines(),
        "current documents use M01-M08 and stage-five wording",
    )

    if MANIFEST.is_file():
        manifest = _load_json(MANIFEST)
        quality_gate = _load_json(QUALITY_GATE)
        expected = quality_gate["expected_library"]
        stages = manifest.get("stages", {})
        m03 = stages.get("M03_library_query", {})
        m05 = stages.get("M05_risk_evidence", {})
        m07 = stages.get("M07_dashboard_data", {})
        expected_statuses = {
            "M02_validation_and_compile": "passed",
            "M04_static_simulation_adapter": "passed",
            "M07_dashboard_data": "passed",
            "M08_demo_orchestrator": "passed",
        }
        _result(results, "manifest_format", manifest.get("format") == "stage5_minimal_demo_v1_manifest", str(manifest.get("format")))
        _result(results, "manifest_mode", manifest.get("execution_mode") == "offline_static_and_evidence", str(manifest.get("execution_mode")))
        _result(results, "manifest_carla_boundary", manifest.get("carla_connected") is False and m05.get("new_carla_risk_evaluation") is False, "offline and no new risk")
        for stage, expected_status in expected_statuses.items():
            _result(results, f"manifest:{stage}", stages.get(stage, {}).get("status") == expected_status, str(stages.get(stage, {}).get("status")))
        _result(results, "library_counts", m03.get("entry_count") == expected["entry_count"] and m07.get("row_count") == expected["entry_count"] and m07.get("entry_count") == expected["entry_count"] and m07.get("summary_entry_count") == expected["entry_count"], f"entries={m03.get('entry_count')} rows={m07.get('row_count')}")
        _result(results, "accepted_run_count", m07.get("accepted_run_evidence_count") == expected["accepted_run_evidence_count"], str(m07.get("accepted_run_evidence_count")))
        output_paths = manifest.get("outputs", {})
        missing_outputs = [name for name, value in output_paths.items() if not Path(value).is_file()]
        _result(results, "manifest_outputs", not missing_outputs, "all outputs present" if not missing_outputs else ", ".join(missing_outputs))
        actual_hash = _sha256(MANIFEST)
        index_text = INDEX.read_text(encoding="utf-8")
        match = re.search(r"当前清单 SHA-256 \| `([0-9a-f]{64})`", index_text)
        _result(results, "manifest_hash", bool(match) and match.group(1) == actual_hash, actual_hash)
    else:
        _result(results, "manifest", False, f"missing {MANIFEST}")

    _result(results, "python_environment", PYTHON.is_file(), str(PYTHON))
    _result(results, "carla_runtime_path", CARLA_ROOT.is_dir(), str(CARLA_ROOT))
    api_ok, api_detail = _check_python_api()
    _result(results, "carla_python_api", api_ok, api_detail)

    git_state = _git_state()
    dirty = bool(git_state and "\n" in git_state)
    if require_clean:
        _result(results, "git_clean", not dirty, git_state or "clean")
    else:
        print(f"[INFO] git_state={git_state or 'clean'}")

    pending = [
        "正式 V1.0 冻结提交尚未指定",
        "最终申请截图尚未从冻结提交重新采集",
        "申请主体、著作权人和开发完成日期尚未确认",
    ]
    return results, pending


def main():
    parser = argparse.ArgumentParser(description="阶段五 V1.0 冻结前静态检查")
    parser.add_argument("--require-clean", action="store_true", help="要求 Git 工作区干净")
    args = parser.parse_args()
    results, pending = run_checks(require_clean=args.require_clean)
    for status, name, detail in results:
        print(f"[{status}] {name}: {detail}")
    failures = [item for item in results if item[0] == "FAIL"]
    print(f"[SUMMARY] pass={len(results) - len(failures)} fail={len(failures)} pending={len(pending)}")
    for item in pending:
        print(f"[PENDING] {item}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
