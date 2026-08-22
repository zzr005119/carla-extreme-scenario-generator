@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-policy-carla-expand-full-v1 -CommandFile "%~dp0server_jobs\adversarial_policy_carla_expand_full_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
