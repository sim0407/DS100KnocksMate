"""上流教材（100knocks-preprocess）の必要ファイルを固定commitから同梱するツール。

使い方:
    git clone https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess <clone_dir>
    git -C <clone_dir> checkout <PINNED_COMMIT>
    uv run python -m tools.vendor_upstream <clone_dir>

clone先のHEADが PINNED_COMMIT と一致しない場合は中止する。
コピー後、各ファイルのsha256を MANIFEST.json に記録する（tests/unit/test_upstream_snapshot.py で検証）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

UPSTREAM_REPO = "https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess"
PINNED_COMMIT = "81e637c5a9d003763dafbbabb91e070674342c2c"

# 同梱するファイル（上流での相対パスをそのまま保持する）。
# docker/doc/100knocks_guide.pdf は CC BY-ND のため同梱しない。
VENDORED_FILES = [
    "LICENSE",
    "docker/work/preprocess_knock_Python.ipynb",
    "docker/work/preprocess_knock_SQL.ipynb",
    "docker/work/answer/ans_preprocess_knock_Python.ipynb",
    "docker/work/answer/ans_preprocess_knock_SQL.ipynb",
    "docker/work/data/category.csv",
    "docker/work/data/customer.csv",
    "docker/work/data/geocode.csv",
    "docker/work/data/product.csv",
    "docker/work/data/receipt.csv",
    "docker/work/data/store.csv",
    "docker/db/init/1_init.sql",
    "docker/db/init/2_create_table.sh",
    "docker/db/init/3_load.sql",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = PROJECT_ROOT / "upstream" / "100knocks-preprocess"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def head_commit(clone_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def vendor(clone_dir: Path, dest_dir: Path = DEST_DIR) -> dict:
    commit = head_commit(clone_dir)
    if commit != PINNED_COMMIT:
        raise SystemExit(f"commit不一致: clone={commit} pinned={PINNED_COMMIT}")

    files = []
    for rel in VENDORED_FILES:
        src = clone_dir / rel
        dst = dest_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        files.append({"path": rel, "sha256": sha256_of(dst), "size": dst.stat().st_size})

    manifest = {
        "repository": UPSTREAM_REPO,
        "commit": PINNED_COMMIT,
        "license_note": "docker/doc/100knocks_guide.pdf のみ CC BY-ND（同梱しない）。その他は MIT。",
        "files": files,
    }
    (dest_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clone_dir", type=Path, help="上流リポジトリをcloneしたディレクトリ")
    args = parser.parse_args(argv)
    manifest = vendor(args.clone_dir.resolve())
    total = sum(f["size"] for f in manifest["files"])
    print(f"vendored {len(manifest['files'])} files ({total:,} bytes) at {manifest['commit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
