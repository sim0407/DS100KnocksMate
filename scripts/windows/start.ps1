# DS100KnocksMate を起動してブラウザで開く（start.bat から呼ばれる）
. (Join-Path $PSScriptRoot 'common.ps1')

$port = if ($env:KNOCKS_PORT) { $env:KNOCKS_PORT } else { '8501' }
$url = "http://127.0.0.1:$port"
$certFile = Join-Path $script:Root 'docker\certs\host-trusted-roots.crt'

function Export-HostCertificates {
    # この PC（Windows）が信頼しているルート証明書を PEM 形式で書き出す（docker/certs/README.md）
    $certs = @(Get-ChildItem Cert:\LocalMachine\Root) + @(Get-ChildItem Cert:\CurrentUser\Root) |
        Sort-Object Thumbprint -Unique
    $sb = New-Object System.Text.StringBuilder
    foreach ($cert in $certs) {
        $base64 = [Convert]::ToBase64String($cert.RawData) -replace '.{64}', "`$&`n"
        [void]$sb.Append("-----BEGIN CERTIFICATE-----`n" + $base64.TrimEnd("`n") + "`n-----END CERTIFICATE-----`n")
    }
    [System.IO.File]::WriteAllText($certFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  $($certs.Count) 件の証明書を docker\certs\host-trusted-roots.crt に書き出しました。"
}

function Start-App {
    Write-Host 'アプリを起動しています（初回は部品のダウンロードと組み立てで数分かかります）...'
    return Invoke-Logged 'docker compose up -d --build --wait'
}

if (-not (Find-Docker)) {
    Stop-WithError @('[エラー] Docker が見つかりません。Docker Desktop をインストールしてから、もう一度実行してください。',
                     '        https://www.docker.com/products/docker-desktop/')
}

if (-not (Test-Quiet 'docker info')) {
    Write-Host 'Docker Desktop を起動しています（数十秒〜数分かかることがあります）...'
    foreach ($exe in @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
                       "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe")) {
        if (Test-Path $exe) { Start-Process $exe; break }
    }
    $deadline = (Get-Date).AddMinutes(5)
    while (-not (Test-Quiet 'docker info')) {
        if ((Get-Date) -gt $deadline) {
            Stop-WithError @('[エラー] Docker Desktop が起動しませんでした。Docker Desktop を手動で起動し、',
                             '        画面左下が「Engine running」になってから、もう一度実行してください。')
        }
        Start-Sleep -Seconds 3
    }
}

$result = Start-App

if (-not $result.Ok -and $result.Output -match 'CERTIFICATE_VERIFY_FAILED' -and -not (Test-Path $certFile)) {
    Write-Host ''
    Write-Host '[確認] 部品のダウンロードが「証明書を確認できない」エラーで失敗しました。' -ForegroundColor Yellow
    Write-Host '       ウイルス対策ソフトの HTTPS 検査や、会社・学校のネットワーク（プロキシ）で通信が' -ForegroundColor Yellow
    Write-Host '       検査されている場合に起こります。この PC が信頼している証明書を、アプリの組み立てにも' -ForegroundColor Yellow
    Write-Host '       使うことで解決できます（書き出した証明書は docker\certs に置かれ、公開されません）。' -ForegroundColor Yellow
    $answer = if ($env:KNOCKS_TRUST_HOST_CERTS) { $env:KNOCKS_TRUST_HOST_CERTS } else { Read-Host 'この PC の証明書を使って組み立て直しますか？ [Y/n]' }
    if ($answer -match '^(|y|yes|1)$') {
        Export-HostCertificates
        $result = Start-App
    }
}

if (-not $result.Ok) {
    $lines = @('[エラー] アプリの起動に失敗しました。上に表示されたメッセージを確認してください。')
    if ($result.Output -match 'CERTIFICATE_VERIFY_FAILED') {
        $lines += @('        証明書のエラーが続いています。会社・学校のネットワークでは、管理者から組織の証明書（.crt）を',
                    '        もらって docker\certs フォルダに置き、もう一度実行してください（README の「困ったとき」）。')
    }
    if ($result.Output -match 'port is already allocated|address already in use|Only one usage of each socket') {
        $lines += @("        ポート $port がほかのアプリで使われています。README の「ポートを変える」を参照してください。")
    }
    Stop-WithError $lines
}

Write-Host ''
Write-Host "起動しました: $url" -ForegroundColor Green
if (-not $env:KNOCKS_NO_BROWSER) { Start-Process $url }
Write-Host '終了するときは stop.bat を実行してください（学習履歴は残ります）。このウィンドウは閉じてかまいません。'
if (-not $env:KNOCKS_NO_PAUSE) { Start-Sleep -Seconds 10 }
