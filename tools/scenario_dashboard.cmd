@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
python tools\scenario_dashboard.py --open %*
exit /b %ERRORLEVEL%
