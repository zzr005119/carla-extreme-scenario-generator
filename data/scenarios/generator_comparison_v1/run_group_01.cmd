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

echo [DONE] Generator comparison group 01 completed.
exit /b 0
