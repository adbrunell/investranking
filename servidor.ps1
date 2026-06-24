$port = 8080
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $dir "frontend"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Invest Ranking - Servidor Local" -ForegroundColor Yellow
Write-Host "  Acesse: http://localhost:$port" -ForegroundColor Green
Write-Host "  Ctrl+C para parar" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
& "$dir\backend\.venv\Scripts\python.exe" -m http.server $port --directory "$frontend"