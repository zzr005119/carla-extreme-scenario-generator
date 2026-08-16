@echo off
setlocal
call "%~dp0server_run.cmd" -Name dual-candidate-scoring-v3 -CommandFile "%~dp0server_jobs\dual_candidate_scoring_v3.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
