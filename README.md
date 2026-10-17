# 100本ノック トレーナー（非公式）

「データサイエンス100本ノック（構造化データ加工編）」を、**自分のPCのブラウザで Python / SQL を書いて、その場で実行・自動採点・進捗保存**しながら解ける学習アプリです。

- 自分のPCの中だけで動きます（アカウント不要、書いたコードを外部に送りません）
- Python と SQL で同じ問題に別々に挑戦でき、進捗も言語ごとに記録されます
- 書いたコードと正解状態は自動保存され、アプリを閉じても残ります

> 本アプリは一般社団法人データサイエンティスト協会の公式アプリではなく、承認・提携を受けたものでもありません。教材の出典は[下記](#出典ライセンス)を参照してください。

## 現在の対応状況（開発中）

| 項目 | 状況 |
| --- | --- |
| 問題文の表示 | 100問すべて |
| 実行（Python / SQL） | 100問すべてで可能 |
| 自動採点 | **91問**（Python・SQLとも）。正解が1つに決まらない9問（乱数・任意のカテゴリ名など）は理由を表示して自動採点しません |
| SQL でのテーブル作成 | 「データを作成せよ」という問題では CREATE TABLE などを実行できます（作成したテーブルは実行後に自動で取り消され、教材データは変わりません） |
| ファイル入出力 | Python は `./data` に出力します。SQL は安全のため DB サーバー上のファイルを使えないので、`COPY ... TO STDOUT` / `COPY ... FROM STDIN` を使います（画面に案内が出ます） |
| 動作確認済みの環境 | Windows 11 + Docker Desktop（WSL2）。macOS は未確認 |

## 必要なもの

- **Docker Desktop**（[公式サイト](https://www.docker.com/products/docker-desktop/)からインストールし、起動しておく）
- このリポジトリのファイル（`git clone` するか、GitHub の「Code → Download ZIP」で取得して展開）
- ディスク空き容量: 数GB程度（初回にアプリの部品をダウンロード・組み立てるため）

## 起動する

1. Docker Desktop を起動し、画面左下が「Engine running」になるまで待ちます。
2. このフォルダでターミナル（Windows なら PowerShell）を開き、次を実行します。

   ```bash
   docker compose up -d --build
   ```

   初回は数分かかります。2回目以降は数十秒で起動します。
3. ブラウザで **http://127.0.0.1:8501** を開きます。

ポート 8501 がほかのアプリで使われている場合は、`KNOCKS_PORT` で変更できます（例: PowerShell なら `$env:KNOCKS_PORT=8600; docker compose up -d --build` → http://127.0.0.1:8600）。

## 使い方

1. 左のサイドバーで **言語（Python / SQL）** と **問題** を選びます。
2. 問題文を読み、「コード」欄に解答を書きます。入力欄では次のキーが使えます。
   - **Tab** / **Shift+Tab**: インデント / インデントを戻す（複数行を選んでまとめて変更も可）
   - **Enter**: 前の行のインデントを引き継ぎます（Python で `:` で終わる行の次は1段下げます）
   - **Ctrl+Enter**（Mac は Cmd+Enter）: 実行
   - **Esc の後に Tab**: 入力欄の外へフォーカスを移動
   - うまく動かない場合は、サイドバーの「入力欄」を「シンプル」に切り替えてください。
   - **Python**: 最後の行に書いた式の値が結果として表示されます（Jupyter と同じ）。`df_receipt` などのデータは最初から使えます。
   - **SQL**: SELECT 文（WITH 句を含む）を1つ書きます。データベースは読み取り専用なので、壊れる心配はありません。
3. **▶ 実行** で結果を確認し、納得したら **✔ 採点** を押します（実行だけでは正解になりません）。
4. 採点結果は「正解 / 不正解（理由つき）/ 自動採点できない / エラー」のいずれかで表示されます。
5. 「次へ →」で次の問題に進みます。サイドバーの印は ✅ 正解 / ✏️ 挑戦中 / ⬜ 未着手 / 🔖 復習対象 です。
6. 行き詰まったら **💡 ヒント・解答例** を開きます。「ヒント1: 使う関数・構文」→「ヒント2: コードの骨組み」→「解答例」の順に少しずつ表示できます（どこまで見たかは記録されますが、採点には影響しません）。
7. サイドバーの「表示」で **進捗一覧** に切り替えると、全問題の状態を Python / SQL 別に確認できます（行を選ぶとその問題を開きます）。「自動採点に対応している問題だけ表示」で一覧を絞り込めます。

コードは、入力欄から離れたとき・入力が1.5秒止まったとき・実行や採点をしたときに自動保存されます。

## 終了する・再開する

```bash
docker compose down        # 終了（学習履歴は残ります）
docker compose up -d       # 再開（その後 http://127.0.0.1:8501 を開く）
```

> ⚠️ `docker compose down -v` のように **`-v` を付けると学習履歴も削除されます**。

## 学習履歴の保存場所

書いたコード・実行/採点の履歴・進捗は、Docker のボリューム **`ds100knocks_progress`** 内の SQLite ファイルに保存されます。このフォルダの中には保存されないため、Git にコミットされることもありません。

## アップデートする

新しい版のファイルを取得してから（`git pull` など）、次を実行します。学習履歴はそのまま引き継がれます。

```bash
docker compose up -d --build
```

## アンインストール

```bash
docker compose down -v --rmi local   # コンテナ・学習履歴・このアプリのイメージを削除
```

その後、このフォルダを削除します。

## 安全性について

- アプリは自分のPC（127.0.0.1）からのみ開けます。LAN やインターネットには公開しません。
- 書いた Python コードは、画面とは別の隔離されたコンテナで実行されます（時間・メモリ・ファイル書き込みの制限あり、インターネットや DB には接続不可）。
- SQL は読み取り専用の権限で実行され、教材データを変更できません。
- 本人がローカルで使うことを前提にした設計です。**インターネットに公開して他人のコードを実行させる用途には使わないでください。**

## 出典・ライセンス

- 教材: 一般社団法人データサイエンティスト協会 スキル定義委員会「データサイエンス100本ノック（構造化データ加工編）」
  https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess （MIT License。ガイドPDFとロゴは CC BY-ND のため同梱していません）
- 同梱した教材ファイルと取得元のcommitは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
- 本アプリ自体のライセンスは公開時に決定します（MIT を予定）。

---

## 開発者向け

[uv](https://docs.astral.sh/uv/) と Docker Desktop を使います（Python 3.12 は uv が用意します）。

```bash
uv sync                                                # 依存をインストール
uv run pytest                                          # 単体テスト（Docker不要）
uv run ruff check . && uv run ruff format --check .    # lint / format
docker compose --profile test run --rm --build tests   # 統合テスト（DB・ワーカー・UI）
docker compose --profile test down
docker build -f docker/worker/Dockerfile --target test -t knocks-worker:test .
docker run --rm --init knocks-worker:test              # ワーカー単体テスト（fork隔離を含む）
uv run python -m tools.extract_problems                # 同梱教材から問題カタログを再生成
```

E2E確認（学習履歴を書き換えるため、E2E用のプロジェクト名・ポートで実行。毎回 `down -v` で初期化してから）:

```bash
docker compose -p ds100knocks-e2e down -v
KNOCKS_PORT=8502 docker compose -p ds100knocks-e2e up -d --build --wait
uv sync --group e2e && uv run --group e2e playwright install chromium   # 初回のみ
KNOCKS_E2E_URL=http://127.0.0.1:8502 uv run --group e2e pytest tests/e2e -m e2e   # 実ブラウザ
docker compose -p ds100knocks-e2e exec -T app python - solve  < tests/e2e/ui_session.py
docker compose -p ds100knocks-e2e down && KNOCKS_PORT=8502 docker compose -p ds100knocks-e2e up -d --wait
docker compose -p ds100knocks-e2e exec -T app python - verify < tests/e2e/ui_session.py
docker compose -p ds100knocks-e2e down -v
```

構成:

| ディレクトリ | 内容 |
| --- | --- |
| `app/` | Streamlit UI（`editor.py` はコード入力用の軽量エディタ） |
| `core/` | 問題カタログ・実行クライアント・採点・学習履歴（UI非依存） |
| `worker/` | 学習者の Python を隔離実行するワーカー |
| `docker/` | 各コンテナの Dockerfile、教材DBの初期化SQL |
| `exercises/` | 問題カタログ（生成物）と採点定義（`problems/*.toml`） |
| `upstream/` | 原教材のスナップショット（無改変） |
| `tools/` | 教材の同梱・問題抽出ツール |
| `docs/` | 要件・設計・計画・決定事項・セッションログ |
