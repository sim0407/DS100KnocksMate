# 決定事項・保留事項・リスク

## A. 合意済みの方針

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 問題集 | 公式100本ノック（構造化データ加工編） | 既存教材を活用 |
| 対象言語 | Python、SQL | 主要学習目的 |
| 使い方 | ローカルWebアプリ | 手軽な起動・結果確認 |
| UI | Streamlit | Pythonで構築できMVPが早い |
| SQL DB | PostgreSQL | 公式教材との互換性 |
| 履歴DB | SQLite | 単一ローカルユーザーに十分 |
| 配布 | Docker Compose / GitHub | 再現性、配布容易性 |
| 採点 | 実行結果・問題固有の条件で判定 | 別解を認められる |
| 実装順 | 少数問題の縦切り→一般化→100問 | リスクの早期発見 |
| 学習者コード | UIプロセスと分離 | 安定性・安全性 |

## B. 技術詳細としてClaude Codeが検証して決める事項

1. Python実行ワーカーのプロトコル（HTTP/ローカルRPC）と実行の境界。Docker socketを使わないことは必須。
2. コードエディタ（`st.text_area`、Ace、その他）の採用。MVPでは依存数を最小化。
3. 原教材を必要部分だけ取り込むか、初回セットアップで取得するか。出典・固定commit・ライセンス表示は必須。
4. 公式CSVの読み込み型とPostgres初期化（元の文字列コード・NULLを保護）。
5. SQL用のロール、DB接続制御、スナップショット運用。
6. Pythonの最後の式を自動表示するロジックと`result`変数の扱い。
7. 問題ごとの判定方式、行順・列順・数値誤差。公式問題を読んでから判断。
8. READMEの正確な起動コマンド、Docker DesktopでのWindows動作。

迷ったらMVPに不要な機能を増やさず、検証できる最小案を選ぶ。

## C. リスクと対策

| リスク | 影響 | 対策 |
| --- | --- | --- |
| 模範解答の出力に過適合する採点 | 偽陽性/偽陰性 | 別解・誤答テスト、問題固有の性質検証 |
| NULLや型、行順の比較ミス | 合っているのに不正解になる | 正規化・比較仕様をテストで固定 |
| ランダム処理やI/O問題を一律比較できない | 正解が判定できない | `manual_review`、専用バリデータ |
| 学習コードがUIをフリーズ/破壊 | 進捗喪失 | ワーカー隔離、リソース・時間制限、SQLite永続化 |
| Python実行環境からPostgresへ侵入 | 教材DB破壊 | 内部ネットワーク分割、資格情報を渡さない |
| SQLのUPDATEやDDLが残存データを破壊 | 学習体験の破綻 | read-only role/transaction、後期は隔離更新 |
| Docker隔離を過信 | 悪意ある外部コード実行の危険 | 信頼できる本人のローカルコードのみ扱い、公開ネットワークに設置しない |
| 学習データがGitHubへ混入 | プライバシー/品質事故 | `.gitignore`、Git history・秘密情報チェック |
| 原教材ライセンス誤解 | 公開・再配布停止 | MIT本文とCopyright、PDF例外確認、NOTICEに出典明示 |
| 上流教材の変更 | 再現性低下 | 取得時のcommit固定、依存・検証結果を保存 |
| Windowsの改行コードの差 | DB初期化失敗 | `.gitattributes` やLFの整合を検証 |

## E. 2026-10-17 確定事項（要件確定セッション）

### ユーザー確認済み

| 項目 | 決定 | 理由・補足 |
| --- | --- | --- |
| 開発環境のDocker | ユーザーがDocker Desktop（WSL2）を導入する。導入までは Docker不要部分（教材抽出・比較器・SQLite進捗）をローカルPython + pytestで先行し、Docker依存部分は導入後に検証 | 2026-10-17時点でPCにDocker未導入 |
| 「先頭N件表示」系の採点 | 列名・列順・行数Nが一致し、かつ各行が「LIMITを外した正しい全結果」に含まれれば正解（多重度も考慮） | SQLの `ORDER BY` なし `LIMIT` は行が非決定。厳密一致だと正答を誤って不正解にする |
| Python実行環境の版 | **Python 3.12 + pandas 3.0.6**, numpy 2.5.4, scikit-learn 1.9.1, imbalanced-learn 0.14.2, python-dateutil 2.9.0.post0（2026-10-17 ユーザー確認で確定） | 学習価値。模範解答の実行調査で 3.0.6 は 94/100 問が無修正で動作、2.3.3 は 100/100（警告8問）。3.0で失敗する 071/072/073/083/084/086 は `Series[0]`→`.iloc[0]`、`Series.view` 削除が原因で、3.0対応の参照解答を別途用意し上流との差分を記録する |
| 教材の取り込み | 固定commitから必要なCSV・抽出した問題定義をリポジトリに同梱。MIT表示とcommit hashを記録 | オフライン起動・テスト、再現性 |

