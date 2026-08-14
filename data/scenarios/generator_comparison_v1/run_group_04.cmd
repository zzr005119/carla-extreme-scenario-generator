@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "%~dp0run_part_10.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_11.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_12.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

echo [DONE] Generator comparison group 04 completed.
exit /b 0
