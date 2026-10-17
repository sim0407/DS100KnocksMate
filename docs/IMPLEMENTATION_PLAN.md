# 実装ロードマップと完了条件

## 原則

- 最小の動く縦切りを先に作る。まず1問×2言語、その後、複数問・複数採点方式へ拡張。
- 動作確認なしの「実装完了」は認めない。未検証なら理由と検証手順を記録する。
- UIの見栄え・高度なダッシュボードより **実行の安全性、採点の正確性、保存の確実性** を優先。

## Phase 0 — 技術検証・原教材の調査

### タスク

- [x] 公式GitHubリポジトリを取得し、確認したcommit hashを記録（cloneできない場合は未検証として扱う）。
- [x] 原教材のディレクトリ構造、Python/SQL設問と模範解答Notebook、CSV、DB初期化スクリプトを確認。
- [ ] 問題IDの対応、カテゴリ、冒頭10問の仕様、日付やコード列の型変換ルールを整理。（ID対応・問題文・依存関係は抽出済み。型変換ルールは0-A④で実施。上流にカテゴリ情報はない）
- [x] MITライセンスとPDF例外、帰属表示方法、取り込み範囲を確認。
- [ ] 公式データをPostgresとpandasへロードできるか試す。
- [ ] 1件の模範解答でPython/SQL双方の期待出力を得る。
- [ ] PythonユーザーコードをUI外の隔離ワーカーで実行するPoC（タイムアウト、出力サイズ、エラー時挙動も）。
- [ ] Postgresのread-only role / transactionでSQLを実行し、更新が拒否されることを確認。
- [ ] 1問について参照結果との比較が成立するか検証。結果の順序、列型、NULL等を確認。
- [ ] 直近の実装設計でリスクがあれば `docs/DECISIONS_AND_RISKS.md` に追加。

### Done条件

- 採点に使用する実物の問題1件と期待出力が確認できている。
- UIと分離されたPython実行PoC、SQL読み取り専用PoCがある。
- 上流教材の取得・データロード方法が再現可能な手順として残っている。
- 問題スキーマ、検証器のインターフェース、Docker分離方針が簡潔に説明できる。

### Phase 0 着手計画（2026-10-17確定）

Docker未導入のため、Docker不要の 0-A を先行し、Docker Desktop導入後に 0-B を行う。各ステップの最後にテストを実行して結果を記録する。

**0-A（Docker不要・ローカル Python 3.12 / uv）**

1. ✅ `git init`、`.gitignore`（学習履歴・SQLite・`.env`・キャッシュ）、`.gitattributes`（`*.sh`/`*.sql` を LF 固定）、`pyproject.toml`（uv、Python 3.12固定、pytest/ruff）。
2. ✅ 上流の固定commitから CSV 6件と Notebook 4件を `upstream/` 相当の場所に同梱し、`THIRD_PARTY_NOTICES.md` にMIT表示とcommit hashを記録。
3. ✅ 問題抽出ツール：Notebookから `id / python問題文 / sql問題文 / 模範解答コード` を抽出し、カタログ（`exercises/catalog/problems.json` / `answers.json`）を生成。採点方式など手作業の定義は別ファイル（YAML、⑤⑦で作成）。まず100問の抽出件数・ID対応をテストで確認。
4. ✅ pandasのロード検証（`worker/datasets.py`、pandas 3.0.6 に確定）：公式dtype指定でCSVを読み込み、コード列のゼロ埋め保持・NULL・日付列を確認。
5. ✅ 比較器（TDD, `core/grading/compare.py`）：`dataframe_exact`（順序なし多重集合／順序あり）、N件ルール（部分集合判定）、index無視、型カテゴリ、NaN/NULL、float誤差。CLAUDE.mdの具体的テストケースを網羅。
6. ✅ Python実行ワーカーの中核（Docker外でも単体テスト可能な部分）：最後の式の値の取得、stdout捕捉、例外整形、結果のJSON正規化（行数・サイズ上限、pickle不使用）、子プロセス＋タイムアウト。
7. ✅ P-001〜005 のPython模範解答をワーカー経由で実行し参照結果を生成、別解・誤答で比較器が正しく判定することをテスト。（採点定義 `exercises/problems/00[1-5].toml`、`core/grading/grader.py`、統合テスト `tests/integration/test_grading_cases.py`。参照結果は上流Notebookの保存出力と照合済み）
8. ✅ SQLite進捗リポジトリ（TDD, `core/progress/repository.py`）：`exercise_status` / `attempts`、マイグレーション、再オープン後の復元。

