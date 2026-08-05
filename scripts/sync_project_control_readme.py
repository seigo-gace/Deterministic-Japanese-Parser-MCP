from __future__ import annotations

import argparse
from pathlib import Path

TOP_START = "<!-- project-control-top:start -->"
TOP_END = "<!-- project-control-top:end -->"
JA_START = "<!-- project-control-ja:start -->"
JA_END = "<!-- project-control-ja:end -->"
EN_START = "<!-- project-control-en:start -->"
EN_END = "<!-- project-control-en:end -->"

TOP_BLOCK = f"""{TOP_START}
<p align=\"center\">
  <strong>Created and maintained by Seigo Kato (<a href=\"https://github.com/seigo-gace\">@seigo-gace</a>).</strong><br>
  <strong>設計・開発・管理：加藤星悟（<a href=\"https://github.com/seigo-gace\">@seigo-gace</a>）</strong><br>
  Official project direction, releases, contribution acceptance, and brand permissions are controlled by the Project Owner.
</p>

<p align=\"center\">
  <a href=\"MAINTAINERS.md\">Owner &amp; Maintainers</a> ｜
  <a href=\"GOVERNANCE.md\">Governance</a> ｜
  <a href=\"TRADEMARK.md\">Trademark Policy</a> ｜
  <a href=\"CONTRIBUTING.md\">Contributing</a> ｜
  <a href=\"CONTRIBUTOR_LICENSE_AGREEMENT.md\">CLA</a>
</p>
{TOP_END}"""

JA_BLOCK = f"""{JA_START}
### Project Owner・Brand・Governance

**設計・開発・管理：加藤星悟（[`@seigo-gace`](https://github.com/seigo-gace)）。** 公式Repository、Roadmap、Architecture、Release、Contribution採択、Project Marksの使用許可に関する最終決定権は、[`GOVERNANCE.md`](GOVERNANCE.md)に従ってProject Ownerが保持します。

Program CodeはMIT Licenseで無料利用・改変・再配布できます。ただし、MIT Licenseは`Deterministic Japanese Parser MCP`、`DJPMCP`、`Shiori MCP Server`、公式Logo、`Astera`等のBrandを使って、改変Fork・製品・Serviceを公式と表示する権利を与えません。Brand利用は[`TRADEMARK.md`](TRADEMARK.md)に従います。

外部ContributionはDCOが必須です。実質的なCode、辞書、Gold、設計、Release、Security、Governance変更は、Merge前にProject Ownerが受領した[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)を必要とします。詳細は[`CONTRIBUTING.md`](CONTRIBUTING.md)を参照してください。
{JA_END}

"""

EN_BLOCK = f"""{EN_START}
### Project ownership, brand, and governance

**This project was created and is maintained by Seigo Kato ([`@seigo-gace`](https://github.com/seigo-gace)).** Under [`GOVERNANCE.md`](GOVERNANCE.md), the Project Owner retains final authority over the official repository, roadmap, architecture, releases, contribution acceptance, and permissions to use Project Marks.

Program code is free to use, modify, and redistribute under the MIT License. The MIT License does not authorize a modified fork, product, service, package, account, or organization to present itself as official by using `Deterministic Japanese Parser MCP`, `DJPMCP`, `Shiori MCP Server`, official logos, `Astera`, or other Project Marks. Brand use is governed by [`TRADEMARK.md`](TRADEMARK.md).

External contributions require DCO sign-off. Substantive code, dictionary, Gold, design, release, security, or governance contributions require a Project-Owner-accepted [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md) before merge. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
{EN_END}

"""


def _insert_once(text: str, marker: str, block: str) -> str:
    if marker not in text:
        raise ValueError(f"README anchor not found: {marker!r}")
    return text.replace(marker, block + marker, 1)


def _replace_marked_block(text: str, start: str, end: str, block: str) -> str:
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != 1 or end_count != 1:
        raise ValueError(
            f"README marker count invalid: {start}={start_count} / {end}={end_count}"
        )
    prefix, remainder = text.split(start, 1)
    _, suffix = remainder.split(end, 1)
    return prefix + block + suffix


def synchronize(text: str) -> str:
    updated = text

    if TOP_START not in updated and TOP_END not in updated:
        badge_boundary = "</p>\n\n---\n\n<a id=\"日本語\"></a>"
        replacement = f"</p>\n\n{TOP_BLOCK}\n\n---\n\n<a id=\"日本語\"></a>"
        if badge_boundary not in updated:
            raise ValueError("README badge boundary not found")
        updated = updated.replace(badge_boundary, replacement, 1)

    if JA_START not in updated and JA_END not in updated:
        updated = _insert_once(updated, "### License\n\n", JA_BLOCK)

    if EN_START not in updated and EN_END not in updated:
        english_anchor = "\n### License\n\nProgram code is MIT licensed."
        if english_anchor not in updated:
            raise ValueError("English License anchor not found")
        updated = updated.replace(
            english_anchor,
            "\n" + EN_BLOCK + "### License\n\nProgram code is MIT licensed.",
            1,
        )

    updated = _replace_marked_block(updated, TOP_START, TOP_END, TOP_BLOCK)
    updated = _replace_marked_block(updated, JA_START, JA_END, JA_BLOCK)
    updated = _replace_marked_block(updated, EN_START, EN_END, EN_BLOCK)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="README.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    original = path.read_text(encoding="utf-8")
    updated = synchronize(original)

    if args.check:
        if updated != original:
            raise SystemExit(
                "README project-control section is missing or stale. "
                "Run: python scripts/sync_project_control_readme.py"
            )
        print("README PROJECT CONTROL OK")
        return 0

    if updated == original:
        print("README PROJECT CONTROL ALREADY CURRENT")
        return 0

    path.write_text(updated, encoding="utf-8", newline="\n")
    print("README PROJECT CONTROL UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
