$taskName = "InvestRanking-Update"
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$folder = $service.GetFolder("\")
$task = $folder.GetTask($taskName)
$definition = $task.Definition
$trigger = $definition.Triggers.Item(1)
$trigger.Repetition.Interval = "PT30M"
$trigger.Repetition.Duration = "P1D"
$trigger.Repetition.StopAtDurationEnd = $false
$folder.RegisterTaskDefinition($taskName, $definition, 4, $null, $null, 3)

Write-Host "Repetition configurada: a cada 30min por 1 dia" -ForegroundColor Green

# Verify
$v = $folder.GetTask($taskName)
Write-Host "Trigger type: $($v.Definition.Triggers.Item(1).Type)"
Write-Host "Repetition interval: $($v.Definition.Triggers.Item(1).Repetition.Interval)"
Write-Host "Repetition duration: $($v.Definition.Triggers.Item(1).Repetition.Duration)"
Read-Host "Pressione Enter para sair"
