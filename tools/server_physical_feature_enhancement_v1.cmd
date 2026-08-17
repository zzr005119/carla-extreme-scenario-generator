@echo off
setlocal
call "%~dp0server_run.cmd" -Name physical-feature-enhancement-v1 -CommandFile "%~dp0server_jobs\physical_feature_enhancement_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
