@echo off
setlocal
call "%~dp0server_run.cmd" -Name risk-feedback-v5 -CommandFile "%~dp0server_jobs\risk_feedback_v5.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
