@echo off
setlocal
call "%~dp0server_run.cmd" -Name collision-boundary-multisensor-collect-v1 -CommandFile "%~dp0server_jobs\collision_boundary_multisensor_collect_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
