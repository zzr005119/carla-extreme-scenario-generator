@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-p3-1-04-evaluate-blind -Command "bash tools/server_jobs/carla_rl_p3_1_blind_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
