@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name feedback-validation-v1 -CommandFile "%~dp0server_jobs\feedback_candidate_validation_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
