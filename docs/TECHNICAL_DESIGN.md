# 技術設計 — ローカル実行・採点・進捗

## 1. 構成方針

```text
Browser (127.0.0.1:8501)
    |
Streamlit UI / application (Python)
    |-- exercise repository (YAML/JSON definitions + validators)
    |-- progress repository (SQLite on persistent volume)
    |-- SQL runner (PostgreSQL with read-only role/transaction)
    |-- Python runner API -> isolated worker container
                              |-- read-only CSV / fixed libraries
                              |-- per-run fresh subprocess, timeout, caps
                              `-- bounded JSON response

PostgreSQL <- official dataset / DB init scripts (with adjustments documented)
```

UIと採点ロジック、問題定義、永続化、Python実行環境を分離。ホストから見る公開ポートは原則Streamlitのみ。Postgres/workerは内部Dockerネットワーク上に配置。初期対象は **信頼できるローカル利用者による利用** に限定。Docker隔離を完全な攻撃者対策と誤認しない。

## 2. 推奨ディレクトリ（実装開始後に作る）

```text
DS100KnocksMate/
├── CLAUDE.md
├── README.md
├── app/                     # Streamlit UI, controllers
├── core/
│   ├── exercises/           # 問題取得とモデル
│   ├── execution/           # Python/SQL runner interfaces
│   ├── grading/             # strategy/validators/normalizers
│   └── progress/            # SQLite repository
├── worker/                  # PythonをUI外で実行するサービス
├── exercises/
│   ├── problems/            # 設問メタデータ
│   ├── validators/          # 固有テスト
│   └── reference/           # 検証済み期待値（学習UIには露出しない）
├── datasets/                # 再配布する対象データ（必要部分、著作権表示付き）
├── docker/                  # Dockerfiles / SQL初期化など
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/
├── docker-compose.yml
├── pyproject.toml
├── .gitignore
└── LICENSE
```

### 教材データ配布

まず上流教材を確認し、利用するCSV、初期化スクリプト、問題本文、検証済み参照出力だけを必要最小限取り込む設計を優先。**出典と上流commit hashを固定し、元のライセンス・著作権表示を保持する**。公式ガイドPDFとロゴは同梱しない。取得時ネットワーク依存方式にする場合は初回セットアップの複雑さを評価し、採用理由を記録する。

## 3. 問題定義フォーマット（案）

**実際の問題を調査してから埋める**。下記はスキーマのイメージであり、公式問題の実物ではない。

```yaml
id: '001'               # 原教材とのID対応表を別途用意
source_ids:
  python: 'P-001'
  sql: 'S-001'
title: '（公式教材から取得）'
category: '（公式教材から取得）'
statement: '（公式教材から取得）'
languages: [python, sql]
input_tables: ['receipt']
validators:
  python:
    strategy: dataframe_exact
    reference_id: '001-python'
    ordered_rows: true
    ordered_columns: true
  sql:
    strategy: dataframe_exact
    reference_id: '001-sql'
    ordered_rows: true
    ordered_columns: true
