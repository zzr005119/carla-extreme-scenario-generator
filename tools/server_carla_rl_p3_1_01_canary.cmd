@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-p3-1-01-canary -Command "bash tools/server_jobs/carla_rl_p3_1_v1.sh canary" -RequiresCarla
exit /b %ERRORLEVEL%