**0-B（Docker Desktop導入後）**

9. （DB・worker・testsまで実装済み。app は Phase 1）Compose：`app`（Streamlit, 127.0.0.1:8501のみ公開）/ `worker`（内部ネットワーク、非root、`cap_drop: ALL`、read-only rootfs、tmpfs、CPU/メモリ/PID制限）/ `db`（Postgres 16、ホスト非公開、app用ネットワークのみ）。worker⇔db間は到達不可。
10. ✅ Postgres初期化（`docker/db/`、ビルド時に初期化。統合テスト41件）：上流DDLとCOPYを取り込み、SELECT権限のみの学習用ロールを作成。`BEGIN READ ONLY` + `statement_timeout` で更新・DDLが拒否されることを統合テストで確認。
11. ✅ S-001〜005 の模範解答で参照結果を生成し、比較器で判定できることを確認。
12. ✅（単体コンテナでのスモークに加え、compose構成で DB/インターネット到達不可・DB資格情報なし・読み取り専用FSを統合テストで確認）workerの隔離確認：無限ループ、巨大出力、メモリ過大、ネットワーク・DBへの到達試行が抑止されることを確認。

**Phase 0 Done判定**：上記の既存Done条件。0-Bが未実施の間は「Phase 0 部分完了（Docker依存部分は未検証）」と記録する。

## Phase 1 — 1問×Python/SQLでMVPの縦切り

### タスク

- [x] Streamlitの問題選択UI、言語切替、コードエディタを実装。（`app/main.py`）
- [x] Code Editorは導入前にメンテナンス状況と入力保持を確認。初期は `st.text_area` でもよい。（Phase 1 は `st.text_area`。2026-10-18 に既存部品を評価のうえ自前の軽量エディタ `app/editor.py` を導入、`st.text_area` は切替可能な代替として残す）
- [x] Python runnerの分離APIと出力JSON正規化を実装。
- [x] SQL runnerをread-only Postgresで実装。
- [x] 1問の検証器を作り、`実行` と `採点` を分離。（001〜005）
- [x] 採点結果に `passed` / `failed` / `manual_review` / `error` を設ける。
- [x] SQLiteに草稿・解答履歴・正解状態を保存。再起動後の復元を確認。（AppTest と compose down/up のE2Eで確認）
- [x] Docker Composeを用意し、UIのみlocalhostに公開。（`127.0.0.1:8501` のみ）
- [x] READMEにWindowsを含む起動手順、停止手順、履歴保存場所を記載。
- [x] 最小限のintegration testと手動スモークテストを実施。（統合テスト105件、E2Eスクリプト。ブラウザでの目視確認はユーザー待ち）

### Done条件

1. 学習者が1問をPythonで解き、その場で結果を確認し採点できる。
2. 同じ設問をSQLでも解き、実行・採点できる。
3. 正しい別解も受理、明らかな誤答は拒否できる。
4. 言語切替・アプリ再起動後、入力コードと正解状態が復元する。
5. 更新SQL・Python無限ループ等で教材とUIの稼働が守られる（検証可能な範囲で）。

## Phase 2 — 10問程度と採点器の一般化

### タスク

- [x] 公式教材から、まず実際の冒頭10問の定義を構築。（001〜010）
- [x] 共通比較器：DataFrame、スカラー、float、NULL、順序あり/なし、重複を実装。（+ 列名を問わない位置照合、1行1列の表を値として扱う）
- [x] 性質が異なる3〜5問の正解・誤答・別解を試し、一般化して10問へ拡張。（017/018 ソート上位N件、019 ランク、021/022 件数、023 集計、027 平均上位N件。020/029 は複数正解のため理由付き manual_review）
- [x] python/sqlの設問ID対応、カテゴリ、見出しを整理。（上流にカテゴリ情報はないため見出しは問題文の先頭行）
- [x] 未対応設問に対して明確な表示・ステータスを実装。（一覧の「採点未対応」表示、理由の表示、採点基準の注記）
- [x] UIに簡単な進捗集計を表示（言語別の正解数）。（サイドバー + 進捗一覧画面、自動採点対応のみの絞り込み）
- [x] 単体/統合テストを追加し、判定の偽陽性・偽陰性を検証。（採点ケース、全模範解答、上流Notebook保存出力との自動照合）

### Done条件

