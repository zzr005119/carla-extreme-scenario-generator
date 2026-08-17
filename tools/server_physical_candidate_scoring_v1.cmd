@echo off
setlocal
call "%~dp0server_run.cmd" -Name physical-candidate-scoring-v1 -CommandFile "%~dp0server_jobs\physical_candidate_scoring_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
