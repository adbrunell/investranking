Write-Host "Configurando tarefa agendada Invest Ranking..." -ForegroundColor Cyan

# Desabilita a tarefa antiga que estava quebrada
schtasks /change /tn "\Atualizar FIIs" /DISABLE 2>$null
Write-Host "  [OK] Tarefa \Atualizar FIIs desabilitada" -ForegroundColor Green

# Deleta a tarefa existente para recriar
schtasks /delete /tn "\InvestRanking-Update" /f 2>$null

$runAll = Join-Path $PSScriptRoot "run_all.ps1"
# Cria nova tarefa (ONLOGON nao suporta /ri na criacao)
schtasks /create /tn "\InvestRanking-Update" `
  /tr "powershell.exe -ExecutionPolicy Bypass -File '$runAll'" `
  /sc ONLOGON `
  /ru "$env:USERDOMAIN\$env:USERNAME" `
  /rl HIGHEST `
  /f

Write-Host "  [OK] Tarefa \InvestRanking-Update criada" -ForegroundColor Green

# Define repeticao de 10min via COM API (unico metodo que funciona com ONLOGON)
try {
    $s = New-Object -ComObject Schedule.Service
    $s.Connect()
    $t = $s.GetFolder("\").GetTask("InvestRanking-Update")
    $x = [xml]$t.Xml
    $trig = $x.Task.Triggers.LogonTrigger
    if ($trig.Repetition) {
        $trig.Repetition.Interval = "PT10M"
        $trig.Repetition.Duration = "P1D"
        $trig.Repetition.StopAtDurationEnd = $false
    } else {
        $rep = $x.CreateElement("Repetition", $x.DocumentElement.NamespaceURI)
        $rep.SetAttribute("Interval", "PT10M")
        $rep.SetAttribute("Duration", "P1D")
        $rep.SetAttribute("StopAtDurationEnd", "false")
        $trig.AppendChild($rep) | Out-Null
    }
    $s.GetFolder("\").RegisterTask("InvestRanking-Update", $x.OuterXml, 6, $null, $null, 5, $null)
    Write-Host "  [OK] Repeticao a cada 10min configurada" -ForegroundColor Green
} catch {
    Write-Host "  [Aviso] Nao foi possivel configurar repeticao: $_" -ForegroundColor Yellow
    Write-Host "  Execute manualmente no PowerShell Admin:" -ForegroundColor Yellow
    Write-Host '    $t = Get-ScheduledTask -TaskName "InvestRanking-Update"' -ForegroundColor Gray
    Write-Host '    $t.Triggers[0].Repetition.Interval = "PT10M"' -ForegroundColor Gray
    Write-Host '    $t.Triggers[0].Repetition.Duration = "P1D"' -ForegroundColor Gray
    Write-Host '    $t.Triggers[0].Repetition.StopAtDurationEnd = $false' -ForegroundColor Gray
    Write-Host '    Set-ScheduledTask -TaskName "InvestRanking-Update"' -ForegroundColor Gray
}

Write-Host ""
Write-Host "Pronto! A tarefa vai executar a cada 10 minutos enquanto voce estiver logado." -ForegroundColor Green
Write-Host "Scripts com captcha (STATUS_ACOES) sao pulados quando executados pelo agendador." -ForegroundColor Yellow
