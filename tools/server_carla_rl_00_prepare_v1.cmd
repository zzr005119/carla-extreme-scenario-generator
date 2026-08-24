@echo off
setlocal
call "%~dp0server_run.cmd" -Name carla-rl-00-prepare-v1 -CommandFile "%~dp0server_jobs\carla_rl_00_prepare_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
