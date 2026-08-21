@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-sb3-smoke-v1 -CommandFile "%~dp0server_jobs\adversarial_sb3_smoke_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
