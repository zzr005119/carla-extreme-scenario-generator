@echo off
setlocal
call "%~dp0server_run.cmd" -Name feedback-candidates-v1 -CommandFile "%~dp0server_jobs\feedback_candidate_scoring_v1.sh" -Wait
exit /b %ERRORLEVEL%
