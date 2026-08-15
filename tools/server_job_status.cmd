@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_job_status.ps1" %*
exit /b %ERRORLEVEL%
