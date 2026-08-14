@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

echo [RUN 1/3] cvae_high_20260813_0074__tm_20260823
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_high_20260813_0074__tm_20260823.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [RUN 2/3] cvae_low_20260813_0001__tm_20260821
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_low_20260813_0001__tm_20260821.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [RUN 3/3] cvae_medium_20260813_0103__tm_20260822
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_medium_20260813_0103__tm_20260822.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [DONE] Route regression batch completed.
exit /b 0

:failed
echo [FAILED] Stop after CARLA or Python error.
exit /b 1