### Claude判断の既定値（異議があれば変更可）

- **参照結果は言語ごと**: Python解答はPython模範解答の実行結果と、SQL解答はSQL模範解答の実行結果と比較する（言語間の型差を吸収しない）。
- **Pythonの結果取得**: Jupyterと同様に「コード最後の式の値」を採点対象とする。`print` は stdout として別表示。最後が式でない場合は「結果を返す式を最後に書いてください」と案内（`error` ではなく `failed` でもない専用メッセージ）。
- **DataFrameのindex**: 既定では比較しない（`reset_index` 相当で比較）。indexが意味を持つ問題のみ問題定義で有効化。
- **型の比較**: 厳密なdtype一致ではなく、意味カテゴリ（整数/浮動小数/文字列/日時/真偽）で比較。コード列のゼロ埋め文字列は数値化しない。
- **ソート必須問題**: 指定ソートキーの順序のみ検証し、同順位（tie）内の並びは問わない。
- **SQL**: Phase 1は単一文のみ。専用の SELECT 権限のみロール + `BEGIN READ ONLY` + `statement_timeout` を併用。更新系問題（043, 080〜093）はPhase 3まで `manual_review`/未対応表示。
- **Python実行環境の境界**: ワーカーはCSVから `df_*` を読み込み、Postgres接続情報・ネットワークを持たない。
- **Postgres版**: 16.15（`postgres:16.15-trixie` をダイジェスト固定、上流は15.1）、`ja_JP.UTF-8`。差異が出たら記録。
- **教材DBの構築**: イメージのビルド時に initdb・DDL・COPY・ロール設定まで実行し、初期化済みデータをイメージに含める（永続volumeなし、コンテナ再作成で常に初期状態、起動が速い）。
- **DBの認証**: 管理者 `postgres` はコンテナ内UNIXソケット（peer）のみ。学習者用 `knocks_learner` はSELECTのみ・TEMP不可・`default_transaction_read_only`・`statement_timeout` を固定し、内部ネットワークから scram 認証。パスワードは秘密情報扱いしない（非公開ネットワーク・読み取り専用のため）。
- **SQLの実行方式**: `DECLARE カーソル FOR <学習者SQL>` を prepared statement で送る（psycopg `prepare=True`）。実機検証で、SELECT系以外は構文エラー、複数文はサーバが拒否、`%` もそのまま扱えることを確認。FETCHで先頭N行、MOVEで総行数。psycopg の通常実行（パラメータなし）は複数文を実行してしまうため使わない。
- **エディタ**: Phase 1は `st.text_area`。保存は 実行/採点/言語・問題切替時、および入力確定（blur）時。ブラウザを閉じる直前の未確定入力は失われうる点をREADMEに明記。
- **Pythonワーカーの実行方式（確定・0-A⑥で検証済み）**: ライブラリと教材データを読み込み済みの常駐親プロセスから、実行ごとに `fork` した子プロセスでコードを実行（`worker/sandbox.py`）。子は setsid・実時間タイムアウトでプロセスグループごとSIGKILL・RLIMIT_CPU/FSIZE・新規一時ディレクトリ・`oom_score_adj=1000`・fd 0/1/2 を /dev/null。Linux専用で、fork系テストはWindowsではskipしコンテナ内で実行。
- **ワーカーのプロトコル**: 標準ライブラリの **シングルスレッド** `HTTPServer`（`worker/server.py`、POST /execute, GET /health）。マルチスレッドからのforkはデッドロックしうるため。ヘルスチェックはTCP接続の受付で判定。コンテナは `init: true`（ゾンビ回収）。学習者コードはログに出さない。
- **採点の実行場所**: ワーカーは「実行して結果を返す」だけ。比較はアプリ側（`core.grading.compare`）。参照結果は採点時に模範解答（subset_n/top_n では件数制限なし版）を同じランナーで実行して得てアプリ側でキャッシュ。巨大な期待値ファイルは置かず、回帰検出用に行数・ハッシュ等の指紋を `exercises/reference/` に保存する（0-A⑦）。
- **結果のindex**: 名前なしindexは捨て、名前付き/MultiIndex（groupbyキー等）は列に戻す。MultiIndex列は `_` で連結。
- **学習履歴（SQLite）**: `core/progress/repository.py`。状態は not_started / in_progress / passed、一度 passed になれば後の不正解で戻さない（直近結果は `last_grade_status`）。復習フラグは別属性。WALモード、操作ごとに接続・1トランザクション、`PRAGMA user_version` でマイグレーション。保存先はDockerの**名前付きvolume**（Windowsフォルダのbind mountはWALが不安定になりうるため使わない）。
- **UI（Phase 1）**: `app/main.py`（Streamlit 1.66.0）。画面に依存しない操作は `core/service.py`。エディタは `st.text_area`（保存は入力確定時・実行/採点時）。Streamlit の利用統計送信は無効（`.streamlit/config.toml`）。ローカル開発時の待受は 127.0.0.1、コンテナ内は 0.0.0.0 でホスト公開は compose で 127.0.0.1 のみ。
- **appコンテナのネットワーク**: ポート公開には internal でないネットワークが必要なため `frontnet` に接続（app のみ外向き通信が可能。学習者コードは app では実行しない）。
- **学習履歴volume**: 固定名をやめ `<プロジェクト名>_progress`（既定 `ds100knocks_progress`）。E2E確認は別プロジェクト名で行い、普段の学習履歴を汚さない。
- **採点定義の形式**: 設計書の YAML 案ではなく TOML（`exercises/problems/<id>.toml`、標準ライブラリ `tomllib` で読めて依存が増えずコメントも書ける）。キー: strategy / reference / rows / n / sort_keys / column_order / column_names / float_decimals / reason / note。未知のキーはエラー。
- **Phase 2 で追加した採点ルール**: 列名を問わない位置照合（`column_names=false`）、1行1列の表を値として採点、学習者向けの採点基準注記（`note`）。020（ROW_NUMBER）・029（最頻値）は正解が一意でないため理由付き manual_review。
- **参照結果の照合の自動化**: `tests/integration/test_reference_crosscheck.py` で、自動採点する全問題の模範解答の結果を上流解答Notebookの保存出力（Python: 行数/値、SQL: rows affected）と照合する。
- **コードエディタ（2026-10-18）**: 既存部品を評価（streamlit-ace: 2021年で停止、streamlit-code-editor: 2024年12月以降更新なし・PyPIにライセンス表記なし、streamlit-monaco: 2023年・Monacoは既定でCDN読込の恐れ、streamlit-monaco-editor: 実績少・CDN未確認）し、いずれも採用せず、Streamlit 1.66 の `st.components.v2` で **依存・CDNなしの自前エディタ**（`app/editor.py`）を実装。Tab/Shift+Tab、自動インデント、行番号、Ctrl+Enter実行、Esc→Tabでフォーカス移動、`execCommand('insertText')` で元に戻すを維持。`setStateValue` は呼ぶたびにスクリプトを再実行するため、送信は「入力欄から離れたとき・Ctrl+Enter・入力停止1.5秒後」。シンタックスハイライトは未対応。標準 `st.text_area`（シンプル）にサイドバーで切替可能。
- **ブラウザE2E**: AppTest は独自部品を操作できないため、Playwright（`e2e` 依存グループ、Chromium）で実ブラウザ確認（`tests/e2e/test_editor_browser.py`）。この過程で「選択欄のラベル変化でウィジェットが作り直され選択問題が001に戻る」不具合を発見し、`current_exercise` で選択を保持する方式に修正。
- **公開ポート**: `KNOCKS_PORT`（既定8501、常に 127.0.0.1 のみ）。E2E は 8502 で並行実行。
- **採点対象の拡大（2026-10-18）**: 62問/言語を自動採点。追加した仕組み: (1) `alternatives`（許容する別の参照。まず reference と比較し、不一致のときだけ順に試す。不正解の理由は reference との比較から作る）、(2) 日時の正規化（タイムゾーン付きはUTCへ、深夜0時は日付へ）、(3) Series の名前なし index が整数以外（列名などのラベル）なら列 `index` として残す、(4) 参照結果キャッシュを LRU（既定4件）に。実測で10万行級の参照を続けて採点してもアプリのメモリは約250MB。
- **application_date の型**: 上流CSV分岐では整数になるが、問題文と上流の主環境（DB）に合わせて文字列で読む（`worker/datasets.py`）。
- **上流解答セルの扱い**: 単独では完全な解答にならないセル（055の確認用・前セル依存・題意を満たさない参考、069の横持ち参考例）は「模範解答が正解になる」テストの対象外とし、理由を `tests/integration/test_grading_cases.py` に記載。
- **Phase 3（2026-10-18）残り29問の対応**: 追加した仕組み
  - `setup` / `setup_note`: 前の問題のデータを模範解答で用意（Python はワーカーで学習者コードの前に実行、出力は捨てる、失敗は SetupError。SQL は同じトランザクションで先に実行）
  - `artifacts`: 作成した変数/テーブルを採点（コード末尾に名前 / `SELECT * FROM 名前` を付加。見つからない場合は案内メッセージ）
  - SQL 書き込み可能モード（`writable`）: `sqlparse` で文に分割して順に実行、`search_path = pg_temp, public` で CREATE TABLE は一時スキーマへ、SELECT はカーソル経由、最後に ROLLBACK。学習者ロールに TEMPORARY 権限を追加（教材テーブルは SELECT のみのまま）。`COPY ... TO STDOUT` は files として回収、`COPY ... FROM STDIN` には `stdin_query` の出力を流す
  - Python の作業フォルダ: カレントは work/、`./data` と `../data` は同じ data/（上流解答の `../data` パスもそのまま動く）。`collect_files` で回収
  - `strategy = "file"`（`core/grading/files.py`）、`strategy = "custom"`（`core/grading/validators.py`: train_test_split, undersampling）、`key_columns`（先頭N列のみ比較）、NumPy 配列を表として扱う
