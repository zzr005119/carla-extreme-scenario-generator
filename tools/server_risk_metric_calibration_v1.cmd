@echo off
setlocal
call "%~dp0server_run.cmd" -Name risk-metric-calibration-v1 -CommandFile "%~dp0server_jobs\risk_metric_calibration_v1.sh" -Resource Cpu -Wait
exit /b %ERRORLEVEL%
