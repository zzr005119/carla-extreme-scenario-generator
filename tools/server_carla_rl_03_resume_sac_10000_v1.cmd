@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-03-resume-sac-10000-v1 -CommandFile "%~dp0server_jobs\carla_rl_03_resume_sac_10000_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
