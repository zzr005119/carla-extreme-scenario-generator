[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "server_workflow_common.ps1")

$context = Get-ServerWorkflowContext
$config = $context.Config
$remoteName = [string]$config.git.remote_name
$branch = [string]$config.git.branch
$bareRepository = [string]$config.git.bare_repository
$projectDirectory = [string]$config.git.project_directory
$remoteUrl = "{0}:{1}" -f $context.Target, $bareRepository

Push-Location $context.ProjectRoot
try {
    $status = Get-LocalGitValue -Arguments @("status", "--porcelain")
    if ($status) {
        if ($DryRun) {
            Write-Warning "Local repository is dirty; a real sync would stop until changes are committed."
            Write-Host $status
        }
        else {
            throw "Local repository is dirty. Commit or discard changes before syncing.`n$status"
        }
    }

    $commit = Get-LocalGitValue -Arguments @("rev-parse", "HEAD")
    $currentBranch = Get-LocalGitValue -Arguments @("branch", "--show-current")
    if ($currentBranch -ne $branch) {
        throw "Expected local branch '$branch', found '$currentBranch'."
    }

    Write-Host "[SYNC] commit=$commit"
    Write-Host "[SYNC] target=$($context.Target):$projectDirectory"
    if ($DryRun) {
        Write-Host "[SYNC] dry-run completed; no remote changes were made."
        return
    }

    $initializeScript = @"
set -euo pipefail
bare_repository='$bareRepository'
mkdir -p "`$(dirname "`$bare_repository")"
if ! git --git-dir="`$bare_repository" rev-parse --is-bare-repository >/dev/null 2>&1; then
    git init --bare "`$bare_repository"
fi
"@
    Invoke-ServerScript -Context $context -Script $initializeScript

    $remoteNames = @((Get-LocalGitValue -Arguments @("remote")) -split "`n")
    if ($remoteNames -contains $remoteName) {
        Invoke-CheckedCommand -Command "git" -Arguments @(
            "remote", "set-url", $remoteName, $remoteUrl
        )
    }
    else {
        Invoke-CheckedCommand -Command "git" -Arguments @(
            "remote", "add", $remoteName, $remoteUrl
        )
    }

    $previousSshCommand = $env:GIT_SSH_COMMAND
    try {
        $env:GIT_SSH_COMMAND = "ssh -i `"$($context.IdentityFile)`" -o IdentitiesOnly=yes -o BatchMode=yes"
        Invoke-CheckedCommand -Command "git" -Arguments @(
            "push", $remoteName, "HEAD:refs/heads/$branch"
        )
    }
    finally {
        $env:GIT_SSH_COMMAND = $previousSshCommand
    }

    $deployScript = @"
set -euo pipefail
bare_repository='$bareRepository'
project_directory='$projectDirectory'
branch='$branch'
remote_name='$remoteName'

if [ ! -d "`$project_directory/.git" ]; then
    mkdir -p "`$(dirname "`$project_directory")"
    git clone "`$bare_repository" "`$project_directory"
fi

cd "`$project_directory"
git config core.autocrlf false
if [ -n "`$(git status --porcelain)" ]; then
    echo '[SYNC] Server working tree is dirty:' >&2
    git status --short >&2
    exit 20
fi

if git remote get-url "`$remote_name" >/dev/null 2>&1; then
    git remote set-url "`$remote_name" "`$bare_repository"
else
    git remote add "`$remote_name" "`$bare_repository"
fi

git fetch "`$remote_name" "`$branch"
git checkout "`$branch"
git merge --ff-only "`$remote_name/`$branch"
while IFS= read -r -d '' shell_script; do
    git cat-file blob "HEAD:`$shell_script" > "`$shell_script"
done < <(git ls-files -z -- '*.sh')
actual_commit="`$(git rev-parse HEAD)"
if [ "`$actual_commit" != '$commit' ]; then
    echo "[SYNC] Commit mismatch: expected $commit, got `$actual_commit" >&2
    exit 21
fi
echo "[SYNC] server_commit=`$actual_commit"
"@
    Invoke-ServerScript -Context $context -Script $deployScript
    Write-Host "[SYNC] completed. GitHub origin was not pushed."
}
finally {
    Pop-Location
}
