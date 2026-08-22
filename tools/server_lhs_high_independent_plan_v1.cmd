@echo off
setlocal
call "%~dp0server_run.cmd" -Name lhs-high-independent-plan-v1 -CommandFile "%~dp0server_jobs\lhs_high_independent_plan_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
