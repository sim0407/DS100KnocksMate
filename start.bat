@echo off
rem Start DS100KnocksMate and open it in the browser (double-click).
rem The actual work is done in scripts\windows\start.ps1 (Japanese messages).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\start.ps1"
