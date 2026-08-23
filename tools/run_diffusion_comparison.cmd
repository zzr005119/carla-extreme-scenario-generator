@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0.."
set "PROJECT_PYTHON=D:\ANACONDA\envs\Carla666-0916\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" tools\run_diffusion_comparison.py %*
exit /b %ERRORLEVEL%
