@echo off
setlocal enabledelayedexpansion

set "ARQ_STATUS=%~dp0..\00.STATUS_ATUALIZACAO"

cd /d "%~dp0..\.."
for /f "tokens=*" %%a in (.env) do set %%a
cd scripts

cls
echo.
echo ============================================
echo   Invest Ranking - Execucao de Scripts
echo ============================================
echo.

set "STATS="
set EXIT_CODE=0

REM Use run_all.ps1 em vez deste .bat (ps1 tem logica condicional)
REM Agende no Windows: powershell -File "scripts\data-updates\run_all.ps1"
call :roda "B3_AOVIVO" "data-updates\atualizar_b3_cotacoes_aovivo.py"
call :roda "FNET_DADOS" "data-updates\atualizar_fnet_dados.py"
call :roda "YOUTUBE" "data-updates\atualizar_youtube_videos.py"

echo %DATE% ^| %TIME:~0,8% ^| %STATS% >> "%ARQ_STATUS%"

echo.
echo ============================================
echo   Log: 00.STATUS_ATUALIZACAO
echo ============================================
echo.
if %EXIT_CODE% equ 0 (echo Concluido com sucesso!) else (echo Concluido com erros!)
echo.
pause
exit /b %EXIT_CODE%

:roda
set "NOME=%~1"
set "SCRIPT=%~2"
set "OUT=%TEMP%\%NOME:_=_%.txt"

echo.
echo  [ .. ] %NOME%

REM Executa mostrando saida na tela e capturando para arquivo
powershell -Command "$r=0; & python '%SCRIPT%' 2>&1 | Tee-Object -FilePath '%OUT%'; if ($LASTEXITCODE) {$r=$LASTEXITCODE}; exit $r" 2>nul
set "EC=!ERRORLEVEL!"

REM Extrai resultado do arquivo
set "RAW="
for /f "tokens=*" %%i in ('findstr /b "RESULT:" "%OUT%" 2^>nul') do set "RAW=%%i"
if defined RAW set "RAW=!RAW:RESULT:=!"
if not defined RAW if "!EC!"=="0" set "RAW=OK"
if not defined RAW set "RAW=ERRO(!EC!)"

set "STATUS=%NOME%:%RAW%"
if defined STATS (set "STATS=!STATS! ^| !STATUS!") else (set "STATS=!STATUS!")
if "!RAW:ERRO=!" neq "!RAW!" set EXIT_CODE=1

del "%OUT%" 2>nul
exit /b 0
