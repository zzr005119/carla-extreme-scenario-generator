@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "%~dp0run_part_13.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_14.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_15.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

echo [DONE] Generator comparison group 05 completed.
exit /b 0
