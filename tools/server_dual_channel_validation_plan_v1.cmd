@echo off
setlocal
call "%~dp0server_run.cmd" -Name dual-channel-validation-plan-v1 -CommandFile "%~dp0server_jobs\dual_channel_validation_plan_v1.sh" -Wait
exit /b %ERRORLEVEL%
