@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "%~dp0..\..\.."

python -u tools\collect_carla_repeatability.py --manifest "%~dp0manifest.json"
if errorlevel 1 goto :failed

echo [DONE] Strict repeatability acceptance passed.
exit /b 0

:failed
echo [FAILED] Strict repeatability acceptance failed.
exit /b 1
