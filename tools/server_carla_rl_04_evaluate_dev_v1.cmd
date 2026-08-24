@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-04-evaluate-dev-v1 -CommandFile "%~dp0server_jobs\carla_rl_04_evaluate_dev_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
