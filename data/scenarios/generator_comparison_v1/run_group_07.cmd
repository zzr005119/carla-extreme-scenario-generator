@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "%~dp0run_part_19.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_20.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

call "%~dp0run_part_21.cmd"
if errorlevel 1 exit /b 1
timeout /t 20 /nobreak >nul

echo [DONE] Generator comparison group 07 completed.
exit /b 0
