@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-baseline-carla-full-v1 -CommandFile "%~dp0server_jobs\adversarial_baseline_carla_full_v1.sh" -RequiresCarla -Resource Cpu -Wait
exit /b %ERRORLEVEL%
