@echo off
setlocal
call "%~dp0server_carla.cmd" -Action Start
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0server_run.cmd" -Name carla-rl-05-evaluate-test-v1 -CommandFile "%~dp0server_jobs\carla_rl_05_evaluate_test_v1.sh" -RequiresCarla
exit /b %ERRORLEVEL%
