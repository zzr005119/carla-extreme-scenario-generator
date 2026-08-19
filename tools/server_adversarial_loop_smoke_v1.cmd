@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-loop-smoke-v1 -CommandFile "%~dp0server_jobs\adversarial_loop_smoke_v1.sh" -RequiresCarla -Resource Cpu -Wait
exit /b %ERRORLEVEL%
