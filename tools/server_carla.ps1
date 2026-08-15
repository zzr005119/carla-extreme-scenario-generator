[CmdletBinding()]
param(
    [ValidateSet("Start", "Status", "Stop")]
    [string]$Action = "Status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "server_workflow_common.ps1")

$context = Get-ServerWorkflowContext
$runtime = $context.Config.runtime
$carlaRoot = [string]$runtime.carla_root
$outputRoot = [string]$runtime.output_root
$gpu = [int]$runtime.gpu
$gpuLock = [string]$runtime.gpu_lock
$rpcPort = [int]$runtime.carla_rpc_port
$session = [string]$runtime.carla_tmux_session
$logDirectory = "$outputRoot/server_runtime/carla"
$logPath = "$logDirectory/carla.log"

switch ($Action) {
    "Start" {
        $script = @"
set -euo pipefail
session='$session'
rpc_port='$rpcPort'
launcher='$carlaRoot/CarlaUE4.sh'
log_directory='$logDirectory'
log_path='$logPath'
gpu_lock='$gpuLock'

mkdir -p "`$log_directory"
if timeout 1 bash -c ">/dev/tcp/127.0.0.1/`$rpc_port" >/dev/null 2>&1; then
    echo "[CARLA] already listening on port `$rpc_port"
    exit 0
fi
if tmux has-session -t "`$session" 2>/dev/null; then
    tmux kill-session -t "`$session"
fi
tmux new-session -d -s "`$session" "exec flock -n -E 73 '$gpuLock' env CUDA_VISIBLE_DEVICES=$gpu DISPLAY= '$carlaRoot/CarlaUE4.sh' -RenderOffScreen -nosound -graphicsadapter=$gpu -carla-rpc-port=$rpcPort >> '$logPath' 2>&1"

for attempt in `$(seq 1 90); do
    if timeout 1 bash -c ">/dev/tcp/127.0.0.1/`$rpc_port" >/dev/null 2>&1; then
        echo "[CARLA] ready on port `$rpc_port"
        echo "[CARLA] log=$logPath"
        exit 0
    fi
    if ! tmux has-session -t "`$session" 2>/dev/null; then
        echo '[CARLA] tmux session exited before the RPC port became ready.' >&2
        tail -n 40 "`$log_path" >&2 || true
        exit 30
    fi
    sleep 2
done

echo '[CARLA] startup timeout.' >&2
tail -n 40 "`$log_path" >&2 || true
exit 31
"@
        Invoke-ServerScript -Context $context -Script $script
    }
    "Status" {
        $script = @"
set -euo pipefail
session='$session'
rpc_port='$rpcPort'
if tmux has-session -t "`$session" 2>/dev/null; then
    echo '[CARLA] tmux=running'
else
    echo '[CARLA] tmux=stopped'
fi
if timeout 1 bash -c ">/dev/tcp/127.0.0.1/`$rpc_port" >/dev/null 2>&1; then
    echo "[CARLA] rpc_port=`$rpc_port listening"
else
    echo "[CARLA] rpc_port=`$rpc_port closed"
fi
nvidia-smi -i $gpu --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null || true
if flock -n '$gpuLock' true; then
    echo '[CARLA] project_gpu_lock=free'
else
    echo '[CARLA] project_gpu_lock=held'
fi
echo '[CARLA] gpu=$gpu'
echo '[CARLA] log=$logPath'
"@
        Invoke-ServerScript -Context $context -Script $script
    }
    "Stop" {
        $script = @"
set -euo pipefail
session='$session'
rpc_port='$rpcPort'
if tmux has-session -t "`$session" 2>/dev/null; then
    tmux send-keys -t "`$session" C-c
    for attempt in `$(seq 1 15); do
        if ! tmux has-session -t "`$session" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if tmux has-session -t "`$session" 2>/dev/null; then
        tmux kill-session -t "`$session"
    fi
fi
for attempt in `$(seq 1 30); do
    if ! timeout 1 bash -c ">/dev/tcp/127.0.0.1/`$rpc_port" >/dev/null 2>&1; then
        echo '[CARLA] stopped'
        exit 0
    fi
    sleep 1
done
echo '[CARLA] RPC port is still open; an unmanaged CARLA process may exist.' >&2
exit 32
"@
        Invoke-ServerScript -Context $context -Script $script
    }
}
