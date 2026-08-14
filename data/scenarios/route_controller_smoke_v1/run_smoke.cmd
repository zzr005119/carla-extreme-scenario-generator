@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0config.json"
if errorlevel 1 goto :failed

cd /d "%~dp0..\..\.."
python tools\collect_carla_repeatability.py --manifest "%~dp0manifest.json"
if errorlevel 1 goto :failed

echo [DONE] Route controller smoke regression passed.
exit /b 0

:failed
echo [FAILED] Route controller smoke regression failed.
exit /b 1
