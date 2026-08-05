from __future__ import annotations

import argparse
from pathlib import Path


JA_START = "<!-- project-control-ja:start -->"
JA_END = "<!-- project-control-ja:end -->"
EN_START = "<!-- project-control-en:start -->"
EN_END = "<!-- project-control-en:end -->"

JA_BLOCK = f"""{JA_START}
## 所有・管理・ブランド

**設計・開発・管理：加藤星悟（[`@seigo-gace`](https://github.com/seigo-gace)）。**

公式リポジトリ、設計方針、公開版、外部提供物の採用、名称・ロゴなどの利用許可に関する最終決定権は、[`GOVERNANCE.md`](GOVERNANCE.md)に従ってプロジェクト所有者が保持します。

プログラムはMITライセンスで利用・改変・再配布できます。ただし、MITライセンスは、改変版や派生サービスを公式版として表示するための名称・ロゴ・ブランド利用権を与えません。詳細は[`TRADEMARK.md`](TRADEMARK.md)を参照してください。

外部提供には開発者証明への署名が必要です。実質的なコード、辞書、正解検証データ、設計、公開、安全性、管理規程の変更には、統合前にプロジェクト所有者が受領した[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)が必要です。
{JA_END}"""

EN_BLOCK = f"""{EN_START}
## Ownership, governance, and brand

**Created, designed, developed, and maintained by Seigo Kato ([`@seigo-gace`](https://github.com/seigo-gace)).**

Under [`GOVERNANCE.md`](GOVERNANCE.md), the Project Owner retains final authority over the official repository, architecture, releases, contribution acceptance, and permission to use names, logos, and other Project Marks.

Program code may be used, modified, and redistributed under the MIT License. The MIT License does not authorize modified forks, products, or services to present themselves as official through project names, logos, or branding. See [`TRADEMARK.md`](TRADEMARK.md).

External contributions require DCO sign-off. Substantive code, dictionary, Gold data, design, release, security, or governance changes require a Project-Owner-accepted [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md) before merge.
{EN_END}"""


def _replace_marked_block(text: str, start: str, end: str, block: str) -> str:
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != 1 or end_count != 1:
        raise ValueError(
            f"README marker count invalid: {start}={start_count} / {end}={end_count}"
        )
    prefix, remainder = text.split(start, 1)
    _, suffix = remainder.split(end, 1)
    return prefix + block + "\n\n" + suffix.lstrip("\n")


def synchronize_japanese(text: str) -> str:
    return _replace_marked_block(text, JA_START, JA_END, JA_BLOCK)


def synchronize_english(text: str) -> str:
    return _replace_marked_block(text, EN_START, EN_END, EN_BLOCK)


def _synchronize_path(path: Path, synchronize, *, check: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = synchronize(original)

    if check:
        if updated != original:
            raise SystemExit(
                f"{path} project-control section is missing or stale. "
                "Run: python scripts/sync_project_control_readme.py"
            )
        return False

    if updated == original:
        return False

    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ja-path", default="README.md")
    parser.add_argument("--en-path", default="README_EN.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed_ja = _synchronize_path(
        Path(args.ja_path), synchronize_japanese, check=args.check
    )
    changed_en = _synchronize_path(
        Path(args.en_path), synchronize_english, check=args.check
    )

    if args.check:
        print("README PROJECT CONTROL OK: Japanese and English")
        return 0

    if not changed_ja and not changed_en:
        print("README PROJECT CONTROL ALREADY CURRENT: Japanese and English")
        return 0

    changed = []
    if changed_ja:
        changed.append(args.ja_path)
    if changed_en:
        changed.append(args.en_path)
    print("README PROJECT CONTROL UPDATED: " + ", ".join(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
