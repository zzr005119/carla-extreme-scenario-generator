@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "MJX_PYTHON=%PROJECT_ROOT%\tmp\mjx_jax_env\Scripts\python.exe"
if not exist "%MJX_PYTHON%" (
  echo [MJX-PoC] blocked: missing tmp\mjx_jax_env; install requirements-mjx-poc.txt in an isolated env first.
  exit /b 2
)
cd /d "%PROJECT_ROOT%"
"%MJX_PYTHON%" tools\run_mjx_differentiable_poc.py %*
exit /b %errorlevel%
