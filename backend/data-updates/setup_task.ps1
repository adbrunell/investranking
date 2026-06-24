Write-Host "Configurando tarefa agendada Invest Ranking..." -ForegroundColor Cyan

# Desabilita a tarefa antiga que estava quebrada
schtasks /change /tn "\Atualizar FIIs" /DISABLE
Write-Host "  [OK] Tarefa \Atualizar FIIs desabilitada" -ForegroundColor Green

# Deleta a tarefa existente para recriar
schtasks /delete /tn "\InvestRanking-Update" /f 2>$null

# Cria nova tarefa com repeticao a cada 30min
schtasks /create /tn "\InvestRanking-Update" `
  /tr "powershell.exe -ExecutionPolicy Bypass -File 'C:\Users\adria\OneDrive\Projetos\Invest Ranking\backend\data-updates\run_all.ps1'" `
  /sc ONLOGON `
  /ru "DESKTOP-3AR4LBD\adria" `
  /rl HIGHEST `
  /f

Write-Host "  [OK] Tarefa \InvestRanking-Update criada" -ForegroundColor Green

# Adiciona repeticao via PowerShell
$task = Get-ScheduledTask -TaskName "InvestRanking-Update"
if ($task) {
    $trigger = $task.Triggers[0]
    $trigger.Repetition.Interval = "PT10M"
    $trigger.Repetition.Duration = "P1D"
    $trigger.Repetition.StopAtDurationEnd = $false
    Set-ScheduledTask -TaskName "InvestRanking-Update"
    Write-Host "  [OK] Repeticao a cada 10 minutos configurada" -ForegroundColor Green
}

Write-Host ""
Write-Host "Pronto! A tarefa vai executar a cada 30 minutos enquanto voce estiver logado." -ForegroundColor Green
Write-Host "Scripts com captcha (STATUS_ACOES, B3_COTAHIST) tem timeout de 10min." -ForegroundColor Yellow