- **依存の追加**: `sqlparse==0.6.0`（BSD、app グループ）
- **上流解答をテスト対象外にしたもの（理由は tests 内に記載）**: pandas 3 非互換（071〜073, 083, 084, 086 の Python）、確認用/前セル依存のセル、092 SQL の address 欠落（上流の誤り）、094〜100 SQL のサーバー上ファイル入出力
- **リスク（書き込み可能モード）**: 一時テーブルは statement_timeout（15秒）内であれば大きく作れるため、DBコンテナのディスクを一時的に使う。ローカル単一利用のため許容し、ROLLBACK/セッション終了で削除される
- **段階的ヒント（2026-10-18）**: `core/exercises/hints.py`。Python は ast で関数呼び出しを出現順に抽出、骨組みは tokenize で文字列・数値を「…」に（コメント除去）。SQL は sqlparse でキーワードと関数名を抽出（SELECT 等の基本語と、別名に使われやすい UNKNOWN は除外）、骨組みは識別子も「…」に（SQL は文字列・数値を含まない解答が多く、伏せないと解答そのものになるため）。元にするコードは、Python は動く最初の解答例、SQL は全セル（手順のため）。動かない解答例しかない場合は採点用参照コードを「pandas 3 で動く書き方の例」として表示。解答例への注記は `exercises/answer_notes.toml`。学習履歴に `hint_level` 列（スキーマ v2、既存データは自動移行）。
- **pyarrow**: 当面入れない（pandas 3 の文字列型はPython実装で動作）。性能問題が出たら再検討。
- **自作部分のライセンス**: MITを第一候補（Phase 4で最終確認）。名称は仮称のまま（リポジトリ名 `DS100KnocksMate` / 文書上の「100 Knocks Trainer」の統一はPhase 4）。

### 追加リスク

| リスク | 影響 | 対策 |
| --- | --- | --- |
| Docker未導入のまま進行 | 隔離・SQL安全性が未検証のまま機能が増える | Docker依存のDone条件は導入後まで「未検証」と明記し、Phase 1完了扱いにしない |
| モダンpandasで公式解答が動かない/結果が変わる | 参照結果を作れない | 参照結果生成時に全解答を実行し、失敗・警告を一覧化して問題ごとに調整 |
| pandas 3.0 で模範解答が無言で異なる結果を返す（例: 055 カテゴリ集計の `observed` 既定値変更） | 誤った参照結果で採点 | 参照結果生成時に、上流解答Notebookの保存済み出力（pandas 1.5.3時代）と照合し、差異を問題ごとに確認・記録 |
| ローカル開発のPython(3.14)と実行環境(3.12)の差 | 環境依存バグ | uvで3.12を固定してローカルテスト |

## D. 明示的な非決定事項

- サービス名、ロゴ、ブランドデザインは仮称。公式団体に見える表現は避ける。
- GitHubリポジトリの公開先（ユーザー自身が決定）。
- 完全な100問対応の期限。
- 他人に使わせる公開Webサービス化。初期構成をそのまま外部に公開しない。
