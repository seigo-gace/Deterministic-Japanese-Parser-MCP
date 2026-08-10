#!/usr/bin/env python3
"""Evidence-driven discovery for the Ministry of Justice legal dictionary download.

The public download page renders controls dynamically. This tool does not guess a
file URL. It records the page HTML digest, forms, select/options, same-origin scripts,
and download-related strings from those scripts so a versioned source endpoint can
be locked from observed evidence before the dictionary itself is normalized.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA = "Deterministic-Japanese-Parser-MCP/legal-dictionary-source-discovery"
DOWNLOAD_PAGE = "https://www.japaneselawtranslation.go.jp/ja/dicts/download"
DTD_PAGE = "https://www.japaneselawtranslation.go.jp/ja/infos/dtd"
ORIGIN = "https://www.japaneselawtranslation.go.jp"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        content_type = response.headers.get("content-type", "")
    return payload, content_type


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.inputs: list[dict[str, str]] = []
        self.selects: list[dict[str, Any]] = []
        self.scripts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._current_form: int | None = None
        self._current_select: int | None = None
        self._current_option: dict[str, str] | None = None

    @staticmethod
    def attrs_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self.attrs_map(attrs)
        if tag == "form":
            self.forms.append(
                {
                    "action": values.get("action", ""),
                    "method": values.get("method", "get").lower(),
                    "id": values.get("id", ""),
                    "class": values.get("class", ""),
                }
            )
            self._current_form = len(self.forms) - 1
        elif tag == "input":
            item = {
                "name": values.get("name", ""),
                "type": values.get("type", ""),
                "value": values.get("value", ""),
                "id": values.get("id", ""),
                "form_index": str(self._current_form) if self._current_form is not None else "",
            }
            self.inputs.append(item)
        elif tag == "select":
            self.selects.append(
                {
                    "name": values.get("name", ""),
                    "id": values.get("id", ""),
                    "form_index": self._current_form,
                    "options": [],
                }
            )
            self._current_select = len(self.selects) - 1
        elif tag == "option":
            self._current_option = {
                "value": values.get("value", ""),
                "selected": "selected" if "selected" in values else "",
                "text": "",
            }
        elif tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        elif tag == "a" and values.get("href"):
            self.links.append(
                {
                    "href": values.get("href", ""),
                    "text": "",
                    "id": values.get("id", ""),
                    "class": values.get("class", ""),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current_form = None
        elif tag == "select":
            self._current_select = None
        elif tag == "option" and self._current_option is not None:
            if self._current_select is not None:
                self.selects[self._current_select]["options"].append(self._current_option)
            self._current_option = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._current_option is not None:
            self._current_option["text"] = (
                self._current_option.get("text", "") + " " + text
            ).strip()
        if self.links:
            # Best-effort label collection only. URL evidence never depends on link text.
            last = self.links[-1]
            if len(last["text"]) < 500:
                last["text"] = (last["text"] + " " + text).strip()


def same_origin(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "www.japaneselawtranslation.go.jp"


def interesting_lines(text: str) -> list[str]:
    results: list[str] = []
    needles = (
        "dict",
        "download",
        "xml",
        "dtd",
        "version",
        "pdf",
        "csv",
        "xlsx",
        "file",
    )
    for line_number, line in enumerate(text.splitlines(), 1):
        folded = line.casefold()
        if not any(needle in folded for needle in needles):
            continue
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue
        results.append(f"{line_number}:{compact[:3000]}")
        if len(results) >= 1000:
            break
    return results


def discover(report_path: Path, evidence_root: Path) -> dict[str, Any]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    scripts_to_fetch: set[str] = set()
    combined_forms: list[dict[str, Any]] = []
    combined_selects: list[dict[str, Any]] = []
    combined_inputs: list[dict[str, Any]] = []
    combined_links: list[dict[str, str]] = []

    for page_url in (DOWNLOAD_PAGE, DTD_PAGE):
        payload, content_type = fetch(page_url)
        text = payload.decode("utf-8", errors="replace")
        parser = StructureParser()
        parser.feed(text)
        page_name = "dict-download" if page_url == DOWNLOAD_PAGE else "dict-dtd"
        html_path = evidence_root / f"{page_name}.html"
        html_path.write_bytes(payload)
        forms = []
        for form in parser.forms:
            item = dict(form)
            if item["action"]:
                item["absolute_action"] = urljoin(page_url, item["action"])
            forms.append(item)
        scripts = [urljoin(page_url, src) for src in parser.scripts]
        for script in scripts:
            if same_origin(script):
                scripts_to_fetch.add(script)
        links = []
        for link in parser.links:
            item = dict(link)
            item["absolute_href"] = urljoin(page_url, item["href"])
            if any(
                token in (item["href"] + " " + item["text"]).casefold()
                for token in ("download", "dict", "dtd", "xml")
            ):
                links.append(item)
        pages.append(
            {
                "url": page_url,
                "content_type": content_type,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "forms": forms,
                "selects": parser.selects,
                "inputs": parser.inputs,
                "scripts": scripts,
                "relevant_links": links,
                "evidence_path": str(html_path),
            }
        )
        combined_forms.extend(forms)
        combined_selects.extend(parser.selects)
        combined_inputs.extend(parser.inputs)
        combined_links.extend(links)

    script_reports: list[dict[str, Any]] = []
    for index, script_url in enumerate(sorted(scripts_to_fetch), 1):
        payload, content_type = fetch(script_url)
        text = payload.decode("utf-8", errors="replace")
        lines = interesting_lines(text)
        script_path = evidence_root / f"script-{index:03d}.txt"
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        script_reports.append(
            {
                "url": script_url,
                "content_type": content_type,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "interesting_line_count": len(lines),
                "evidence_path": str(script_path),
            }
        )

    candidate_urls: set[str] = set()
    for form in combined_forms:
        value = str(form.get("absolute_action") or "")
        if value and any(token in value.casefold() for token in ("dict", "download", "dtd")):
            candidate_urls.add(value)
    for link in combined_links:
        value = str(link.get("absolute_href") or "")
        if value:
            candidate_urls.add(value)

    report = {
        "status": "DOWNLOAD_ENDPOINT_DISCOVERY_EVIDENCE_CAPTURED",
        "pages": pages,
        "same_origin_scripts": script_reports,
        "forms": combined_forms,
        "selects": combined_selects,
        "inputs": combined_inputs,
        "candidate_urls_from_html": sorted(candidate_urls),
        "source_endpoint_locked": False,
        "version_18_seen_in_controls": any(
            "18.0" in json.dumps(select, ensure_ascii=False)
            for select in combined_selects
        ),
        "url_guessing_used": False,
        "llm_api_used": False,
        "web_scraping_used": False,
        "note": (
            "This is endpoint-discovery evidence only. The legal dictionary is not "
            "considered acquired until a concrete official response URL/request and "
            "payload digest are observed and locked."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    report = discover(args.report, args.evidence_root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
