@echo off
setlocal
call "%~dp0server_run.cmd" -Name carla-rl-multiscene-v1 -Command "bash tools/server_jobs/carla_rl_multiscene_v1.sh train" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
