#!/bin/bash
# DS100KnocksMate を起動してブラウザで開きます（Finder でダブルクリック）
cd "$(dirname "$0")" || exit 1
PORT="${KNOCKS_PORT:-8501}"
URL="http://127.0.0.1:${PORT}"

pause_and_exit() {
  echo
  read -r -p "Enter キーで閉じます" _
  exit 1
}

# docker コマンドを探す（PATH に無い場合は Docker Desktop の既定の場所）
if ! command -v docker >/dev/null 2>&1; then
  for dir in /usr/local/bin /opt/homebrew/bin /Applications/Docker.app/Contents/Resources/bin; do
    if [ -x "$dir/docker" ]; then export PATH="$dir:$PATH"; fi
  done
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "[エラー] Docker が見つかりません。Docker Desktop をインストールしてから、もう一度実行してください。"
  echo "        https://www.docker.com/products/docker-desktop/"
  pause_and_exit
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop を起動しています（数十秒〜数分かかることがあります）..."
  open -a Docker || true
  for _ in $(seq 1 100); do
    sleep 3
    if docker info >/dev/null 2>&1; then break; fi
  done
  if ! docker info >/dev/null 2>&1; then
    echo "[エラー] Docker Desktop が起動しませんでした。手動で起動してから、もう一度実行してください。"
    pause_and_exit
  fi
fi

echo "アプリを起動しています（初回は部品のダウンロードと組み立てで数分かかります）..."
if ! docker compose up -d --build --wait; then
  echo "[エラー] アプリの起動に失敗しました。上に表示されたメッセージを確認してください。"
  echo "        ポート ${PORT} が使用中の場合は README の「ポートを変える」を参照してください。"
  pause_and_exit
fi
echo
echo "起動しました: ${URL}"
if [ "${KNOCKS_NO_BROWSER:-}" != "1" ]; then open "$URL"; fi
echo "終了するときは stop.command を実行してください（学習履歴は残ります）。"
