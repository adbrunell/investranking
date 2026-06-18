$taskName = "InvestRanking-Update"
$scriptPath = "C:\Users\adria\OneDrive\Projetos\Invest Ranking\scripts\data-updates\run_all.ps1"

# Check if task exists, delete if so
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host "Tarefa antiga removida" -ForegroundColor Gray
}

# Create with schtasks (handles ONLOGON trigger properly)
schtasks /CREATE /TN $taskName `
  /TR "powershell.exe -ExecutionPolicy Bypass -File '$scriptPath'" `
  /SC ONLOGON /RL HIGHEST /F

# Add repetition via PowerShell
$task = Get-ScheduledTask -TaskName $taskName
$trigger = $task.Triggers[0]
$trigger.Repetition.Interval = "PT30M"
$trigger.Repetition.Duration = "P1D"
$trigger.Repetition.StopAtDurationEnd = $false
$task | Set-ScheduledTask

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Tarefa '$taskName' configurada:" -ForegroundColor Cyan
Write-Host "   Trigger: Ao logar" -ForegroundColor White
Write-Host "   Repetir: a cada 30 minutos por 1 dia" -ForegroundColor White
Write-Host "   Nivel:   Mais alto" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan

# Also verify the old broken task is disabled
$oldTask = Get-ScheduledTask -TaskName "Atualizar FIIs" -ErrorAction SilentlyContinue
if ($oldTask) {
  $oldTask | Disable-ScheduledTask
  Write-Host "Tarefa '\Atualizar FIIs' desabilitada" -ForegroundColor Yellow
}

pause
