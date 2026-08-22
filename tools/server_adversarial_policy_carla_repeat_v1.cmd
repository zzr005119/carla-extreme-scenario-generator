@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-policy-carla-repeat-v1 -CommandFile "%~dp0server_jobs\adversarial_policy_carla_repeat_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
