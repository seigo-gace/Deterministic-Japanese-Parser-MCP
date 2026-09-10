#!/usr/bin/env python3
"""Run the NDL topical collector with namespace-tolerant SPARQL Results XML parsing.

The official endpoint has returned SPARQL Results XML whose root is recognized but
whose child namespace layout does not match a fixed XPath. This runner replaces only
the XML decoder. It matches elements by local-name while preserving URI/literal/
bnode values, xml:lang and datatype exactly. Query, pagination, output generation
and validation stay in public_authority_sparql.py.
"""
from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

import public_authority_sparql as base

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def children_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def first_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if local_name(child.tag) == name:
            return child
    return None


def parse_sparql_xml_local(raw: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        preview = raw[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"SPARQL Results XML is not well formed: {exc}; preview={preview!r}") from exc
    if local_name(root.tag) != "sparql":
        raise RuntimeError(f"unexpected SPARQL XML root: {root.tag}")

    head = first_child(root, "head")
    results = first_child(root, "results")
    if head is None or results is None:
        raise RuntimeError(
            f"SPARQL XML missing head/results: child_tags={[child.tag for child in list(root)]}"
        )
    variables = [
        element.attrib.get("name", "")
        for element in children_named(head, "variable")
    ]
    if not variables or any(not variable for variable in variables):
        raise RuntimeError(
            f"SPARQL XML head variables invalid: variables={variables} "
            f"head_children={[child.tag for child in list(head)]}"
        )

    rows: list[dict[str, Any]] = []
    for result_index, result in enumerate(children_named(results, "result"), 1):
        row: dict[str, Any] = {variable: base.empty_cell() for variable in variables}
        for binding in children_named(result, "binding"):
            name = binding.attrib.get("name", "")
            if not name or name not in row:
                raise RuntimeError(
                    f"SPARQL XML binding variable unexpected: result={result_index} name={name!r}"
                )
            terms = [child for child in list(binding) if local_name(child.tag) in {"uri", "literal", "bnode"}]
            if len(terms) != 1:
                raise RuntimeError(
                    f"SPARQL XML binding must contain one term: result={result_index} name={name!r} "
                    f"children={[child.tag for child in list(binding)]}"
                )
            term = terms[0]
            term_type = local_name(term.tag)
            row[name] = {
                "value": term.text or "",
                "term_type": term_type,
                "language": term.attrib.get(XML_LANG, ""),
                "datatype": term.attrib.get("datatype", ""),
            }
        rows.append(row)
    return rows


def main() -> int:
    base.parse_sparql_xml = parse_sparql_xml_local
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
