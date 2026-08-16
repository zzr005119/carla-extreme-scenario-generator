@echo off
setlocal
call "%~dp0server_run.cmd" -Name dual-candidate-scoring-v2 -CommandFile "%~dp0server_jobs\dual_candidate_scoring_v2.sh" -Wait
exit /b %ERRORLEVEL%
