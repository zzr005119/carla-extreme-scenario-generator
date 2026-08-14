@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

echo [RERUN] lhs_critical_20260813_0101__tm_20260821__generator_compare_v1
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "D:\Xx\竞赛\大创实施ing\data\scenarios\generator_comparison_v1\configs\lhs_critical_20260813_0101__tm_20260821__generator_compare_v1.json"
if errorlevel 1 goto :failed

echo [DONE] Failed run rerun completed. Now run collect_results.cmd.
exit /b 0

:failed
echo [FAILED] Rerun failed.
exit /b 1
