$ErrorActionPreference = 'Stop'
$url = 'https://ojs.aaai.org/index.php/AAAI/article/download/32951/35106'
$out = Join-Path (Resolve-Path '.\literature_generative_ai_autonomous_driving\pdf') '2025_DiffScene_Diffusion_Based_Safety_Critical_Scenario_Generation_for_Autonomous_Vehicles.pdf'
$tmp = "$out.part"
try {
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -TimeoutSec 180 -Headers @{ 'User-Agent' = 'Mozilla/5.0 CodexLiteratureCollector/1.0' }
    $bytes = [IO.File]::ReadAllBytes($tmp)
    if ($bytes.Length -lt 4 -or [Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne '%PDF') {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        Write-Output 'INVALID_PDF'
        exit 2
    }
    Move-Item -LiteralPath $tmp -Destination $out -Force
    Write-Output ('DOWNLOADED_BYTES=' + $bytes.Length)
} catch {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    Write-Output ('DOWNLOAD_ERROR=' + $_.Exception.Message)
    exit 1
}
