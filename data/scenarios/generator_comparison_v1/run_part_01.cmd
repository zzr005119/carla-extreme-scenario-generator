@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

echo [RUN 1/4] gmm_high_20260813_0079__tm_20260821__generator_compare_v1
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\gmm_high_20260813_0079__tm_20260821__generator_compare_v1.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 2/4] cvae_low_20260813_0001__tm_20260823__generator_compare_v1
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_low_20260813_0001__tm_20260823__generator_compare_v1.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 3/4] cvae_critical_20260813_0046__tm_20260823__generator_compare_v1
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\cvae_critical_20260813_0046__tm_20260823__generator_compare_v1.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [RUN 4/4] lhs_medium_20260813_0026__tm_20260822__generator_compare_v1
python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%~dp0configs\lhs_medium_20260813_0026__tm_20260822__generator_compare_v1.json"
if errorlevel 1 goto :failed
timeout /t 10 /nobreak >nul

echo [DONE] Generator comparison part completed.
exit /b 0

:failed
echo [FAILED] Stop after CARLA or Python error.
exit /b 1
