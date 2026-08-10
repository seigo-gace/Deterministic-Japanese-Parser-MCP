#!/usr/bin/env python3
"""Collect every Web NDL Authorities topical-term authority via official SPARQL 1.1.

The NDLSH batch covers only its published subset. This collector targets all
authorities in the official topicalTerms scheme. It preserves every direct
URI/literal predicate-object pair and resolves SKOS-XL pref/alt labels.
SPARQL Results JSON is the primary response format; CSV remains a validated
fallback. Unknown response formats fail closed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"
SCHEME = "http://id.ndl.go.jp/auth#topicalTerms"
PAGE_SIZE = 1000
UA = "Deterministic-Japanese-Parser-MCP/Web-NDL-Authorities-collector"

PREFIXES = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
PREFIX ndl: <http://ndl.go.jp/dcndl/terms/>
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_sparql_json(raw: bytes) -> list[dict[str, str]]:
    value = json.loads(raw.decode("utf-8-sig", errors="strict"))
    if not isinstance(value, dict):
        raise RuntimeError("SPARQL JSON root is not an object")
    head = value.get("head") or {}
    results = value.get("results") or {}
    variables = head.get("vars") or []
    bindings = results.get("bindings") or []
    if not isinstance(variables, list) or not all(isinstance(item, str) for item in variables):
        raise RuntimeError(f"SPARQL JSON head.vars invalid: {variables!r}")
    if not isinstance(bindings, list):
        raise RuntimeError("SPARQL JSON results.bindings is not a list")
    rows: list[dict[str, str]] = []
    for row_number, binding in enumerate(bindings, 1):
        if not isinstance(binding, dict):
            raise RuntimeError(f"SPARQL JSON binding is not an object: row={row_number}")
        row: dict[str, str] = {}
        for variable in variables:
            cell = binding.get(variable)
            if cell is None:
                row[variable] = ""
                continue
            if not isinstance(cell, dict):
                raise RuntimeError(
                    f"SPARQL JSON binding cell invalid: row={row_number} variable={variable}"
                )
            cell_value = cell.get("value", "")
            if not isinstance(cell_value, str):
                raise RuntimeError(
                    f"SPARQL JSON binding value invalid: row={row_number} variable={variable}"
                )
            row[variable] = cell_value
        rows.append(row)
    return rows


def parse_sparql_response(raw: bytes, content_type: str) -> tuple[list[dict[str, str]], str]:
    stripped = raw.lstrip()
    folded_type = content_type.casefold()
    if "json" in folded_type or stripped.startswith(b"{"):
        return parse_sparql_json(raw), "sparql-results-json"
    if "csv" in folded_type or b"," in raw[:1024]:
        text = raw.decode("utf-8-sig", errors="strict")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames:
            raise RuntimeError("SPARQL CSV response has no header")
        rows = [
            {str(key): (value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
        return rows, "csv-fallback"
    preview = raw[:300].decode("utf-8", errors="replace")
    raise RuntimeError(
        f"unsupported SPARQL response format: content_type={content_type!r} preview={preview!r}"
    )


def request_rows(query: str, *, retries: int = 6) -> tuple[list[dict[str, str]], str]:
    payload = urlencode({"query": query}).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=payload,
        headers={
            "User-Agent": UA,
            "Accept": "application/sparql-results+json, application/json;q=0.9, text/csv;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=120) as response:
                raw = response.read()
                content_type = response.headers.get("content-type", "")
            return parse_sparql_response(raw, content_type)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 >= retries:
                break
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"SPARQL request failed after {retries} attempts: {last_error}")


def paginated(
    query_body: str,
    order_by: str,
    response_formats: Counter[str],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    offset = 0
    while True:
        query = f"{PREFIXES}\n{query_body}\nORDER BY {order_by}\nLIMIT {PAGE_SIZE} OFFSET {offset}"
        rows, response_format = request_rows(query)
        response_formats[response_format] += 1
        output.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.05)
    return output


def collect(output_root: Path, report_path: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    response_formats: Counter[str] = Counter()

    base_rows = paginated(
        f'''SELECT ?uri ?label WHERE {{
          ?uri skos:inScheme <{SCHEME}> ; rdfs:label ?label .
        }}''',
        "?uri",
        response_formats,
    )
    uri_order: list[str] = []
    labels: dict[str, str] = {}
    for row in base_rows:
        uri = row.get("uri", "").strip()
        label = row.get("label", "").strip()
        if not uri or not label:
            raise RuntimeError(f"base topical row incomplete: {row}")
        if uri not in labels:
            uri_order.append(uri)
            labels[uri] = label
        elif labels[uri] != label:
            raise RuntimeError(f"multiple rdfs:label values for {uri}: {labels[uri]!r} vs {label!r}")

    direct_rows = paginated(
        f'''SELECT ?uri ?predicate ?object WHERE {{
          ?uri skos:inScheme <{SCHEME}> ; ?predicate ?object .
          FILTER (isIRI(?object) || isLiteral(?object))
        }}''',
        "?uri ?predicate ?object",
        response_formats,
    )
    pref_rows = paginated(
        f'''SELECT ?uri ?literal ?yomi WHERE {{
          ?uri skos:inScheme <{SCHEME}> ; xl:prefLabel ?node .
          ?node xl:literalForm ?literal .
          OPTIONAL {{ ?node ndl:transcription ?yomi . }}
        }}''',
        "?uri ?literal ?yomi",
        response_formats,
    )
    alt_rows = paginated(
        f'''SELECT ?uri ?literal ?yomi WHERE {{
          ?uri skos:inScheme <{SCHEME}> ; xl:altLabel ?node .
          ?node xl:literalForm ?literal .
          OPTIONAL {{ ?node ndl:transcription ?yomi . }}
        }}''',
        "?uri ?literal ?yomi",
        response_formats,
    )

    base_path = output_root / "topical-authorities.jsonl"
    with base_path.open("w", encoding="utf-8", newline="\n") as handle:
        for uri in uri_order:
            handle.write(
                json.dumps({"uri": uri, "label": labels[uri]}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )

    direct_path = output_root / "topical-direct-triples.jsonl"
    seen_direct: set[tuple[str, str, str]] = set()
    with direct_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in direct_rows:
            item = (row.get("uri", ""), row.get("predicate", ""), row.get("object", ""))
            if not all(item):
                raise RuntimeError(f"direct topical triple incomplete: {row}")
            if item in seen_direct:
                continue
            seen_direct.add(item)
            handle.write(
                json.dumps({"uri": item[0], "predicate": item[1], "object": item[2]}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )

    def write_labels(path: Path, rows: list[dict[str, str]], label_type: str) -> int:
        seen: set[tuple[str, str, str]] = set()
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                uri = row.get("uri", "").strip()
                literal = row.get("literal", "").strip()
                yomi = row.get("yomi", "").strip()
                if not uri or not literal:
                    raise RuntimeError(f"{label_type} label row incomplete: {row}")
                key = (uri, literal, yomi)
                if key in seen:
                    continue
                seen.add(key)
                handle.write(
                    json.dumps({"uri": uri, "literal": literal, "yomi": yomi, "label_type": label_type}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                )
        return len(seen)

    pref_path = output_root / "topical-pref-labels.jsonl"
    alt_path = output_root / "topical-alt-labels.jsonl"
    pref_count = write_labels(pref_path, pref_rows, "pref")
    alt_count = write_labels(alt_path, alt_rows, "alt")

    base_set = set(uri_order)
    observed_direct_uris = {item[0] for item in seen_direct}
    missing_direct = sorted(base_set - observed_direct_uris)
    if missing_direct:
        raise RuntimeError(
            f"topical authorities missing direct triples: count={len(missing_direct)} sample={missing_direct[:20]}"
        )

    files = []
    for path in (base_path, direct_path, pref_path, alt_path):
        files.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    report = {
        "status": "COMPLETE_SPARQL_COLLECTION",
        "endpoint": ENDPOINT,
        "scheme": SCHEME,
        "topical_authorities": len(uri_order),
        "direct_triples": len(seen_direct),
        "pref_label_records": pref_count,
        "alt_label_records": alt_count,
        "response_format_pages": dict(sorted(response_formats.items())),
        "files": files,
        "attribution": "Web NDL Authorities（国立国会図書館典拠データ検索・提供サービス）から取得",
        "collection_method": "official SPARQL 1.1 endpoint; PAGE_SIZE=1000; OFFSET pagination; SPARQL Results JSON primary with CSV fallback",
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.output_root, args.report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
