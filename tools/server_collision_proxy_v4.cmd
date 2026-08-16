@echo off
setlocal
call "%~dp0server_run.cmd" -Name collision-proxy-v4 -CommandFile "%~dp0server_jobs\collision_proxy_v4.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
