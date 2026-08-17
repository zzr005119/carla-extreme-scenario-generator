@echo off
setlocal
call "%~dp0server_run.cmd" -Name physical-feature-validation-plan-v1 -CommandFile "%~dp0server_jobs\physical_feature_validation_plan_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
