@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_run.ps1" %*
exit /b %ERRORLEVEL%
