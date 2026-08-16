@echo off
setlocal
call "%~dp0server_run.cmd" -Name risk-feedback-v4 -CommandFile "%~dp0server_jobs\risk_feedback_v4.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
