@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "%~dp0..\..\.."

python -u tools\collect_carla_generator_comparison.py --manifest "%~dp0manifest.json"
if errorlevel 1 goto :failed

echo [DONE] Generator comparison acceptance passed.
exit /b 0

:failed
echo [FAILED] Generator comparison acceptance failed.
exit /b 1
