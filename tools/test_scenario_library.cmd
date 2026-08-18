@echo off
set "PYTHONUTF8=1"
cd /d "%~dp0.."
python -m unittest discover -s tests -v
exit /b %ERRORLEVEL%
