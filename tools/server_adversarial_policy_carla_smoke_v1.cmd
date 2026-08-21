@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-policy-carla-smoke-v1 -CommandFile "%~dp0server_jobs\adversarial_policy_carla_smoke_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
