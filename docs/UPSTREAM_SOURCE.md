# 原教材の出典・ライセンス・取り込み方針

## 1. 公式ソース

- 作者: The Japan DataScientist Society（データサイエンティスト協会）
- 教材: データサイエンス100本ノック（構造化データ加工編）
- URL: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess
- 公式README: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess#readme
- 公式LICENSE: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess/blob/master/LICENSE
- 公式Compose: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess/blob/master/docker-compose.yml

### 公式READMEで確認済みの概要

- 演習はSQL、Python、Rの3言語共通の100問。
- `docker/work/` に演習Notebook、`docker/work/answer/` に解答例、`docker/work/data/` にCSV。
- `docker/db/init/` にDB初期化スクリプト、Docker Composeの設定あり。
- 個人情報らしいデータはダミー。
- 団体・組織での利用については出典明示が求められている。
- README記載では `docker/doc/100knocks_guide.pdf` はCC BY-ND、その他はMIT。

### 出典表示（READMEに掲載する例）

> 本プロジェクトは、一般社団法人データサイエンティスト協会 スキル定義委員会公開の「データサイエンス100本ノック（構造化データ加工編）」を教材として使用しています。
> 原教材: https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess
> 原教材の著作権およびライセンスは原教材のライセンス表記に従います。
> 本プロジェクトは原団体による公式アプリ、承認・提携プロジェクトではありません。

実際に公開する際には、**取り込んだファイルに対して必要な著作権・ライセンス文書を同梱**する。自作部分のライセンスは別途決定する（MITを候補）。ガイドPDFや協会ロゴはMVPに同梱しない。

## 2. 元のDocker環境をそのまま採用しない理由

公式Composeは既存Notebook学習のための設定であり、このプロダクトの実行・履歴・採点分離を満たすわけではない。特に、Notebookの認証設定・DB初期設定のまま外部公開する構成は不可。公式の設定を無批判にコピーせず、必要なデータと初期化手順を取り込み、本アプリ専用の権限構成を作る。

## 3. Claude Codeの調査タスク

1. 公式リポジトリの **具体的なcommit hash** を記録。
2. 100問のID・順序・問題文の抽出元を調べる。Notebookセル構造は実物を確認。
3. Python/SQL模範解答の実行に必要な共通セットアップを特定。
4. CSVのサイズ、データ型、NULL、コード列、Postgresテーブル名を把握。
5. 利用するCSV・解答・問題文のファイル一覧を作る。
6. LICENSE本文、原著作権表示、除外ファイルの境界を改めて確認。
7. 取り込み（vendoring）方式とアップデート方法、バージョン固定方法を決める。
8. `THIRD_PARTY_NOTICES.md` 等の予定を決定し、実装進捗に合わせて追加。

## 4. スナップショット記録（開発時に記入）

| 記録項目 | 値 |
| --- | --- |
| upstream repository | The-Japan-DataScientist-Society/100knocks-preprocess |
| branch/tag | `master`（2026-10-17 shallow clone で確認） |
| commit hash | `81e637c5a9d003763dafbbabb91e070674342c2c`（2026-10-08 19:49 +0900, Merge PR #320） |
| question notebook(s) | `docker/work/preprocess_knock_Python.ipynb`, `docker/work/preprocess_knock_SQL.ipynb`（各100問、P-001〜P-100 / S-001〜S-100、番号は1対1対応） |
| answer notebook(s) | `docker/work/answer/ans_preprocess_knock_Python.ipynb`, `docker/work/answer/ans_preprocess_knock_SQL.ipynb` |
| dataset CSV(s) | `docker/work/data/` の category / customer / geocode / product / receipt / store（計約23MB、最大 geocode 12.8MB、UTF-8 BOM付き） |
| SQL init scripts | `docker/db/init/1_init.sql`（ユーザー作成）, `2_create_table.sh`（DDL）, `3_load.sql`（`COPY ... WITH CSV HEADER`） |
| 適用したLICENSE/NOTICE | 実施済み: 上流 `LICENSE` の原本を `upstream/100knocks-preprocess/` に同梱し、MIT部分・出典・同梱 commit を `THIRD_PARTY_NOTICES.md` に記載（ガイドPDF・ロゴは同梱しない） |
| データ型・問題採点の調査 | 冒頭12問と全100問の特徴スキャンを実施（下記 §6） |

## 6. 現物調査メモ（2026-10-17）

