#!/usr/bin/env python3
"""Download approved open dictionary dumps for offline import and pin evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

SOURCES = {
    "jawiktionary": {
        "url": "https://dumps.wikimedia.org/jawiktionary/latest/jawiktionary-latest-pages-articles.xml.bz2",
        "license": "CC-BY-SA-4.0 AND GFDL-1.3-or-later",
        "attribution": "Japanese Wiktionary contributors",
        "homepage": "https://ja.wiktionary.org/",
    },
    "wikidata-lexemes": {
        "url": "https://dumps.wikimedia.org/wikidatawiki/entities/latest-lexemes.json.bz2",
        "license": "CC0-1.0",
        "attribution": "Wikidata contributors",
        "homepage": "https://www.wikidata.org/wiki/Wikidata:Lexicographical_data",
    },
    "jmdict": {
        "url": "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz",
        "license": "CC-BY-SA-4.0",
        "attribution": "Electronic Dictionary Research and Development Group",
        "homepage": "https://www.edrdg.org/wiki/JMdict-EDICT_Dictionary_Project",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Deterministic-Japanese-Parser-MCP dictionary importer/0.3 "
                "(https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP)"
            )
        },
    )
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=output.name + ".",
        suffix=".partial",
        delete=False,
    ) as temp:
        temp_path = Path(temp.name)
        with urllib.request.urlopen(request, timeout=120) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                temp.write(chunk)
            headers = dict(response.headers.items())
    if temp_path.stat().st_size == 0:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"download produced an empty file: {url}")
    temp_path.replace(output)
    return headers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--url", help="Explicit reviewed mirror URL override")
    args = parser.parse_args()

    source = SOURCES[args.source]
    url = args.url or source["url"]
    headers = download(url, args.output)
    digest = sha256(args.output)
    if args.expected_sha256 and digest.lower() != args.expected_sha256.lower():
        args.output.unlink(missing_ok=True)
        raise RuntimeError(
            f"checksum mismatch: expected={args.expected_sha256} actual={digest}"
        )
    manifest_path = args.manifest or args.output.with_suffix(
        args.output.suffix + ".source.json"
    )
    payload = {
        "schema_version": "1.0.0",
        "source": args.source,
        "download_url": url,
        "homepage": source["homepage"],
        "license": source["license"],
        "attribution": source["attribution"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "filename": args.output.name,
        "bytes": args.output.stat().st_size,
        "sha256": digest,
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"FETCH OK: source={args.source} bytes={payload['bytes']} "
        f"sha256={digest} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
