$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Get-Content "$projectRoot\.env" | ForEach-Object {
  if ($_ -match "^(.*?)=(.*)$" -and $_ -notlike "#*") {
    Set-Item -Path "env:$($matches[1])" -Value $matches[2]
  }
}

Set-Location $PSScriptRoot

$stateFile = "$PSScriptRoot\.run_state.json"
$logFile = "$PSScriptRoot\log.txt"
if (-not (Test-Path $logFile)) {
  "data_hora | b3_aovivo | fnet_dados | youtube | cvm_fii | cvm_fiagro | cvm_cadastral | status_acoes | status_dividendos | b3_cotahist | fatos_ia" | Set-Content $logFile
}
$py = "$projectRoot\backend\.venv\Scripts\python.exe"
$apiKey = $env:SUPABASE_SERVICE_KEY
$supabaseUrl = $env:SUPABASE_URL
$parentProc = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
$parentName = (Get-CimInstance Win32_Process -Filter "ProcessId=$parentProc").Name
$isTaskScheduler = $parentName -match 'svchost|taskeng|explorer'
$captchaScripts = @()
$scriptOrder = @("B3_AOVIVO","FNET_DADOS","YOUTUBE","CVM_FII","CVM_FIAGRO","CVM_CADASTRAL","STATUS_ACOES","STATUS_DIVIDENDOS","B3_COTAHIST")

$state = @{}
if (Test-Path $stateFile) {
  try { $state = Get-Content $stateFile | ConvertFrom-Json -AsHashtable } catch {}
}
$now = (Get-Date).ToUniversalTime()

function should-run($name, $intervalHours) {
  if (-not $state.ContainsKey($name)) { return $true }
  $last = [DateTime]$state[$name]
  $elapsed = ((Get-Date).ToUniversalTime() - $last).TotalHours
  return $elapsed -ge $intervalHours
}