- **ライセンス**: 上流 `LICENSE` はMIT本文（Copyright (c) 2020 The Japan DataScientist Society）とCC BY-ND 4.0本文を併記。READMEにより CC BY-ND は `docker/doc/100knocks_guide.pdf` のみ、その他はMIT。→ Notebook由来の問題文・解答・CSVはMIT表示を保持すれば同梱可。ガイドPDF・ロゴは同梱しない。
- **問題文の構造**: Markdownセルに `> P-001: 問題文` 形式（複数行の箇条書き条件を含む）。直後のcode cellが解答欄（演習版は空、解答版は1つ以上の解答例。`# コード例1` 等のコメントや補足markdownあり）。
- **Python共通セットアップ**: 解答Notebook冒頭セル。環境変数 `PG_PORT` が無い場合は CSV を `encoding="utf-8-sig"` と文字列 `dtype`（customer_id, gender_cd, postal_cd, application_store_cd, status_cd, category_*_cd, product_cd, store_cd, prefecture_cd, tel_no, street）で読み込む分岐がある。→ 本アプリのPythonワーカーはこのCSV分岐を採用し、DB接続情報を持たせない。
- **SQL環境**: Postgresテーブル名は customer / category / product / receipt / store / geocode。コード列は `VARCHAR`。上流Postgresは `postgres:15.1-bullseye`（Notebook内表記は「PostgreSQL13」で不整合あり）。上流の `padawan` ユーザーは DB owner + `pg_read/write_server_files` 付与で、本アプリでは流用しない。
- **application_date の型（2026-10-18 判明）**: 上流のCSV分岐は `application_date` を型指定しておらず整数で読まれ、046 等の模範解答 `pd.to_datetime(...)` が誤った日時になる。問題文と主環境（DB: VARCHAR(8)）に合わせ、本アプリは文字列で読む（`worker/datasets.py`）。
- **上流Python環境**: Python 3.11, pandas 1.5.3, numpy 1.24.3, scikit-learn 1.5.0, imbalanced-learn 0.12.3, SQLAlchemy 1.4.46。
- **採点上の注意（簡易スキャン、確定ではない）**:
  - S-001/002/003/010/011 等は `ORDER BY` なし `LIMIT 10` → 行集合が非決定。
  - 乱数系: 075, 076, 089, 091
  - SQLでDDL/DML（CREATE TABLE等）を使う: 043, 080〜093
  - ファイル入出力: 094〜100
- **改行**: 上流 `.gitattributes` は `*.sh text eol=lf` のみ。

## 7. 同梱と抽出（2026-10-17 実施）

- 同梱先: `upstream/100knocks-preprocess/`（上流の相対パスを保持、無改変、14ファイル・約24MB）。sha256は同ディレクトリの `MANIFEST.json`。手順は `upstream/README.md`。
- 同梱しないもの: `docker/doc/` 一式（ガイドPDFはCC BY-ND。問題PDF/HTMLも不要）、R版Notebook、ER図PNG、上流のDocker設定。
- 抽出物: `exercises/catalog/problems.json`（問題文・TIPS・依存関係）、`answers.json`（模範解答・解説・共通セットアップ・閑話セル）。生成ツールは `tools/extract_problems.py`。
- Notebook構造の実測:
  - 見出しは `---\n> P-001: ...`。**P-043/044 は全角コロン `：`**。
  - 問題間に `TIPS:` のmarkdownセルあり（直前の問題の注記として扱う）。
  - 解答Notebookに番号なしの `P-閑話`（088の後、`del df_customer_1` 等）があり、問題とは分けて保持。
  - 解答Notebookには実行結果の出力が保存されている（Python 125セル、SQL 132セル）。参照結果の照合に利用できる。
- 上流の不整合: P-003（解答版の表現差のみ）、P-086（解答版の数式に `+` が欠落）。問題文は設問Notebookを正とする。
- 参照結果の照合（2026-10-18）: 001〜005 について、本アプリの実行結果（pandas 3.0.6 / PostgreSQL 16.15）が上流解答Notebookの保存出力と一致（Python: 行数と値、SQL: 行数と S-001 先頭行）。
- 上流解答と本アプリの違い（2026-10-18, Phase 3）:
  - SQL 094〜100 の解答は DBサーバー上のファイル（/tmp/data）に COPY する。本アプリは安全のためサーバー上のファイル入出力を許可せず、`COPY ... TO STDOUT` / `FROM STDIN` を使う（画面に案内）
  - SQL 092 の解答は customer_std から address 列を落としている（第三正規形への正規化として誤り）。本アプリは address を残す形を正とする
  - pandas 3 では Python 071〜073, 083, 084, 086 の解答が動かない（`Series[0]` の位置指定、`Series.view`）。参照は pandas 3 で動く書き方で用意
  - pandas 3 の `stack` は欠損の行を残すため、044 の上流解答は上流Notebookの出力と行数が異なる（欠損行あり/なしの両方を正解とする）
  - 043 は問題文の列順（女性・男性）と上流解答（男性・女性）が異なるため、両方を正解とする
- 前問への依存（検出結果）: 044←043, 057←056, 080←079, 086←085, 088←087, 094/095/096/099←093, 097←094, 098←096, 100←099。依存問題の実行には前問の成果物（`df_sales_summary` 等）のセットアップが必要で、Phase 3で扱う。

## 5. Windows環境での注意

公式リポジトリの過去のGitHub Issueには、Windowsの自動改行コード変換がSQL初期化等のシェルスクリプトの動作に影響する旨の議論がある。`core.autocrlf`、`.gitattributes` とDocker上の実際の改行を確認する。グローバルのGit設定を無断変更せず、必要なら本リポジトリに局所的な設定を導入する。
