Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ServerWorkflowContext {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $configPath = Join-Path $projectRoot "configs\server_workflow.json"
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "Missing workflow config: $configPath"
    }

    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $identityFile = [Environment]::ExpandEnvironmentVariables(
        [string]$config.ssh.identity_file
    )
    if (-not (Test-Path -LiteralPath $identityFile -PathType Leaf)) {
        throw "Missing SSH identity file: $identityFile"
    }

    [pscustomobject]@{
        ProjectRoot = $projectRoot
        ConfigPath = $configPath
        Config = $config
        IdentityFile = $identityFile
        Target = "{0}@{1}" -f $config.ssh.user, $config.ssh.host
    }
}

function Invoke-ServerScript {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Script,

        [switch]$CaptureOutput
    )

    $normalized = $Script.Replace("`r`n", "`n")
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($normalized)
    )
    $remoteCommand = "printf '%s' '$encoded' | base64 --decode | bash"
    $arguments = @(
        "-i", $Context.IdentityFile,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        $Context.Target,
        $remoteCommand
    )

    if ($CaptureOutput) {
        $output = & ssh @arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Remote command failed with exit code $LASTEXITCODE`n$($output -join "`n")"
        }
        return $output
    }

    & ssh @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Get-LocalGitValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git failed with exit code $LASTEXITCODE`n$($output -join "`n")"
    }
    return ($output -join "`n").Trim()
}