function log-db {
  if (-not $apiKey -or -not $supabaseUrl) { return }
  $h = @{"apikey"=$apiKey; "Authorization"="Bearer $apiKey"; "Content-Type"="application/json"}
  $body = @{
    started_at = $runStarted.ToString("o")
    finished_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  foreach ($k in $scriptOrder) { $body[$k.ToLower()] = $statuses[$k] }; $body["fatos_ia"] = $statuses["FATOS_IA"]
  try {
    Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/00.log_atualizacao" -Method Post -Headers $h -Body ($body | ConvertTo-Json) -TimeoutSec 10 | Out-Null
  } catch {
    Write-Host "  [Aviso] Falha ao salvar log no banco: $_" -ForegroundColor Gray
  }
}

function run-script($name, $file) {
  $started = (Get-Date).ToUniversalTime()
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Executando $name..." -ForegroundColor Yellow
  $tempFile = Join-Path $env:TEMP "$($name)_run.txt"
  $output = & $py $file 2>&1
  $ec = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  $output | ForEach-Object { Write-Host $_ }
  $output | Out-File -FilePath $tempFile
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

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Invest Ranking - Execucao de Scripts" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$globalExitCode = 0
$statuses = @{}
$runStarted = (Get-Date).ToUniversalTime()

$sempre = @(
  @{Name="B3_AOVIVO"; File="atualizar_b3_cotacoes_aovivo.py"},
  @{Name="FNET_DADOS"; File="atualizar_fnet_dados.py"}
)
foreach ($s in $sempre) {
  $st = run-script $s.Name $s.File
  $statuses[$s.Name] = $st
  if ($st -like "ERRO*") { $globalExitCode = 1 }
  $state[$s.Name] = $now.ToString("o")
}

$horario = @(
  @{Name="YOUTUBE"; File="atualizar_youtube_videos.py"},
  @{Name="B3_COTAHIST"; File="gdrive_cotahist.py"}
)
foreach ($s in $horario) {
  if (should-run $s.Name 1) {
    $st = run-script $s.Name $s.File
    $statuses[$s.Name] = $st
    if ($st -like "ERRO*") { $globalExitCode = 1 }
    $state[$s.Name] = $now.ToString("o")
  } else {
    $statuses[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) - pulado (<1h)" -ForegroundColor Gray
  }
}

$cvm = @(
  @{Name="CVM_FII"; File="atualizar_cvm_fii_mensal.py"},
  @{Name="CVM_FIAGRO"; File="atualizar_cvm_fiagro_mensal.py"},
  @{Name="CVM_CADASTRAL"; File="atualizar_cvm_cadastral.py"}
)
foreach ($s in $cvm) {
  if (should-run $s.Name 2) {
    $st = run-script $s.Name $s.File
    $statuses[$s.Name] = $st
    if ($st -like "ERRO*") { $globalExitCode = 1 }
    $state[$s.Name] = $now.ToString("o")
  } else {
    $statuses[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) - pulado (<2h)" -ForegroundColor Gray
  }
}

$status = @(
  @{Name="STATUS_ACOES"; File="atualizar_statusinvest_acoes.py"},
  @{Name="STATUS_DIVIDENDOS"; File="atualizar_statusinvest_dividendos.py"}
)
foreach ($s in $status) {
  if ($isTaskScheduler -and $captchaScripts -contains $s.Name) {
    $statuses[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) - pulado (requer captcha)" -ForegroundColor Gray
  } elseif (should-run $s.Name 2) {
    $st = run-script $s.Name $s.File
    $statuses[$s.Name] = $st
    if ($st -like "ERRO*") { $globalExitCode = 1 }
    $state[$s.Name] = $now.ToString("o")
  } else {
    $statuses[$s.Name] = "SKIP"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($s.Name) - pulado (<2h)" -ForegroundColor Gray
  }
}

$parts = foreach ($k in $scriptOrder) { $statuses[$k] }; $parts += $statuses["FATOS_IA"]
$logLine = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $($parts -join ' | ')"
Add-Content -Path $logFile -Value $logLine
log-db
# Atualiza minigrafico no banco
try {
  Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/rpc/fn_atualizar_minigrafico" -Method Post -Headers @{"apikey"=$apiKey; "Authorization"="Bearer $apiKey"} -TimeoutSec 120 | Out-Null
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Minigrafico atualizado" -ForegroundColor Green
} catch {
  Write-Host "  [Aviso] Falha ao atualizar minigrafico: $_" -ForegroundColor Gray
}
# Atualiza Ranking FIIs (materialized view)
try {
  Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/rpc/fn_refresh_ranking_fiis" -Method Post -Headers @{"apikey"=$apiKey; "Authorization"="Bearer $apiKey"} -TimeoutSec 120 | Out-Null
  Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Ranking FIIs atualizado" -ForegroundColor Green
} catch {
  Write-Host "  [Aviso] Falha ao atualizar Ranking FIIs: $_" -ForegroundColor Gray
}
# Limpa cotacoes historicas (>2 anos)
try {
  Invoke-RestMethod -Uri "$supabaseUrl/rest/v1/rpc/fn_limpar_b3_historico" -Method Post -Headers @{"apikey"=$apiKey; "Authorization"="Bearer $apiKey"} -TimeoutSec 120 | Out-Null
} catch {
  Write-Host "  [Aviso] Falha ao limpar historico B3: $_" -ForegroundColor Gray
}
# Processa Fatos Relevantes com IA (Gemini)
try {
  $tempFile = Join-Path $env:TEMP "FATOS_IA_run.txt"
  & $py processar_fatos_ia.py 2>&1 | Out-File -FilePath $tempFile
  Get-Content $tempFile | ForEach-Object { Write-Host $_ }
  $statuses["FATOS_IA"] = if (Select-String -Path $tempFile -Pattern "^RESULT:" -Quiet) { (Select-String -Path $tempFile -Pattern "^RESULT:" | Select-Object -Last 1).ToString().Replace("RESULT:", "") } else { "OK" }
  Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
} catch {
  Write-Host "  [Aviso] Falha ao processar fatos IA: $_" -ForegroundColor Gray
  $statuses["FATOS_IA"] = "ERRO"
}
$state | ConvertTo-Json | Set-Content $stateFile

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
