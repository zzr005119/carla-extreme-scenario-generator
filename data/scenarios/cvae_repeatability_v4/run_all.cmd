@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "%~dp0run_part_01.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_02.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_03.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_04.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_05.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_06.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_07.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_08.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_09.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0collect_results.cmd"
if errorlevel 1 exit /b 1

echo [DONE] All route regression batches completed.
exit /b 0
