#!/bin/bash
# DS100KnocksMate を終了します（学習履歴は残ります）
cd "$(dirname "$0")" || exit 1
if ! command -v docker >/dev/null 2>&1; then
  for dir in /usr/local/bin /opt/homebrew/bin /Applications/Docker.app/Contents/Resources/bin; do
    if [ -x "$dir/docker" ]; then export PATH="$dir:$PATH"; fi
  done
fi
if docker compose down; then
  echo "終了しました。学習履歴は残っています（再開するときは start.command）。"
else
  echo "[エラー] 終了に失敗しました。Docker Desktop が起動しているか確認してください。"
  read -r -p "Enter キーで閉じます" _
  exit 1
fi
