@echo off
title Invest Ranking - Manager (DEBUG)
cd /d "%~dp0\..\.."
if not exist "backend\.venv\Scripts\python.exe" (
  echo ERRO: python.exe nao encontrado em backend\.venv\
  pause
  exit /b 1
)
echo Iniciando Manager em modo DEBUG (janela visivel)...
echo Feche a janela para parar.
echo.
echo Se aparecer erro de import, instale as dependencias:
echo   backend\.venv\Scripts\python.exe -m pip install -r backend\manager\requirements.txt
echo.
"backend\.venv\Scripts\python.exe" "backend\manager\main.py"
pause
