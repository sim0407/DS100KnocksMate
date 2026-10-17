# 100 Knocks Trainer — Claude Codeへの開発引き継ぎ

このフォルダは **開発開始用の設計・指示書セット** です。アプリの実装本体ではありません。

## 目的

データサイエンティスト協会の「データサイエンス100本ノック（構造化データ加工編）」を教材に、Python・SQLを実際に書いて学べる **ローカルWebアプリ** を構築し、GitHubで公開する。

重視する体験：①問題を読む → ②Python/SQLを書く → ③その場で実行結果を見る → ④自動採点する → ⑤解答と進捗を自動保存する。

## このフォルダの使い方

1. これらのファイルを新しい開発用フォルダのルートに展開する（`CLAUDE.md` をルートに置く）。
2. そのフォルダで Claude Code を起動する。
3. `START_PROMPT.md` の文章をClaude Codeへ貼り付ける。
4. Claude Codeの最初の仕事は **公式リポジトリの調査・ライセンス確認・Phase 0の技術的検証**。設計・実装の判断はこのファイル群を正とする。
5. 以後、マイルストーンごとに実装・テスト・成果報告を行う。

まだ環境にDockerがない場合や、ネットワークが使えない場合は、その制約と未検証事項をClaude Codeに記録させる。確認していないことを「動作済み」と扱わない。

## ファイルの案内

| ファイル | 内容 |
| --- | --- |
| `CLAUDE.md` | Claude Codeが常に従う開発方針と作業ルール |
| `START_PROMPT.md` | Claude Codeの初回セッションに貼るプロンプト |
| `docs/PRODUCT_REQUIREMENTS.md` | 機能・画面・MVPスコープ・受入条件 |
| `docs/TECHNICAL_DESIGN.md` | アーキテクチャ、実行・採点・進捗・安全設計 |
| `docs/IMPLEMENTATION_PLAN.md` | Phase 0〜4の作業と完了条件 |
| `docs/DECISIONS_AND_RISKS.md` | 確定方針、保留事項、リスクと対策 |
| `docs/UPSTREAM_SOURCE.md` | 教材の出典・ライセンス・取り込みルール |
| `docs/SESSION_LOG.md` | 開発セッションをまたぐ記録（初期テンプレート） |

## 目標とする技術スタック

- UI: Streamlit（コードエディタ用コンポーネントは実機で評価して選ぶ）
- アプリ・採点: Python
- SQL教材データベース: PostgreSQL（公式教材との互換性）
- 学習履歴: SQLite（永続化）
- 実行環境: Docker Compose（UI、Python実行ワーカー、PostgreSQLを分離）
- テスト: pytest（ユニット・統合・必要最低限のE2E）
- 配布: GitHubの公開リポジトリ、最終的には `docker compose up --build` など簡単な起動

## 明確な非目標（初期段階）

- クラウドサービス、ログイン、複数ユーザー管理
- R言語、AI採点・AI解説、スマホ向けUIの最適化
- 100問全問の自動採点を最初の1回の実装で完成させること
- 任意の第三者がインターネットからコードを投稿できる公開実行サービス

## 公式教材

- Repository: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess
- 主な配置: `docker/work/`（設問Notebook）、`docker/work/answer/`（模範解答Notebook）、`docker/work/data/`（CSV）、`docker/db/init/`（DB初期化）
- READMEによると原則MITライセンス。ただし `docker/doc/100knocks_guide.pdf` は CC BY-ND。詳細は `docs/UPSTREAM_SOURCE.md`。

## 注意

この引き継ぎセットには、公式教材の問題本文・CSV・模範解答・実行可能なアプリは同梱していません。公式教材の確認・取り込みは、開発時にClaude Codeが実施します。教材を取り込む際は、出典・ライセンス・取得元のcommitを記録します。

---

## 開発者向け（Phase 0 進行中）

アプリ本体はまだありません。現時点で使えるコマンド（[uv](https://docs.astral.sh/uv/) が必要。Python 3.12 は uv が用意します）:

```bash
uv sync                               # 開発用依存（pytest, ruff）をインストール
uv run pytest                         # テスト実行
uv run ruff check . && uv run ruff format --check .   # lint / format チェック
uv run python -m tools.extract_problems               # 同梱教材から問題カタログを再生成
```

Docker（Docker Desktop）を使う統合テスト:

```bash
docker compose --profile test run --rm --build tests   # DB・Pythonワーカーを起動して統合テスト
docker compose --profile test down                     # 後片付け
docker build -f docker/worker/Dockerfile --target test -t knocks-worker:test .
docker run --rm --init knocks-worker:test              # ワーカー単体テスト（fork隔離を含む）
```

- 原教材のスナップショット: `upstream/`（出典・ライセンスは `THIRD_PARTY_NOTICES.md`）
- 生成された問題カタログ: `exercises/catalog/`
