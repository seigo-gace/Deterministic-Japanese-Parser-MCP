#!/usr/bin/env python3
"""Collect every Web NDL Authorities topical-term authority via official SPARQL 1.1.

The NDLSH batch covers only its published subset. This collector targets all
authorities in the official topicalTerms scheme. It preserves every direct
URI/literal predicate-object pair and resolves SKOS-XL pref/alt labels.
SPARQL Results XML is requested explicitly so literal control characters are not
silently sanitized from a malformed JSON serialization. CSV remains a validated
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
import xml.etree.ElementTree as ET

ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"
SCHEME = "http://id.ndl.go.jp/auth#topicalTerms"
PAGE_SIZE = 1000
UA = "Deterministic-Japanese-Parser-MCP/Web-NDL-Authorities-collector"
SPARQL_NS = "http://www.w3.org/2005/sparql-results#"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

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


def empty_cell() -> dict[str, str]:
    return {"value": "", "term_type": "", "language": "", "datatype": ""}


def cell_value(row: dict[str, Any], variable: str) -> str:
    cell = row.get(variable)
    if not isinstance(cell, dict):
        return ""
    value = cell.get("value", "")
    return value if isinstance(value, str) else ""


def cell_meta(row: dict[str, Any], variable: str) -> dict[str, str]:
    cell = row.get(variable)
    if not isinstance(cell, dict):
        return empty_cell()
    result = empty_cell()
    for key in result:
        value = cell.get(key, "")
        result[key] = value if isinstance(value, str) else ""
    return result


def parse_sparql_xml(raw: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        preview = raw[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"SPARQL Results XML is not well formed: {exc}; preview={preview!r}") from exc
    if root.tag != f"{{{SPARQL_NS}}}sparql":
        raise RuntimeError(f"unexpected SPARQL XML root: {root.tag}")
    variables = [
        element.attrib.get("name", "")
        for element in root.findall(f"./{{{SPARQL_NS}}}head/{{{SPARQL_NS}}}variable")
    ]
    if not variables or any(not variable for variable in variables):
        raise RuntimeError(f"SPARQL XML head variables invalid: {variables}")
    rows: list[dict[str, Any]] = []
    for result_index, result in enumerate(
        root.findall(f"./{{{SPARQL_NS}}}results/{{{SPARQL_NS}}}result"), 1
    ):
        row: dict[str, Any] = {variable: empty_cell() for variable in variables}
        for binding in result.findall(f"{{{SPARQL_NS}}}binding"):
            name = binding.attrib.get("name", "")
            if not name or name not in row:
                raise RuntimeError(
                    f"SPARQL XML binding variable unexpected: result={result_index} name={name!r}"
                )
            children = list(binding)
            if len(children) != 1:
                raise RuntimeError(
                    f"SPARQL XML binding must contain one term: result={result_index} name={name!r} children={len(children)}"
                )
            term = children[0]
            term_type = term.tag.rsplit("}", 1)[-1]
            if term_type not in {"uri", "literal", "bnode"}:
                raise RuntimeError(
                    f"SPARQL XML term type unsupported: result={result_index} name={name!r} type={term_type!r}"
                )
            row[name] = {
                "value": term.text or "",
                "term_type": term_type,
                "language": term.attrib.get(XML_LANG, ""),
                "datatype": term.attrib.get("datatype", ""),
            }
        rows.append(row)
    return rows


def parse_sparql_csv(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise RuntimeError("SPARQL CSV response has no header")
    rows: list[dict[str, Any]] = []
    for row in reader:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized[str(key)] = {
                "value": value or "",
                "term_type": "csv-untyped",
                "language": "",
                "datatype": "",
            }
        rows.append(normalized)
    return rows


def parse_sparql_response(raw: bytes, content_type: str) -> tuple[list[dict[str, Any]], str]:
    stripped = raw.lstrip()
    folded_type = content_type.casefold()
    if "xml" in folded_type or stripped.startswith(b"<?xml") or stripped.startswith(b"<sparql"):
        return parse_sparql_xml(raw), "sparql-results-xml"
    if "json" in folded_type or stripped.startswith(b"{"):
        preview = raw[:300].decode("utf-8", errors="replace")
        raise RuntimeError(
            "NDL returned JSON although output=xml was requested; JSON is not accepted because "
            f"the endpoint previously emitted invalid unescaped control characters. preview={preview!r}"
        )
    if "csv" in folded_type or b"," in raw[:1024]:
        return parse_sparql_csv(raw), "csv-fallback"
    preview = raw[:300].decode("utf-8", errors="replace")
    raise RuntimeError(
        f"unsupported SPARQL response format: content_type={content_type!r} preview={preview!r}"
    )


def request_rows(query: str, *, retries: int = 6) -> tuple[list[dict[str, Any]], str]:
    payload = urlencode({"query": query, "output": "xml"}).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=payload,
        headers={
            "User-Agent": UA,
            "Accept": "application/sparql-results+xml, application/xml;q=0.9, text/csv;q=0.3",
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
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
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
    labels: dict[str, dict[str, str]] = {}
    for row in base_rows:
        uri = cell_value(row, "uri").strip()
        label = cell_value(row, "label").strip()
        if not uri or not label:
            raise RuntimeError(f"base topical row incomplete: {row}")
        label_meta = cell_meta(row, "label")
        if uri not in labels:
            uri_order.append(uri)
            labels[uri] = label_meta
        elif labels[uri] != label_meta:
            raise RuntimeError(f"multiple rdfs:label values for {uri}: {labels[uri]!r} vs {label_meta!r}")

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
            label_meta = labels[uri]
            handle.write(
                json.dumps(
                    {
                        "uri": uri,
                        "label": label_meta["value"],
                        "label_language": label_meta["language"],
                        "label_datatype": label_meta["datatype"],
                        "label_term_type": label_meta["term_type"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    direct_path = output_root / "topical-direct-triples.jsonl"
    seen_direct: set[tuple[str, str, str, str, str, str]] = set()
    with direct_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in direct_rows:
            uri = cell_value(row, "uri")
            predicate = cell_value(row, "predicate")
            object_meta = cell_meta(row, "object")
            obj = object_meta["value"]
            if not uri or not predicate or not obj:
                raise RuntimeError(f"direct topical triple incomplete: {row}")
            key = (
                uri,
                predicate,
                obj,
                object_meta["term_type"],
                object_meta["language"],
                object_meta["datatype"],
            )
            if key in seen_direct:
                continue
            seen_direct.add(key)
            handle.write(
                json.dumps(
                    {
                        "uri": uri,
                        "predicate": predicate,
                        "object": obj,
                        "object_term_type": object_meta["term_type"],
                        "object_language": object_meta["language"],
                        "object_datatype": object_meta["datatype"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    def write_labels(path: Path, rows: list[dict[str, Any]], label_type: str) -> int:
        seen: set[tuple[str, str, str, str, str, str, str]] = set()
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                uri = cell_value(row, "uri").strip()
                literal_meta = cell_meta(row, "literal")
                yomi_meta = cell_meta(row, "yomi")
                literal = literal_meta["value"].strip()
                yomi = yomi_meta["value"].strip()
                if not uri or not literal:
                    raise RuntimeError(f"{label_type} label row incomplete: {row}")
                key = (
                    uri,
                    literal,
                    yomi,
                    literal_meta["language"],
                    literal_meta["datatype"],
                    yomi_meta["language"],
                    yomi_meta["datatype"],
                )
                if key in seen:
                    continue
                seen.add(key)
                handle.write(
                    json.dumps(
                        {
                            "uri": uri,
                            "literal": literal,
                            "literal_language": literal_meta["language"],
                            "literal_datatype": literal_meta["datatype"],
                            "yomi": yomi,
                            "yomi_language": yomi_meta["language"],
                            "yomi_datatype": yomi_meta["datatype"],
                            "label_type": label_type,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
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
        "collection_method": "official SPARQL 1.1 endpoint; PAGE_SIZE=1000; OFFSET pagination; output=xml; SPARQL Results XML primary with CSV fallback",
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
