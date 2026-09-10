from __future__ import annotations

import argparse
from pathlib import Path


JA_START = "<!-- project-control-ja:start -->"
JA_END = "<!-- project-control-ja:end -->"
EN_START = "<!-- project-control-en:start -->"
EN_END = "<!-- project-control-en:end -->"

JA_BLOCK = f"""{JA_START}
プロジェクトの管理方針と名称・ロゴの扱いは[`GOVERNANCE.md`](GOVERNANCE.md)と[`TRADEMARK.md`](TRADEMARK.md)を参照してください。
{JA_END}"""

EN_BLOCK = f"""{EN_START}
See [`GOVERNANCE.md`](GOVERNANCE.md) and [`TRADEMARK.md`](TRADEMARK.md) for project governance and use of names and logos.
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
    normalized_suffix = suffix.lstrip("\n")
    separator = "\n\n" if normalized_suffix else "\n"
    return prefix + block + separator + normalized_suffix


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
