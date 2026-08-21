@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-baseline-carla-smoke-v1 -CommandFile "%~dp0server_jobs\adversarial_baseline_carla_smoke_v1.sh" -RequiresCarla -Resource Cpu -Wait
exit /b %ERRORLEVEL%
