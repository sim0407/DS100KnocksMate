# DS100KnocksMate を終了する（stop.bat から呼ばれる。学習履歴は残る）
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Find-Docker)) {
    Stop-WithError @('[エラー] Docker が見つかりません。')
}
$result = Invoke-Logged 'docker compose down'
if (-not $result.Ok) {
    Stop-WithError @('[エラー] 終了に失敗しました。Docker Desktop が起動しているか確認してください。')
}
Write-Host ''
Write-Host '終了しました。学習履歴は残っています（再開するときは start.bat）。' -ForegroundColor Green
if (-not $env:KNOCKS_NO_PAUSE) { Start-Sleep -Seconds 5 }
