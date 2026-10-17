"""インストール済みのPythonパッケージとライセンスを Markdown の表で出力する。

コンテナ内で実行し、docs/DEPENDENCY_LICENSES.md を作る（手順は同ファイルの冒頭を参照）:
    docker run --rm -i <image> python - < tools/dependency_licenses.py
"""

from __future__ import annotations

from importlib.metadata import distributions


def license_of(dist) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]
    ]
    if classifiers:
        return " / ".join(sorted(set(classifiers)))
    text = (meta.get("License") or "").strip()
    first_line = text.splitlines()[0] if text else ""
    return first_line[:80] if first_line else "（記載なし）"


def main() -> None:
    rows = sorted(
        {(d.metadata["Name"], d.version, license_of(d)) for d in distributions()},
        key=lambda r: r[0].lower(),
    )
    print("| パッケージ | バージョン | ライセンス |")
    print("| --- | --- | --- |")
    for name, version, lic in rows:
        print(f"| {name} | {version} | {lic.replace('|', '/')} |")


if __name__ == "__main__":
    main()
