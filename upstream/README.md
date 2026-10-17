# upstream/ — 原教材スナップショット

`100knocks-preprocess/` は原教材リポジトリの必要ファイルを、上流の相対パスのまま **無改変で** 同梱したものです。

- 取得元・commit・sha256: `100knocks-preprocess/MANIFEST.json`
- ライセンス: 上流の `LICENSE`（原本）と、ルートの `THIRD_PARTY_NOTICES.md` を参照
- このディレクトリ内のファイルは手で編集しないでください（`tests/unit/test_upstream_snapshot.py` で改変を検出します）。

## 更新手順

1. 上流をcloneし、採用するcommitをcheckoutする。
2. `tools/vendor_upstream.py` の `PINNED_COMMIT` を更新する。
3. `uv run python -m tools.vendor_upstream <clone_dir>` を実行する。
4. `uv run python -m tools.extract_problems` で問題定義を再生成し、差分と `uv run pytest` の結果を確認する。
5. `THIRD_PARTY_NOTICES.md` と `docs/UPSTREAM_SOURCE.md` のcommitを更新する。
