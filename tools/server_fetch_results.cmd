@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_fetch_results.ps1" %*
exit /b %ERRORLEVEL%
