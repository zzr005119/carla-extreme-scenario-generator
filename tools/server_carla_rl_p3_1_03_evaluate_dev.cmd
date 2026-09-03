@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-p3-1-03-evaluate-dev -Command "bash tools/server_jobs/carla_rl_p3_1_v1.sh evaluate-dev" -RequiresCarla
exit /b %ERRORLEVEL%
