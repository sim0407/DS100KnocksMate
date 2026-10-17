"""同梱した上流教材がMANIFESTどおり（改変・欠落なし）であることを検証する。"""

import hashlib
import json
from pathlib import Path

import pytest

from tools.vendor_upstream import PINNED_COMMIT, VENDORED_FILES

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "upstream" / "100knocks-preprocess"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((SNAPSHOT_DIR / "MANIFEST.json").read_text(encoding="utf-8"))


def test_manifest_pins_expected_commit(manifest):
    assert manifest["commit"] == PINNED_COMMIT


def test_manifest_lists_exactly_vendored_files(manifest):
    assert [f["path"] for f in manifest["files"]] == VENDORED_FILES


@pytest.mark.parametrize("rel", VENDORED_FILES)
def test_file_hash_matches_manifest(manifest, rel):
    entry = next(f for f in manifest["files"] if f["path"] == rel)
    data = (SNAPSHOT_DIR / rel).read_bytes()
    assert len(data) == entry["size"]
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_cc_by_nd_guide_pdf_is_not_vendored():
    assert not list(SNAPSHOT_DIR.rglob("*.pdf"))


def test_no_unlisted_files(manifest):
    listed = {f["path"] for f in manifest["files"]} | {"MANIFEST.json"}
    actual = {
        p.relative_to(SNAPSHOT_DIR).as_posix() for p in SNAPSHOT_DIR.rglob("*") if p.is_file()
    }
    assert actual == listed
