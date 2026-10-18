@echo off
rem Stop DS100KnocksMate (learning history is kept).
rem The actual work is done in scripts\windows\stop.ps1 (Japanese messages).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\stop.ps1"
