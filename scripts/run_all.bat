@echo off
cd /d "%~dp0.."
for /f "tokens=*" %%a in (.env) do set %%a
cd scripts
call .venv\Scripts\python atualizar_cvm.py
pause