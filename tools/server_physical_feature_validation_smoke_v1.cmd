@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name physical-feature-validation-smoke-v1 -CommandFile "%~dp0server_jobs\physical_feature_validation_smoke_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
