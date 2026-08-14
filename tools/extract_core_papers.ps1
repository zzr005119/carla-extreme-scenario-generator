$ErrorActionPreference = 'Stop'
$base = Resolve-Path '.\literature_generative_ai_autonomous_driving'
$pdfDir = Join-Path $base 'pdf'
$textDir = Join-Path $base 'text_extracts'
New-Item -ItemType Directory -Force -Path $textDir | Out-Null
$patterns = @(
    '2202.02215',
    '2210.06609',
    '2210.17366',
    '2312.13303',
    '2405.14062',
    '2501.15850',
    '2505.11247',
    'DiffScene',
    '1809.09310',
    '2602.20644',
    '2508.19882',
    '2101.06549'
)
foreach ($pattern in $patterns) {
    $pdf = Get-ChildItem -LiteralPath $pdfDir -File -Filter '*.pdf' |
        Where-Object { $_.Name -match [regex]::Escape($pattern) } |
        Select-Object -First 1
    if (-not $pdf) {
        Write-Output ("MISSING`t$pattern")
        continue
    }
    $textPath = Join-Path $textDir ($pdf.BaseName + '.txt')
    & pdftotext.exe -layout -enc UTF-8 $pdf.FullName $textPath
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $textPath)) {
        Write-Output ("OK`t$pattern`t$([IO.Path]::GetFileName($textPath))")
    } else {
        Write-Output ("FAILED`t$pattern")
    }
}
