@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_01.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_02.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_03.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_04.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_05.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

call "D:\Xx\竞赛\大创实施ing\data\scenarios\cvae_repeatability_v1\run_part_06.cmd"
if errorlevel 1 exit /b 1
timeout /t 10 /nobreak >nul

echo [DONE] All repeatability batches completed.
exit /b 0
