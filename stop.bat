@echo off
rem DS100KnocksMate を終了します（学習履歴は残ります）
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where docker >nul 2>nul
if not errorlevel 1 goto docker_found
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
:docker_found
docker compose down
if errorlevel 1 goto fail
echo 終了しました。学習履歴は残っています（再開するときは start.bat）。
timeout /t 5 >nul 2>nul
exit /b 0
:fail
echo [エラー] 終了に失敗しました。Docker Desktop が起動しているか確認してください。
pause
exit /b 1
