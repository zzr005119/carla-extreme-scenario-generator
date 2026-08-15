@echo off
setlocal
call "%~dp0server_run.cmd" -Name collision-proxy-v1 -CommandFile "%~dp0server_jobs\collision_proxy_v1.sh" -Wait
exit /b %ERRORLEVEL%
