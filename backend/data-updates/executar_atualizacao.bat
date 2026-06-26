@echo off
title Invest Ranking - Atualizacao
cd /d "C:\Users\adria\OneDrive\Projetos\Invest Ranking\backend\data-updates"
powershell -ExecutionPolicy Bypass -File "run_all.ps1"
echo.
echo ============================================
echo  Concluido! Pressione qualquer tecla para fechar.
echo ============================================
pause >nul
