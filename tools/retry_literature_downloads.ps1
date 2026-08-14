param(
    [int]$Bucket = 0,
    [int]$Buckets = 1
)

$ErrorActionPreference = 'Continue'
$base = Resolve-Path '.\literature_generative_ai_autonomous_driving'
$pdfDir = Join-Path $base 'pdf'
$csvPath = @(Get-ChildItem -LiteralPath $base -File -Filter '*.csv' | Select-Object -First 1 -ExpandProperty FullName)
if (-not $csvPath) { throw 'No CSV index found under literature directory.' }
$rows = @(Import-Csv -LiteralPath $csvPath | Where-Object { $_.status -eq 'link-only' })
$selected = @()
for ($i = 0; $i -lt $rows.Count; $i++) {
    if (($i % $Buckets) -eq $Bucket) { $selected += $rows[$i] }
}

$ok = 0
$failed = 0
foreach ($p in $selected) {
    $safe = ($p.title -replace '[^A-Za-z0-9]+','_').Trim('_')
    if ($safe.Length -gt 90) { $safe = $safe.Substring(0,90).Trim('_') }
    $file = Join-Path $pdfDir (('{0}_{1}_{2}.pdf' -f $p.year,$p.id,$safe))
    if (Test-Path -LiteralPath $file) {
        Write-Output ("EXISTS`t$($p.id)`t$([IO.Path]::GetFileName($file))")
        continue
    }
    $tmp = "$file.part"
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    $args = @(
        '-L', '--fail', '--silent', '--show-error', '--retry', '2', '--retry-delay', '2',
        '--connect-timeout', '20', '--max-time', '150', '-A', 'Mozilla/5.0 CodexLiteratureCollector/1.0',
        '-o', $tmp, $p.pdf_url
    )
    & curl.exe @args 2>&1 | ForEach-Object { Write-Output ("CURL`t$($p.id)`t$_") }
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $tmp)) {
        $head = [IO.File]::ReadAllBytes($tmp)
        if ($head.Length -ge 4 -and [Text.Encoding]::ASCII.GetString($head,0,4) -eq '%PDF') {
            Move-Item -LiteralPath $tmp -Destination $file -Force
            $ok++
            Write-Output ("OK`t$($p.id)`t$([IO.Path]::GetFileName($file))")
            continue
        }
    }
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    $failed++
    Write-Output ("FAILED`t$($p.id)`t$($p.pdf_url)")
}
Write-Output ("SUMMARY`tBucket=$Bucket/$Buckets`tSelected=$($selected.Count)`tNew=$ok`tFailed=$failed")
