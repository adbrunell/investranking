param()

$envFile = Join-Path -Path $PSScriptRoot -ChildPath "..\.env"
if (Test-Path -LiteralPath $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^(SUPABASE_\w+)=(.+)$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2]
        }
    }
}

npx -y @supabase/mcp-server-supabase
