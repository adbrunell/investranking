$projectRoot = Split-Path -Parent $PSScriptRoot
Get-Content "$projectRoot\.env" | ForEach-Object {
  if ($_ -match "^(.*?)=(.*)$" -and $_ -notlike "#*") {
    Set-Item -Path "env:$($matches[1])" -Value $matches[2]
  }
}

Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" atualizar_cvm.py

if ($LASTEXITCODE -eq 0) {
  Write-Host "Concluido com sucesso!" -ForegroundColor Green
} else {
  Write-Host "Erro na execucao!" -ForegroundColor Red
  Read-Host "Pressione Enter para sair"
}