- 対象の10問程度でPython/SQLの実行と適切な採点が動く。
- 同じ結果を返す複数の書き方が正解扱いされる。
- 未対応・曖昧問題を誤って正解にしない。
- 自動テストで要点が回帰検査できる。

## Phase 3 — 100問対応・学習UXの改善

### タスク

- [x] 問題本文の取り込み手順・上流の出典・版を監査できるようにする。（`upstream/` の MANIFEST、`tools/`、上流との差分は UPSTREAM_SOURCE.md）
- [x] 100問を分類し、判定方式・データ依存・環境更新の要否で優先度を決める。
- [x] 非決定的な設問（乱数など）は性質のテストやseed扱いを設計。（089/091 は性質で採点、075/076 は理由付きで自動採点しない）
- [x] DB書き込み・ファイル入出力を要する問題は専用ワークスペース/検証器で扱う。（SQL書き込み可能モード=一時テーブル＋ROLLBACK、Python は実行ごとの data フォルダ、COPY TO STDOUT/FROM STDIN）
- [x] 対象全問題の対応状況を一覧化。採点不能問題は理由を表示。（進捗一覧、自動採点 91問/言語、理由付き 9問）
- [x] ヒント・模範解答表示・復習フラグ・カテゴリ別進捗を追加。（段階的ヒント3段階・復習フラグ・進捗一覧。上流にカテゴリ情報がないためカテゴリ別は対象外）
- [ ] Python/SQLの学習内容を比較しやすいUIを追加。

### Done条件

- 100問の一覧と問題本文を表示し、すべての問題に採点対応状況が登録されている。
- 自動採点ができる問題では再現可能なテストがあり、できない問題は自己確認等の代替手段を示す。

## Phase 4 — 公開可能なOSSに整備

### タスク

- [x] README：目的、画面例、セットアップ、アンインストール、データ保存、学習方法。
- [x] 起動のハードルを下げる（start.bat/stop.bat は Windows で実機確認、start.command/stop.command は構文確認のみ・macOS 未確認。ビルド済みイメージ配布は見送り）：ダブルクリックで起動〜ブラウザ表示まで行う起動用ファイル（Windows `start.bat` / macOS `start.command`）。ビルド済みイメージ配布も検討（2026-10-18 ユーザー合意）。
- [x] `LICENSE`, `THIRD_PARTY_NOTICES`, 出典・原教材commitを整備。（MIT, sim0407。依存ライセンスは docs/DEPENDENCY_LICENSES.md）
- [x] `.gitignore` と秘密情報、DBデータ、ユーザー解答の混入を検査。（gitleaks で全履歴に検出なし。`.gitignore` の誤りで core/progress が未コミットだったのを発見・修正し、再発防止テストを追加）
- [x] Windows/Docker DesktopとmacOSで再現性を確認（未対応OSは明示）。（Windows は空の clone から起動・統合テストまで確認。macOS は実機がなく未確認と README に明記）
- [x] 依存関係・Dockerイメージの脆弱性検査、最小権限設定の見直し。（pip-audit で既知の脆弱性なし。Trivy でイメージを確認し、Python ベースイメージを 3.12.15 に更新して CRITICAL 0・修正版のある脆弱性 0 に。db は上流ベースイメージの更新待ち。db も cap_drop ALL・no-new-privileges。Dependabot を設定。手順は docs/RELEASE_CHECKLIST.md）
- [x] CIで単体・統合テスト、lintを実行。（.github/workflows/ci.yml。actionlint で検証、lint・単体ジョブは Linux コンテナで再現済み。GitHub 上での実行は push 後）
- [x] 公式団体の承認・提携によるサービスではないことを明記。（README・画面・THIRD_PARTY_NOTICES）
- [ ] **GitHubへの公開・pushはユーザーの最終承認後**。（2026-10-18 時点で未実施）

### Done条件

- 新規利用者がREADMEに従ってローカルで起動できる。
- リポジトリにライセンス違反・学習データの漏洩・認証情報混入がないと可能な範囲で確認済み。
- 未対応機能、安全上の制約、採点の保証範囲を透明に説明している。

## タスクの進行方法（Claude Code向け）

- 各Phaseを更に1〜3時間程度の小タスクに分けて作業してもよいが、見積りは保証しない。
- 各タスクの終了時にテストを走らせ、できなければ正確な障害を書き残す。
- 同じセッションで次Phaseへ進める場合でも、Phase完了条件を確認してから進む。
- データの破壊・ライセンスリスク・セキュリティリスクのある変更はユーザーの確認を得る。
