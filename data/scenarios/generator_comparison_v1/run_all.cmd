@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

call "%~dp0run_group_01.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_02.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_03.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_04.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_05.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_06.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_07.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_08.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

call "%~dp0run_group_09.cmd"
if errorlevel 1 exit /b 1
timeout /t 30 /nobreak >nul

echo [DONE] All generator comparison groups completed.
exit /b 0