status: verified
```

**注意**: 問題に明示されていない順序を強制しない。source IDも現物と照合すること。教材読み込みロジックはUIに埋め込まず、問題パーサ/マニフェスト生成ツールに分離する。

## 4. コード実行インターフェース

- 共通入力: `exercise_id`, `language`, `source_code`, `mode` (`run` / `grade`), `request_id`
- 共通出力: `execution_status`, `result_type`, `result_data`（件数制限あり）, `stdout`, `stderr`, `error_message`, `elapsed_ms`, `truncated`
- 採点出力: `grading_status` (`passed`, `failed`, `manual_review`, `error`), `feedback`, `details`
- エラー・タイムアウト・出力過大も通常の戻り値として扱う。UI全体をクラッシュさせない。
- 表データをクロスプロセスで渡す時はサイズ制限付きJSON等の **安全にデコードできる形式**。ユーザーコードが生成したpickleをUI側でunpickleしない。

### Python

- UI上のコードを隔離ワーカーに送る。
- ワーカーはユーザーコードごとに新規プロセス/一時作業ディレクトリを利用し、実行が終わったらリセットする。
- `pandas` などの固定ライブラリと `df_receipt` 等の公式データ変数をセットアップする。CSV型は上流Notebookに合わせる。
- Notebookに近い操作感のため、最終式の値（DataFrame/Series/スカラー）を取得できる方式を検証する。`result` 変数への明示代入も許容してよい。
- DataFrame等の結果は `columns`, `rows`, `dtypes`, `row_count`, `truncated` に正規化。`stdout` は別に表示。
- Pythonでタイムアウト・stdoutサイズ・行数・メモリを制限。ImportやファイルI/Oの扱いはMVPの仕様に明記する。
- Pythonのソース内の単純な禁止語チェックだけでは安全性を保証できないため、それに依存しない。

### SQL

- 公式教材との互換性を優先してPostgreSQLを使用。
- MVPの一般的なSELECT問題では、DB権限を最小にして `BEGIN READ ONLY` / `SET LOCAL statement_timeout` 等を組み合わせ、更新を拒否する。
- 「SELECTだから安全」という文字列判定に頼らず、DBロール権限・トランザクション制御を安全性の基礎にする。
- 結果を取得しすぎないよう件数・実行時間・出力サイズを制限。表示用の最初のN行と採点用の検査対象を明確に区別する。
- SQL更新/テーブル作成やCSV出力を要する後半問題は、専用スナップショット・一時schema・ロールバック等、設問に合う隔離策をPhase 3以降に追加。
- Postgresパスワードや接続情報をPythonコード実行ワーカーに渡さない。

## 5. 自動採点（最重要）

### 基本方針

**コード文字列ではなく実行結果を判定**。デフォルトは参照結果との比較、必要に応じて問題固有の性質をテスト。

### 共通比較器

- DataFrame: 列名、列順（必要なときのみ）、行数、行の多重集合（重複を保持）、NULL、データ型の意味、値、浮動小数点の許容誤差を比較。
- 順序指定あり: 行順を比較。指定なし: 順不同で比較。順不同時も重複を落とさない。
- スカラー: 値と型、浮動小数点の誤差を比較。
- タイムスタンプ/日付/文字列: 正規化ルールを明記。`00123`のようなコード値のゼロ埋めを壊さない。
- SQL・Python間で戻り値の型や表現が異なる場合、問題仕様に沿う範囲だけで正規化。過度な緩和はしない。
- 採点前に正解の参照結果を**原教材の模範解答の実行で生成して確認**する。模範解答自身の仕様不整合があれば記録する。

### 判定方式

| strategy | 内容 | 用途 |
| --- | --- | --- |
| `dataframe_exact` | スキーマ・多重集合・指定順序の比較 | 抽出・ソート・結合等 |
| `numeric_tolerance` | 誤差つきの値比較 | 平均・標準化等 |
| `property_based` | 不変条件・統計的条件 | ランダムサンプリング、複数解が成立する問題 |
| `artifact_check` | 生成ファイルやDB状態の検証 | 入出力・更新系（後期） |
| `manual_review` | 自動的に正誤断定しない | 未対応/非決定的な問題 |

### 具体的テストケース

- 同じ答えを返す異なる構文→合格
- 正しい行数だが値が違う→不合格
- 意味のない列欠落→不合格（必要列の場合）
- ソート不要の問題で行順だけ変化→合格
- ソート必須の問題で行順違い→不合格
- 重複を不当に除外→不合格
- NULL・NaN・float誤差を正しく扱う
- 無限ループ、巨大出力、悪意ある更新SQL→タイムアウト/拒否して教材を壊さない

**限界**: 原データ1つに対する結果一致は全入力での意味的等価性を保証しない。必要なら追加の隠しテストデータ、構造的な検査、固有バリデータを使う。未整備なら `manual_review` とする。

## 6. 進捗データモデル（案）

SQLiteを用い、最低限以下を持つ：

- `exercise_status(exercise_id, language, state, last_code, first_passed_at, last_attempted_at, updated_at)`
  - 一意キー: `(exercise_id, language)`
- `attempts(id, exercise_id, language, code, mode, execution_status, grading_status, feedback_summary, created_at)`
  - 実行のたびに記録し、採点時のみ `grading_status` を設定
- `bookmarks(exercise_id, language, needs_review, updated_at)` は必要に応じて追加

マイグレーション可能な形で実装。保存時には原子性を持たせ、コード入力の自動保存（デバウンス等）を検討。コマンド `docker compose down` ではvolumeを削除しない。

## 7. セキュリティ・可用性

**脅威モデル**: 最初は本人が書いたコードだけをローカルで実行する。悪意ある第三者のコードを受け付けるインターネット公開サービスとして安全とは主張しない。

- UI: `127.0.0.1:8501` バインド。認証なしのインターネット公開は禁止。
- Worker: 別コンテナ、非root、`cap_drop: ALL`、読み取り専用ルートFS、必要なtmpfs、CPU/メモリ/PID制限、権限制限、不要な秘密情報・ボリューム無し。
- Workerネットワーク: UIとワーカーだけの内部ネットワーク。DBに接続できないようネットワークを分割。workerへのホスト公開ポートなし。
- **Docker socketはアプリコンテナに渡さない**。ワーカー実行のための特権Docker操作をアプリからしない。
- Workerのsubprocess timeoutとワーカーコンテナリソース上限の両方を設ける。処理中断やkill可能性をテスト。
- SQL: read-only role / read-only transaction / `statement_timeout` 等。DBもホスト公開しない。
- UIのログ/採点結果: 長い標準出力、巨大表、traceback、機密文字列の露出を制限する。
- 学習履歴をGit管理対象から除外。

## 8. 配布と検証

- 最終的な利用フローは `git clone` → `docker compose up --build` → `http://127.0.0.1:8501` を目指す。
- Composeの永続volume、初期データ投入、healthcheck、バインドポートをREADMEに明記。
- 初期化完了前にSQLを実行しないよう依存/healthcheckを設ける。
- テストコマンド例（作成後に確定）: `pytest`, `docker compose config`, `docker compose up --build -d`, E2E smoke test。
- ユーザーに紛らわしい破壊的コマンド（`docker compose down -v` 等）を案内するときは、履歴削除に注意書きを付ける。
