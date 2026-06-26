@echo off
title Invest Ranking - Configurar Tarefa Agendada
cd /d "%~dp0"

echo ============================================
echo  Configurando tarefa agendada Invest Ranking
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_task.ps1"

echo.
pause
