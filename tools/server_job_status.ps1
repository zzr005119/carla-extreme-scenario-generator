[CmdletBinding()]
param(
    [string]$JobId,

    [ValidateRange(1, 500)]
    [int]$Tail = 40,

    [switch]$Summary
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "server_workflow_common.ps1")

$context = Get-ServerWorkflowContext
$outputRoot = [string]$context.Config.runtime.output_root

if ($JobId) {
    if ($JobId -notmatch "^[A-Za-z0-9._-]+$") {
        throw "Invalid job id."
    }
    if ($Summary) {
        $script = @"
set -euo pipefail
job_directory='$outputRoot/remote_jobs/$JobId'
test -d "`$job_directory"
echo 'JOB_ID=$JobId'
echo -n 'COMMIT='; cat "`$job_directory/commit.txt" 2>/dev/null || echo unknown
echo -n 'STARTED='; cat "`$job_directory/started_at.txt" 2>/dev/null || echo pending
echo -n 'FINISHED='; cat "`$job_directory/finished_at.txt" 2>/dev/null || echo pending
if [ -f "`$job_directory/exit_code.txt" ]; then
    echo -n 'STATE=completed EXIT_CODE='; cat "`$job_directory/exit_code.txt"
else
    session="`$(cat "`$job_directory/tmux_session.txt" 2>/dev/null || true)"
    if [ -n "`$session" ] && tmux has-session -t "`$session" 2>/dev/null; then
        echo 'STATE=running'
    else
        echo 'STATE=unknown'
    fi
fi
progress="`$(grep -E 'total_timesteps' "`$job_directory/run.log" 2>/dev/null | tail -n 1 || true)"
if [ -n "`$progress" ]; then
    echo "PROGRESS=`$progress"
else
    echo 'PROGRESS=unknown'
fi
"@
    }
    else {
        $script = @"
set -euo pipefail
job_directory='$outputRoot/remote_jobs/$JobId'
test -d "`$job_directory"
echo '[JOB] id=$JobId'
echo -n '[JOB] commit='; cat "`$job_directory/commit.txt" 2>/dev/null || echo unknown
echo -n '[JOB] started='; cat "`$job_directory/started_at.txt" 2>/dev/null || echo pending
echo -n '[JOB] finished='; cat "`$job_directory/finished_at.txt" 2>/dev/null || echo pending
if [ -f "`$job_directory/exit_code.txt" ]; then
    echo -n '[JOB] exit_code='; cat "`$job_directory/exit_code.txt"
else
    session="`$(cat "`$job_directory/tmux_session.txt" 2>/dev/null || true)"
    if [ -n "`$session" ] && tmux has-session -t "`$session" 2>/dev/null; then
        echo '[JOB] state=running'
    else
        echo '[JOB] state=unknown'
    fi
fi
echo '[JOB] log_tail:'
tail -n $Tail "`$job_directory/run.log" 2>/dev/null || true
"@
    }
}
else {
    $script = @"
set -euo pipefail
root='$outputRoot/remote_jobs'
if [ ! -d "`$root" ]; then
    echo '[JOB] no jobs found'
    exit 0
fi
find "`$root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r | head -n 20
"@
}

Invoke-ServerScript -Context $context -Script $script
