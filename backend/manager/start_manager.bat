@echo off
title Invest Ranking - Manager
cd /d "%~dp0\..\.."
if not exist "backend\.venv\Scripts\pythonw.exe" (
  echo ERRO: pythonw.exe nao encontrado em backend\.venv\
  pause
  exit /b 1
)
echo Iniciando Invest Ranking Manager (oculto na bandeja)...
start "" /b "backend\.venv\Scripts\pythonw.exe" "backend\manager\main.py"
echo.
echo ✅ O gerenciador esta rodando OCULTO na bandeja do sistema.
echo    Procure pelo icone amarelo "IR" ao lado do relogio.
echo.
echo    - Clique DUAS VEZES no icone para abrir o painel
echo    - Clique DIREITO no icone para: Abrir / Pausar / Sair
echo.
echo Para AUTO-INICIAR com o Windows:
echo    Pressione Win+R, digite shell:startup
echo    Copie este .bat para la dentro
echo.
