$projectRoot = Split-Path -Parent $PSScriptRoot
Get-Content "$projectRoot\.env" | ForEach-Object {
  if ($_ -match "^(.*?)=(.*)$" -and $_ -notlike "#*") {
    Set-Item -Path "env:$($matches[1])" -Value $matches[2]
  }
}

Set-Location $PSScriptRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Invest Ranking - Execucao de Scripts" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$scripts = @(
    @{Name="B3_COTACOES_AOVIVO"; File="atualizar_b3_cotacoes_aovivo.py"},
    @{Name="00_FUNDOS_MASTER"; File="atualizar_00_fundos_master.py"},
    @{Name="FNET_DADOS"; File="atualizar_fnet_dados.py"},
    @{Name="CVM_FII_MENSAL"; File="atualizar_cvm_fii_mensal.py"},
    @{Name="CVM_FIAGRO_MENSAL"; File="atualizar_cvm_fiagro_mensal.py"},
    @{Name="CVM_CADASTRAL"; File="atualizar_cvm_cadastral.py"},
    @{Name="YOUTUBE_VIDEOS"; File="atualizar_youtube_videos.py"}
)

$results = @{}
$globalExitCode = 0

foreach ($s in $scripts) {
    $name = $s.Name
    $file = $s.File
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] Executando $name..." -ForegroundColor Yellow
    $tempFile = Join-Path $env:TEMP "$($name)_run.txt"
    & "$PSScriptRoot\.venv\Scripts\python.exe" $file 2>&1 | Tee-Object -FilePath $tempFile
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { $globalExitCode = 1 }

    $rawResult = ""
    if (Test-Path $tempFile) {
        $rawResult = Get-Content $tempFile | Select-String "^RESULT:" | Select-Object -Last 1
    }
    if ($rawResult) {
        $status = $rawResult.ToString().Replace("RESULT:", "")
        $results[$name] = $status
    } elseif ($exitCode -eq 0) {
        $results[$name] = "OK(0)"
    } else {
        $results[$name] = "ERRO($exitCode)"
    }
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] $name processado." -ForegroundColor Green
    Write-Host ""
}

$logLine = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $($results.Values -join ' | ')"
Add-Content -Path "$PSScriptRoot\log.txt" -Value $logLine

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Log registrado em scripts\log.txt" -ForegroundColor Cyan
Write-Host ""

Get-ChildItem "$env:TEMP\*_run.txt" | Remove-Item -Force

Write-Host ""
Write-Host "Para baixar cotacoes B3 historicas, execute manualmente:" -ForegroundColor Yellow
Write-Host "  .\.venv\Scripts\python atualizar_b3_cotahist.py" -ForegroundColor Cyan
Write-Host "(requer resolucao manual de captcha no navegador)" -ForegroundColor Yellow
Write-Host ""

if ($globalExitCode -eq 0) {
    Write-Host "Concluido com sucesso!" -ForegroundColor Green
} else {
    Write-Host "Erro na execucao!" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
}
