@echo off
setlocal
call "%~dp0server_run.cmd" -Name multisensor-smoke-v1 -CommandFile "%~dp0server_jobs\multisensor_smoke_v1.sh" -RequiresCarla -Resource Cpu -Wait
exit /b %ERRORLEVEL%
