@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

echo [RUN 1/4] cvae_critical_20260813_0058__tm_20260822__route_v4
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_critical_20260813_0058__tm_20260822__route_v4.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 2/4] cvae_high_20260813_0033__tm_20260821__route_v4
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_high_20260813_0033__tm_20260821__route_v4.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 3/4] cvae_medium_20260813_0103__tm_20260823__route_v4
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_medium_20260813_0103__tm_20260823__route_v4.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 4/4] cvae_low_20260813_0122__tm_20260822__route_v4
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_low_20260813_0122__tm_20260822__route_v4.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [DONE] Route regression batch completed.
exit /b 0

:failed
echo [FAILED] Stop after CARLA or Python error.
exit /b 1
