@echo off
setlocal
call "%~dp0server_run.cmd" -Name adversarial-loop-multistep-v1 -CommandFile "%~dp0server_jobs\adversarial_loop_multistep_v1.sh" -RequiresCarla -Resource Cpu -Wait
exit /b %ERRORLEVEL%
