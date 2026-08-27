@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name recheck-failed-rl-samples-v1 -CommandFile "%~dp0server_jobs\recheck_failed_rl_samples_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
