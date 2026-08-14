$ErrorActionPreference = 'Continue'
$base = Resolve-Path '.\literature_generative_ai_autonomous_driving'
$pdfDir = Join-Path $base 'pdf'
$csvPath = Get-ChildItem -LiteralPath $base -File -Filter '*.csv' | Select-Object -First 1 -ExpandProperty FullName
$rows = @(Import-Csv -LiteralPath $csvPath | Where-Object { $_.status -eq 'link-only' })
$new = 0
$failed = 0
foreach ($p in $rows) {
    if ($p.id -eq 'DiffScene') { continue }
    $safe = ($p.title -replace '[^A-Za-z0-9]+','_').Trim('_')
    if ($safe.Length -gt 90) { $safe = $safe.Substring(0,90).Trim('_') }
    $file = Join-Path $pdfDir (('{0}_{1}_{2}.pdf' -f $p.year,$p.id,$safe))
    $tmp = "$file.part"
    $urls = @(
        ('https://export.arxiv.org/pdf/' + $p.id),
        ('https://arxiv.org/pdf/' + $p.id + '.pdf')
    )
    $got = $false
    foreach ($url in $urls) {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        Write-Output ("TRY`t$($p.id)`t$url")
        $args = @('-L','--fail','--silent','--show-error','--retry','1','--retry-delay','3','--connect-timeout','20','--max-time','120','-A','Mozilla/5.0 CodexLiteratureCollector/1.0','-o',$tmp,$url)
        & curl.exe @args 2>&1 | ForEach-Object { Write-Output ("CURL`t$($p.id)`t$_") }
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $tmp)) {
            $head = [IO.File]::ReadAllBytes($tmp)
            if ($head.Length -ge 4 -and [Text.Encoding]::ASCII.GetString($head,0,4) -eq '%PDF') {
                Move-Item -LiteralPath $tmp -Destination $file -Force
                Write-Output ("OK`t$($p.id)`t$([IO.Path]::GetFileName($file))")
                $new++
                $got = $true
                break
            }
        }
        Start-Sleep -Seconds 3
    }
    if (-not $got) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue; Write-Output ("FAILED`t$($p.id)"); $failed++ }
    Start-Sleep -Seconds 3
}
Write-Output ("SUMMARY`tNew=$new`tFailed=$failed")
