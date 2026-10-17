# 依存ライブラリのライセンス一覧

利用者が自分のPCで Docker イメージをビルドするときにインストールされるパッケージと、そのライセンスです（本リポジトリはこれらを同梱・再配布していません）。各パッケージのメタデータから機械的に集計したもので、正確な条件は各パッケージのライセンス本文を確認してください。

- 改変せずに利用している、注意が必要なライセンス: `psycopg` / `psycopg-binary`（LGPL-3.0）、`certifi`（MPL-2.0）
- GPL 系のライセンスのパッケージは含まれていません（2026-10-18 時点）
- ベースイメージ: `python:3.12.13-slim`（Python: PSF License、OS: Debian の各パッケージ）、`postgres:16.15-trixie`（PostgreSQL License、OS: Debian の各パッケージ）

再生成の方法（イメージをビルドした後）:

```bash
docker run --rm -i --entrypoint python ds100knocks-app:latest - < tools/dependency_licenses.py
docker run --rm -i --entrypoint python ds100knocks-worker:latest - < tools/dependency_licenses.py
```

## アプリ（app コンテナ: Streamlit UI・採点・SQL実行）

| パッケージ | バージョン | ライセンス |
| --- | --- | --- |
| altair | 6.3.0 | BSD License |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT License |
| idna | 3.20 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD License |
| Jinja2 | 3.1.6 | BSD License |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| narwhals | 2.27.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.0.6 | BSD License |
| pillow | 12.3.0 | MIT-CMU |
| pip | 25.0.1 | MIT License |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psycopg | 3.3.6 | LGPL-3.0-only |
| psycopg-binary | 3.3.6 | LGPL-3.0-only |
| pyarrow | 26.0.0 | Apache-2.0 |
| pydeck | 0.9.3 | Apache License 2.0 |
| python-dateutil | 2.9.0.post0 | Apache Software License / BSD License |
| python-multipart | 0.0.32 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache Software License |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT License |
| sqlparse | 0.6.0 | BSD License |
| starlette | 1.8.0 | BSD-3-Clause |
| streamlit | 1.66.0 | Apache-2.0 |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchdog | 6.0.0 | Apache Software License |
| websockets | 17.2 | BSD-3-Clause |

## Python 実行ワーカー（worker コンテナ: 学習者の Python を実行）

| パッケージ | バージョン | ライセンス |
| --- | --- | --- |
| cloudpickle | 3.1.2 | BSD License |
| imbalanced-learn | 0.14.2 | MIT License |
| joblib | 1.6.0 | BSD-3-Clause |
| narwhals | 2.27.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pandas | 3.0.6 | BSD License |
| pip | 25.0.1 | MIT License |
| python-dateutil | 2.9.0.post0 | Apache Software License / BSD License |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| scipy | 1.18.1 | BSD License |
| six | 1.17.0 | MIT License |
| sklearn-compat | 0.1.6 | BSD License |
| threadpoolctl | 3.7.0 | BSD-3-Clause |
