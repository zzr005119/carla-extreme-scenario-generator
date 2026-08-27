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
$knownUserChange = "data/scenarios/seed_v1/example_record.json"

Push-Location $context.ProjectRoot
try {
    $status = Get-LocalGitValue -Arguments @("status", "--porcelain")
    if ($status) {
        $statusLines = @(
            $status -split "`n" | Where-Object { $_.Trim() }
        )
        $dirtyPaths = @(
            $statusLines | ForEach-Object {
                ($_ -replace "^[ MADRCU?!]{1,2}\s+", "").Trim()
            }
        )
        $onlyKnownUserChange = (
            $dirtyPaths.Count -eq 1 -and $dirtyPaths[0] -eq $knownUserChange
        )
        if (-not $onlyKnownUserChange) {
            if ($DryRun) {
                Write-Warning "Local repository has changes outside the permitted user-owned file; a real sync would stop."
                Write-Host $status
            }
            else {
                throw "Local repository is dirty outside the permitted user-owned file '$knownUserChange'. Commit or discard other changes before syncing.`n$status"
            }
        }
        else {
            Write-Warning "Leaving known user-owned change out of deployment: $knownUserChange"
        }
    }

    $commit = Get-LocalGitValue -Arguments @("rev-parse", "HEAD")
    $currentBranch = Get-LocalGitValue -Arguments @("branch", "--show-current")
    if ($currentBranch -ne $branch -and -not $currentBranch.StartsWith("codex/")) {
        throw "Expected local branch '$branch' or a codex/* worktree branch, found '$currentBranch'."
    }

    Write-Host "[SYNC] commit=$commit"
    Write-Host "[SYNC] source_branch=$currentBranch deploy_branch=$branch"
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
git reset --hard HEAD
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
