@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name collision-boundary-multisensor-v1 -CommandFile "%~dp0server_jobs\collision_boundary_multisensor_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
