@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-01-canary-sac-256-v1 -CommandFile "%~dp0server_jobs\carla_rl_01_canary_sac_256_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
