@echo off
setlocal
call "%~dp0server_run.cmd" -Name lhs-high-independent-smoke-v1 -CommandFile "%~dp0server_jobs\lhs_high_independent_smoke_v1.sh" -RequiresCarla -Wait
exit /b %ERRORLEVEL%
