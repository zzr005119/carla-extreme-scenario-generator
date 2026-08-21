[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RemotePath,

    [string]$Destination,

    [ValidateRange(1, 1024)]
    [int]$MaxFileSizeMB = 20,

    [switch]$IncludeSampleImages
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "server_workflow_common.ps1")

$context = Get-ServerWorkflowContext
$outputRoot = [string]$context.Config.runtime.output_root
$transferRoot = [Environment]::ExpandEnvironmentVariables(
    [string]$context.Config.local.transfer_root
)
$normalizedRemotePath = $RemotePath.TrimEnd("/")
if (-not $normalizedRemotePath.StartsWith("$outputRoot/")) {
    throw "RemotePath must be inside $outputRoot"
}
if ($normalizedRemotePath -notmatch "^/[A-Za-z0-9._/-]+$") {
    throw "RemotePath contains unsupported characters."
}

$leafName = Split-Path -Leaf $normalizedRemotePath
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $Destination) {
    $Destination = Join-Path $transferRoot "server-results\${leafName}_$timestamp"
}
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationPath) {
    throw "Destination already exists: $destinationPath"
}

$incomingDirectory = Join-Path $transferRoot "incoming"
New-Item -ItemType Directory -Path $incomingDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
$token = [Guid]::NewGuid().ToString("N")
$remoteArchive = "$outputRoot/.transfer/$token.tar.gz"
$localArchive = Join-Path $incomingDirectory "$token.tar.gz"
$includeImages = if ($IncludeSampleImages) { "1" } else { "0" }

$archiveScript = @"
set -euo pipefail
source_directory='$normalizedRemotePath'
archive_path='$remoteArchive'
include_images='$includeImages'
max_size_mb='$MaxFileSizeMB'
test -d "`$source_directory"
mkdir -p "`$(dirname "`$archive_path")"
cd "`$source_directory"
if [ "`$include_images" = '1' ]; then
    find . -type f -size -"`$max_size_mb"M \( -name '*.csv' -o -name '*.json' -o -name '*.jsonl' -o -name '*.md' -o -name '*.txt' -o -name '*.log' -o -name '*.yaml' -o -name '*.yml' -o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' \) -print0 |
        sort -z | tar --null -T - -czf "`$archive_path"
else
    find . -type f -size -"`$max_size_mb"M \( -name '*.csv' -o -name '*.json' -o -name '*.jsonl' -o -name '*.md' -o -name '*.txt' -o -name '*.log' -o -name '*.yaml' -o -name '*.yml' \) -print0 |
        sort -z | tar --null -T - -czf "`$archive_path"
fi
echo "[FETCH] archive=`$archive_path"
du -h "`$archive_path"
"@

try {
    Invoke-ServerScript -Context $context -Script $archiveScript
    $scpArguments = @(
        "-i", $context.IdentityFile,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "$($context.Target):$remoteArchive",
        $localArchive
    )
    Invoke-CheckedCommand -Command "scp" -Arguments $scpArguments
    Invoke-CheckedCommand -Command "tar" -Arguments @(
        "-xzf", $localArchive, "-C", $destinationPath
    )

    $manifest = [ordered]@{
        fetched_at = (Get-Date).ToString("o")
        remote_host = [string]$context.Config.ssh.host
        remote_path = $normalizedRemotePath
        max_file_size_mb = $MaxFileSizeMB
        included_sample_images = [bool]$IncludeSampleImages
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (
        Join-Path $destinationPath "fetch_manifest.json"
    ) -Encoding UTF8
    Write-Host "[FETCH] completed: $destinationPath"
}
finally {
    if (Test-Path -LiteralPath $localArchive) {
        Remove-Item -LiteralPath $localArchive -Force
    }
    $cleanupScript = "rm -f '$remoteArchive'"
    try {
        Invoke-ServerScript -Context $context -Script $cleanupScript
    }
    catch {
        Write-Warning "Could not remove remote temporary archive: $remoteArchive"
    }
}
