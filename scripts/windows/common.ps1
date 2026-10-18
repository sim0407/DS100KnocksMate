# 起動・停止用スクリプトの共通部品（start.ps1 / stop.ps1 から読み込む）
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $script:Root

function Wait-Close {
    # ダブルクリックで開いたウィンドウがすぐ閉じないように待つ（テスト時は KNOCKS_NO_PAUSE=1）
    if (-not $env:KNOCKS_NO_PAUSE) { [void](Read-Host 'Enter キーで閉じます') }
}

function Stop-WithError([string[]]$Lines) {
    Write-Host ''
    foreach ($line in $Lines) { Write-Host $line -ForegroundColor Red }
    Wait-Close
    exit 1
}

function Test-Quiet([string]$Command) {
    # コマンドを出力なしで実行し、成功したかどうかを返す
    cmd /c "$Command >nul 2>&1"
    return ($LASTEXITCODE -eq 0)
}

function Find-Docker {
    # docker コマンドを探す（PATH に無い場合は Docker Desktop の既定のインストール先）
    if (Get-Command docker -ErrorAction SilentlyContinue) { return $true }
    foreach ($dir in @("$env:ProgramFiles\Docker\Docker\resources\bin",
                       "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin")) {
        if (Test-Path (Join-Path $dir 'docker.exe')) { $env:PATH = "$dir;$env:PATH" }
    }
    return [bool](Get-Command docker -ErrorAction SilentlyContinue)
}

function Invoke-Logged([string]$Command) {
    # コマンドの出力を画面に出しつつ記録する。戻り値は @{ Ok; Output }
    $output = New-Object System.Collections.Generic.List[string]
    cmd /c "$Command 2>&1" | ForEach-Object { Write-Host $_; $output.Add([string]$_) }
    return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($output -join "`n") }
}
