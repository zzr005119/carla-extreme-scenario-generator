@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul

for %%F in ("%~dp0configs\*.json") do (
  python -u "F:\Carla\test\scenes\scene_04_parameterized.py" --config "%%~fF" --validate-only
  if errorlevel 1 exit /b 1
)
echo [DONE] All generated configs passed validate-only.
exit /b 0
