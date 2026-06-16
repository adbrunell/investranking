$projectRoot = Split-Path -Parent $PSScriptRoot
Get-Content "$projectRoot\.env" | ForEach-Object {
  if ($_ -match "^(.*?)=(.*)$" -and $_ -notlike "#*") {
    Set-Item -Path "env:$($matches[1])" -Value $matches[2]
  }
}

Set-Location $PSScriptRoot

$stateFile = "$PSScriptRoot\.run_state.json"
$logFile = "$PSScriptRoot\log.txt"
$py = "$PSScriptRoot\.venv\Scripts\python.exe"
$apiKey = $env:SUPABASE_SERVICE_KEY
$supabaseUrl = $env:SUPABASE_URL

# Carrega estado (timestamps da ultima execucao de cada script)
$state = @{}
if (Test-Path $stateFile) {
  try { $state = Get-Content $stateFile | ConvertFrom-Json -AsHashtable } catch {}
}
$now = (Get-Date).ToUniversalTime()

function should-run($name, $intervalHours) {
  if (-not $state.ContainsKey($name)) { return $true }
  $last = [DateTime]$state[$name]
  $elapsed = ($now - $last).TotalHours
  return $elapsed -ge $intervalHours
}

function run-script($name, $file) {
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Executando $name..." -ForegroundColor Yellow
  $tempFile = Join-Path $env:TEMP "$($name)_run.txt"
  & $py $file 2>&1 | Tee-Object -FilePath $tempFile
  $ec = $LASTEXITCODE

  $rawResult = ""
  if (Test-Path $tempFile) {
    $rawResult = Get-Content $tempFile | Select-String "^RESULT:" | Select-Object -Last 1
  }
  if ($rawResult) {
    $status = $rawResult.ToString().Replace("RESULT:", "")
  } elseif ($ec -eq 0) {
    $status = "OK"
  } else {
    $status = "ERRO($ec)"
  }

  Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $name -> $status" -ForegroundColor Green
  return $status
}

function check-cotahist {
  # Verifica se b3_cotacoes_aovivo tem data mais recente que b3_cotacoes_historico
  try {
    $h = @{"apikey"=$apiKey; "Authorization"="Bearer $apiKey"}
    $r1 = Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/b3_cotacoes_aovivo?select=data_referencia&order=data_referencia.desc&limit=1" -Headers $h -TimeoutSec 10
    if (-not $r1 -or $r1.Count -eq 0) { return $false }
    $dataAovivo = $r1[0].data_referencia

    $r2 = Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/b3_cotacoes_historico?select=data&order=data.desc&limit=1" -Headers $h -TimeoutSec 10
    if (-not $r2 -or $r2.Count -eq 0) { return $true }
    $dataHist = $r2[0].data

    return $dataAovivo -gt $dataHist
  } catch { return $false }
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Invest Ranking - Execucao de Scripts" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$results = @{}
$globalExitCode = 0

# ─── Sempre executa ─────────────────────────────────────
$sempre = @(
  @{Name="B3_AOVIVO"; File="atualizar_b3_cotacoes_aovivo.py"},
  @{Name="FNET_DADOS"; File="atualizar_fnet_dados.py"},
  @{Name="YOUTUBE"; File="atualizar_youtube_videos.py"}
)
foreach ($s in $sempre) {
  $st = run-script $s.Name $s.File
  $results[$s.Name] = $st
  if ($st -like "ERRO*") { $globalExitCode = 1 }
  $state[$s.Name] = $now.ToString("o")
}

# ─── CVM (2h de intervalo) ──────────────────────────────
$cvm = @(
  @{Name="CVM_FII"; File="atualizar_cvm_fii_mensal.py"},
  @{Name="CVM_FIAGRO"; File="atualizar_cvm_fiagro_mensal.py"},
  @{Name="CVM_CADASTRAL"; File="atualizar_cvm_cadastral.py"}
)
foreach ($s in $cvm) {
  if (should-run $s.Name 2) {
    $st = run-script $s.Name $s.File
    $results[$s.Name] = $st
    if ($st -like "ERRO*") { $globalExitCode = 1 }
    $state[$s.Name] = $now.ToString("o")
  } else {
    $results[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) — pulado (<2h desde ultima exec)" -ForegroundColor Gray
  }
}

# ─── StatusInvest (2h de intervalo) ─────────────────────
$status = @(
  @{Name="STATUS_ACOES"; File="atualizar_statusinvest_acoes.py"},
  @{Name="STATUS_DIVIDENDOS"; File="atualizar_statusinvest_dividendos.py"}
)
foreach ($s in $status) {
  if (should-run $s.Name 2) {
    $st = run-script $s.Name $s.File
    $results[$s.Name] = $st
    if ($st -like "ERRO*") { $globalExitCode = 1 }
    $state[$s.Name] = $now.ToString("o")
  } else {
    $results[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) — pulado (<2h desde ultima exec)" -ForegroundColor Gray
  }
}

# ─── Cotacoes Historicas (so se ao vivo tiver data nova) ─
if (check-cotahist) {
  $st = run-script "B3_COTAHIST" "atualizar_b3_cotahist.py"
  $results["B3_COTAHIST"] = $st
  if ($st -like "ERRO*") { $globalExitCode = 1 }
  $state["B3_COTAHIST"] = $now.ToString("o")
} else {
  $results["B3_COTAHIST"] = "SKIP"
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] B3_COTAHIST — pulado (historico ja atualizado)" -ForegroundColor Gray
}

# ─── Salva estado ───────────────────────────────────────
$state | ConvertTo-Json | Set-Content $stateFile

# ─── Log ────────────────────────────────────────────────
$order = @("B3_AOVIVO","FNET_DADOS","YOUTUBE","CVM_FII","CVM_FIAGRO","CVM_CADASTRAL","STATUS_ACOES","STATUS_DIVIDENDOS","B3_COTAHIST")
$parts = foreach ($k in $order) { $results[$k] }
$logLine = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $($parts -join ' | ')"
Add-Content -Path $logFile -Value $logLine

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Log: $logFile" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if ($globalExitCode -eq 0) {
  Write-Host "Concluido com sucesso!" -ForegroundColor Green
} else {
  Write-Host "Erro na execucao!" -ForegroundColor Red
}
