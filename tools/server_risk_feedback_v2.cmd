@echo off
setlocal
call "%~dp0server_run.cmd" -Name risk-feedback-v2 -CommandFile "%~dp0server_jobs\risk_feedback_v2.sh" -Wait
exit /b %ERRORLEVEL%
