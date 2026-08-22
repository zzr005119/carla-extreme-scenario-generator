@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-policy-carla-repeat-plan-v1 -CommandFile "%~dp0server_jobs\adversarial_policy_carla_repeat_plan_v1.sh" -Wait
exit /b %ERRORLEVEL%
