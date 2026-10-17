@echo off
rem DS100KnocksMate を起動してブラウザで開きます（ダブルクリックで実行）
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if "%KNOCKS_PORT%"=="" set "KNOCKS_PORT=8501"
set "URL=http://127.0.0.1:%KNOCKS_PORT%"

rem docker コマンドを探す（PATH に無い場合は Docker Desktop の既定のインストール先）
where docker >nul 2>nul
if not errorlevel 1 goto docker_found
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
where docker >nul 2>nul
if not errorlevel 1 goto docker_found
echo [エラー] Docker が見つかりません。Docker Desktop をインストールしてから、もう一度実行してください。
echo         https://www.docker.com/products/docker-desktop/
goto fail

:docker_found
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
echo Docker Desktop を起動しています（数十秒〜数分かかることがあります）...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" start "" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
set /a WAITED=0
:wait_docker
timeout /t 3 /nobreak >nul 2>nul
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
set /a WAITED+=3
if %WAITED% LSS 300 goto wait_docker
echo [エラー] Docker Desktop が起動しませんでした。Docker Desktop を手動で起動し、
echo         画面左下が「Engine running」になってから、もう一度実行してください。
goto fail

:docker_ready
echo アプリを起動しています（初回は部品のダウンロードと組み立てで数分かかります）...
docker compose up -d --build --wait
if errorlevel 1 goto compose_failed
echo.
echo 起動しました: %URL%
if not "%KNOCKS_NO_BROWSER%"=="1" start "" "%URL%"
echo 終了するときは stop.bat を実行してください（学習履歴は残ります）。
timeout /t 10 >nul 2>nul
exit /b 0

:compose_failed
echo [エラー] アプリの起動に失敗しました。上に表示されたメッセージを確認してください。
echo         ポート %KNOCKS_PORT% が使用中の場合は README の「ポートを変える」を参照してください。

:fail
echo.
pause
exit /b 1
