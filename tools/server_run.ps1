[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Inline")]
    [string]$Command,

    [Parameter(Mandatory = $true, ParameterSetName = "File")]
    [string]$CommandFile,

    [string]$Name = "job",

    [switch]$RequiresCarla,

    [switch]$SkipSync,

    [switch]$Wait,

    [ValidateSet("Gpu", "Cpu")]
    [string]$Resource = "Gpu",

    [ValidateRange(1, 300)]
    [int]$PollSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "server_workflow_common.ps1")

$context = Get-ServerWorkflowContext
$config = $context.Config
$runtime = $config.runtime
$projectDirectory = [string]$config.git.project_directory
$outputRoot = [string]$runtime.output_root
$pythonEnvironment = [string]$runtime.python_environment
$modelRoot = [string]$runtime.model_root
$gpu = [int]$runtime.gpu
$gpuLock = [string]$runtime.gpu_lock
$rpcPort = [int]$runtime.carla_rpc_port
$trafficManagerPort = [int]$runtime.traffic_manager_port

if (-not $SkipSync) {
    & (Join-Path $PSScriptRoot "server_sync.ps1")
}

Push-Location $context.ProjectRoot
try {
    $commit = Get-LocalGitValue -Arguments @("rev-parse", "HEAD")
}
finally {
    Pop-Location
}

$safeName = [regex]::Replace($Name, "[^A-Za-z0-9._-]", "-").Trim("-", ".")
if (-not $safeName) {
    throw "Job name must contain at least one ASCII letter, digit, dot, dash, or underscore."
}
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$jobId = "{0}_{1}" -f $safeName, $timestamp
$session = "job_{0}" -f $jobId
$jobDirectory = "$outputRoot/remote_jobs/$jobId"
$resourceMode = if ($RequiresCarla) {
    "carla"
}
elseif ($Resource -eq "Gpu") {
    "gpu"
}
else {
    "cpu"
}
$cudaVisibleDevices = if ($resourceMode -eq "cpu") { "" } else { [string]$gpu }

if ($PSCmdlet.ParameterSetName -eq "File") {
    $resolvedCommandFile = (Resolve-Path -LiteralPath $CommandFile).Path
    $commandText = Get-Content -LiteralPath $resolvedCommandFile -Raw -Encoding UTF8
}
else {
    $commandText = $Command
}
$normalizedCommand = $commandText.Replace("`r`n", "`n")
$commandBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($normalizedCommand)
)
$runner = @"
#!/usr/bin/env bash
set -o pipefail
job_directory='$jobDirectory'
resource_mode='$resourceMode'
gpu_lock='$gpuLock'
export CUDA_VISIBLE_DEVICES='$cudaVisibleDevices'
export PYTHONUTF8='1'
export PYTHONUNBUFFERED='1'
export PATH='$pythonEnvironment/bin':"`$PATH"
export CARLA_ROOT='$($runtime.carla_root)'
export PROJECT_MODEL_ROOT='$modelRoot'
export PROJECT_OUTPUT_ROOT='$outputRoot'
export CARLA_RPC_PORT='$rpcPort'
export CARLA_TRAFFIC_MANAGER_PORT='$trafficManagerPort'
cd '$projectDirectory'
date -u +%Y-%m-%dT%H:%M:%SZ > "`$job_directory/started_at.txt"
set +e
if [ "`$resource_mode" = 'gpu' ]; then
    exec 9>"`$gpu_lock"
    if ! flock -n 9; then
        echo '[JOB] Project GPU 1 lock is held by another project task.' > "`$job_directory/run.log"
        exit_code=73
    else
        bash "`$job_directory/command.sh" > "`$job_directory/run.log" 2>&1
        exit_code=`$?
    fi
else
    bash "`$job_directory/command.sh" > "`$job_directory/run.log" 2>&1
    exit_code=`$?
fi
set -e
printf '%s\n' "`$exit_code" > "`$job_directory/exit_code.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "`$job_directory/finished_at.txt"
exit "`$exit_code"
"@
$runner = $runner.Replace("`r`n", "`n")
$runnerBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($runner)
)
$requiresCarlaValue = if ($RequiresCarla) { "1" } else { "0" }

$startScript = @"
set -euo pipefail
project_directory='$projectDirectory'
job_directory='$jobDirectory'
session='$session'
expected_commit='$commit'
rpc_port='$rpcPort'
requires_carla='$requiresCarlaValue'

actual_commit="`$(git -C "`$project_directory" rev-parse HEAD)"
if [ "`$actual_commit" != "`$expected_commit" ]; then
    echo "[JOB] Server commit mismatch: expected `$expected_commit, got `$actual_commit" >&2
    exit 40
fi
if [ "`$requires_carla" = '1' ] && ! timeout 1 bash -c ">/dev/tcp/127.0.0.1/`$rpc_port" >/dev/null 2>&1; then
    echo "[JOB] CARLA is not listening on port `$rpc_port. Run tools/server_carla.cmd -Action Start first." >&2
    exit 41
fi
if tmux has-session -t '$session' 2>/dev/null; then
    echo '[JOB] tmux session already exists: $session' >&2
    exit 42
fi

mkdir -p "`$job_directory"
printf '%s' '$commandBase64' | base64 --decode > "`$job_directory/command.sh"
printf '%s' '$runnerBase64' | base64 --decode > "`$job_directory/runner.sh"
chmod 700 "`$job_directory/command.sh" "`$job_directory/runner.sh"
printf '%s\n' "`$expected_commit" > "`$job_directory/commit.txt"
printf '%s\n' '$session' > "`$job_directory/tmux_session.txt"
tmux new-session -d -s '$session' "bash '$jobDirectory/runner.sh'"
echo '[JOB] id=$jobId'
echo '[JOB] directory=$jobDirectory'
echo '[JOB] session=$session'
"@
Invoke-ServerScript -Context $context -Script $startScript

Write-Host "[JOB] status: .\tools\server_job_status.cmd -JobId $jobId"
Write-Host "[JOB] fetch:  .\tools\server_fetch_results.cmd -RemotePath $jobDirectory"

if ($Wait) {
    while ($true) {
        Start-Sleep -Seconds $PollSeconds
        $statusScript = @"
set -euo pipefail
job_directory='$jobDirectory'
session='$session'
if [ -f "`$job_directory/exit_code.txt" ]; then
    printf 'COMPLETED:'
    cat "`$job_directory/exit_code.txt"
elif tmux has-session -t "`$session" 2>/dev/null; then
    echo 'RUNNING'
else
    echo 'LOST'
fi
"@
        $status = ((Invoke-ServerScript -Context $context -Script $statusScript -CaptureOutput) -join "`n").Trim()
        if ($status -eq "RUNNING") {
            Write-Host "[JOB] running: $jobId"
            continue
        }
        if ($status -eq "LOST") {
            throw "Remote tmux session ended without an exit code: $jobId"
        }
        if ($status.StartsWith("COMPLETED:")) {
            $exitCode = [int]$status.Substring("COMPLETED:".Length).Trim()
            $tailScript = "tail -n 60 '$jobDirectory/run.log' 2>/dev/null || true"
            Invoke-ServerScript -Context $context -Script $tailScript
            if ($exitCode -ne 0) {
                throw "Remote job failed with exit code ${exitCode}: $jobId"
            }
            Write-Host "[JOB] completed: $jobId"
            break
        }
    }
}
