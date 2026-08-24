@echo off
setlocal EnableExtensions

set "PYTHON=D:\ANACONDA\envs\Carla666-0916\python.exe"
set "OUT=F:\Carla\project-transfer\stage5_metrics_p1_20260824"
set "GEN=%OUT%\generation"
set "ROOT=F:\Carla\project-transfer\server-results\20260820_215156_20260820_215411\runtime"
set "BASE=%ROOT%\cvae_medium_20260813_0103_gym_20260820_215156_baseline_00\20260820_215157\metadata.json"
set "CAND1=%ROOT%\cvae_medium_20260813_0103_gym_20260820_215156_candidate_01\20260820_215216\metadata.json"
set "CAND2=%ROOT%\cvae_medium_20260813_0103_gym_20260820_215156_candidate_02\20260820_215233\metadata.json"

if not exist "%PYTHON%" (
  echo [STAGE5-BASELINE] missing Python: %PYTHON%
  exit /b 2
)
if not exist "%BASE%" (
  echo [STAGE5-BASELINE] missing CARLA baseline metadata: %BASE%
  exit /b 3
)
if not exist "%CAND1%" (
  echo [STAGE5-BASELINE] missing CARLA candidate metadata: %CAND1%
  exit /b 3
)
if not exist "%CAND2%" (
  echo [STAGE5-BASELINE] missing CARLA candidate metadata: %CAND2%
  exit /b 3
)

"%PYTHON%" tools\benchmark_stage5_generation_baseline.py --output-dir "%GEN%" --count-per-level 512 --repeats 5 --seed 20260824
if errorlevel 1 exit /b %errorlevel%

"%PYTHON%" tools\measure_stage5_metrics.py ^
  --generation-summary "%GEN%\system_lhs_summary.json" ^
  --baseline-generation-summary "%GEN%\baseline_uniform_rule_summary.json" ^
  --metadata "%CAND1%" --metadata "%CAND2%" ^
  --baseline-metadata "%BASE%" ^
  --reference "data\scenarios\seed_v1\scenarios.jsonl" ^
  --candidate "%GEN%\system_lhs.jsonl" ^
  --baseline-candidate "%GEN%\baseline_fixed_template.jsonl" ^
  --output "%OUT%\metrics_report_full.json"
exit /b %errorlevel%
