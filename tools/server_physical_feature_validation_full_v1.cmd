@echo off
setlocal
call "%~dp0server_run.cmd" -Name physical-feature-validation-full-v1 -CommandFile "%~dp0server_jobs\physical_feature_validation_full_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
