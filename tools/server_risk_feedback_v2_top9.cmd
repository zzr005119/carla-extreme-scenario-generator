@echo off
setlocal
call "%~dp0server_run.cmd" -Name risk-feedback-v2-top9 -CommandFile "%~dp0server_jobs\risk_feedback_v2_top9.sh" -Wait
exit /b %ERRORLEVEL%
