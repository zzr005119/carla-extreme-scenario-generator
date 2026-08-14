@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "F:\Carla\test"

echo [RUN 1/4] cvae_low_20260813_0004
python -u "D:\Xx\竞赛\大创实施ing\scenes\scene_04_parameterized.py" --config "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v1\configs\cvae_low_20260813_0004.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [RUN 2/4] cvae_medium_20260813_0033
python -u "D:\Xx\竞赛\大创实施ing\scenes\scene_04_parameterized.py" --config "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v1\configs\cvae_medium_20260813_0033.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [RUN 3/4] cvae_high_20260813_0107
python -u "D:\Xx\竞赛\大创实施ing\scenes\scene_04_parameterized.py" --config "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v1\configs\cvae_high_20260813_0107.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [RUN 4/4] cvae_critical_20260813_0114
python -u "D:\Xx\竞赛\大创实施ing\scenes\scene_04_parameterized.py" --config "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_validation_v1\configs\cvae_critical_20260813_0114.json"
if errorlevel 1 goto :failed
timeout /t 5 /nobreak >nul

echo [DONE] CARLA sample validation completed.
exit /b 0

:failed
echo [FAILED] Stop after CARLA or Python error.
exit /b 1
