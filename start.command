#!/bin/bash
# DS100KnocksMate を起動してブラウザで開きます（Finder でダブルクリック）
cd "$(dirname "$0")" || exit 1
PORT="${KNOCKS_PORT:-8501}"
URL="http://127.0.0.1:${PORT}"
CERT_FILE="docker/certs/host-trusted-roots.crt"
LOG_FILE="$(mktemp "${TMPDIR:-/tmp}/ds100knocks.XXXXXX")" || exit 1
trap 'rm -f "$LOG_FILE"' EXIT
set -o pipefail

pause_and_exit() {
  echo
  # テスト時は KNOCKS_NO_PAUSE=1 で待たない
  if [ -z "${KNOCKS_NO_PAUSE:-}" ]; then read -r -p "Enter キーで閉じます" _; fi
  exit 1
}

start_app() {
  echo "アプリを起動しています（初回は部品のダウンロードと組み立てで数分かかります）..."
  docker compose up -d --build --wait 2>&1 | tee "$LOG_FILE"
}

export_host_certificates() {
  # この Mac が信頼している証明書（システム・ログインのキーチェーン）を PEM 形式で書き出す（docker/certs/README.md）
  security find-certificate -a -p \
    /System/Library/Keychains/SystemRootCertificates.keychain \
    /Library/Keychains/System.keychain \
    "$HOME/Library/Keychains/login.keychain-db" >"$CERT_FILE" 2>/dev/null
  echo "  $(grep -c 'BEGIN CERTIFICATE' "$CERT_FILE") 件の証明書を ${CERT_FILE} に書き出しました。"
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

ok=0
if start_app; then
  ok=1
elif grep -q CERTIFICATE_VERIFY_FAILED "$LOG_FILE" && [ ! -f "$CERT_FILE" ]; then
  echo
  echo "[確認] 部品のダウンロードが「証明書を確認できない」エラーで失敗しました。"
  echo "       ウイルス対策ソフトの HTTPS 検査や、会社・学校のネットワーク（プロキシ）で通信が"
  echo "       検査されている場合に起こります。この Mac が信頼している証明書を、アプリの組み立てにも"
  echo "       使うことで解決できます（書き出した証明書は docker/certs に置かれ、公開されません）。"
  answer="${KNOCKS_TRUST_HOST_CERTS:-}"
  if [ -z "$answer" ]; then read -r -p "この Mac の証明書を使って組み立て直しますか？ [Y/n] " answer; fi
  case "$answer" in
    "" | [Yy] | [Yy][Ee][Ss] | 1)
      export_host_certificates
      if start_app; then ok=1; fi
      ;;
  esac
fi
if [ "$ok" != "1" ]; then
  echo
  echo "[エラー] アプリの起動に失敗しました。上に表示されたメッセージを確認してください。"
  if grep -q CERTIFICATE_VERIFY_FAILED "$LOG_FILE"; then
    echo "        証明書のエラーが続いています。会社・学校のネットワークでは、管理者から組織の証明書（.crt）を"
    echo "        もらって docker/certs フォルダに置き、もう一度実行してください（README の「困ったとき」）。"
  fi
  if grep -qE "port is already allocated|address already in use" "$LOG_FILE"; then
    echo "        ポート ${PORT} がほかのアプリで使われています。README の「ポートを変える」を参照してください。"
  fi
  pause_and_exit
fi
echo
echo "起動しました: ${URL}"
if [ -z "${KNOCKS_NO_BROWSER:-}" ]; then open "$URL"; fi
echo "終了するときは stop.command を実行してください（学習履歴は残ります）。"
