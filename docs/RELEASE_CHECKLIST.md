# 公開・リリース前の確認手順

GitHub への push・公開の前に行う確認です（2026-10-18 の Phase 4 で実施した手順）。

## 1. テスト（すべて成功すること）

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
docker build -f docker/worker/Dockerfile --target test -t knocks-worker:test .
docker run --rm --init --memory=1g --pids-limit=128 --network=none knocks-worker:test
docker compose --profile test run --rm --build tests
docker compose --profile test down
# 実ブラウザ（README「開発者向け」の E2E 手順。毎回 down -v で初期化してから）
```

## 2. 空のフォルダに clone して確認（コミット漏れ・.gitignore の誤りを見つける）

```bash
git clone <このリポジトリ> /tmp/clone && cd /tmp/clone
docker compose -p ds100knocks-clone --profile test run --rm --build tests
KNOCKS_PORT=8503 docker compose -p ds100knocks-clone up -d --build --wait   # http://127.0.0.1:8503 が応答すること
docker compose -p ds100knocks-clone down -v --rmi local
```

## 3. 秘密情報・ユーザーデータの混入がないこと

```bash
# git の全履歴（Git Bash では MSYS_NO_PATHCONV=1 を前に付ける）
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest git /repo --no-banner --redact
git ls-files | grep -iE '\.sqlite|\.db$|^var/|\.env'   # 何も出ないこと
```

## 4. 脆弱性

```bash
uvx pip-audit --disable-pip --no-deps -r docker/app/requirements.txt -r docker/worker/requirements.txt
# イメージ（OS パッケージを含む）: イメージをファイルに書き出して Trivy で確認
docker save ds100knocks-app:latest -o app.tar
docker run --rm -v "$(pwd):/scan" aquasec/trivy:latest image --input /scan/app.tar --severity HIGH,CRITICAL
```

修正版のある脆弱性があれば、ベースイメージ（ダイジェスト固定）や依存を更新して再テストする。

## 5. 文書

- README のスクリーンショットが現在の画面と合っている（`tools/screenshots.py` で撮り直せる）
- `docs/DEPENDENCY_LICENSES.md` を依存の更新に合わせて再生成した（`tools/dependency_licenses.py`）
- 上流教材を更新した場合は `THIRD_PARTY_NOTICES.md` と `docs/UPSTREAM_SOURCE.md` の commit を更新した

## 2026-10-18 時点の結果

- テスト: 単体 386 / ワーカー 86 / 統合 559 / ブラウザ 10 すべて成功、空の clone から統合テスト・起動も成功
- gitleaks: 全14コミットで検出なし（作業フォルダの検出 18件はすべて Git 管理外の `.venv`）
- pip-audit: 既知の脆弱性なし
- Trivy（ベースイメージ更新後）: app / worker は CRITICAL 0・HIGH 44（すべて Debian 側で修正版なし）。db は CRITICAL 2（libxml2: 修正版なし、gosu の Go 標準ライブラリ: 本アプリは実行時に gosu を使わない）・HIGH 85（24 は修正版あり。ベースイメージ postgres:16.15-trixie は最新で、上流の更新待ち）
- macOS: 実機がなく未確認
