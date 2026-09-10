from __future__ import annotations

import hashlib
import gzip
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.raw_intake import (  # noqa: E402
    inspect_collected_artifact,
    load_profiles,
    scan_payload,
    validate_intake_manifest,
)
from unified_semantic_data.collection_intake import inspect_collection_artifact  # noqa: E402
from build_frozen_raw_factory_input import matching_profiles  # noqa: E402


def _open_bytes(data: bytes):
    return lambda: io.BytesIO(data)


@pytest.mark.parametrize(
    ("profile", "payload", "expected"),
    [
        (
            {"parser_family": "commented-sequence", "encodings": ["utf-8"]},
            b"# comment\n1F600 ; fully-qualified\n",
            1,
        ),
        (
            {
                "parser_family": "delimited-table",
                "encodings": ["utf-8"],
                "delimiter": "\t",
                "minimum_columns": 2,
            },
            "語\tvalue\n".encode(),
            1,
        ),
        (
            {
                "parser_family": "streaming-xml",
                "xml_target_tags": ["entry"],
            },
            b"<root><entry/><entry/></root>",
            2,
        ),
        (
            {"parser_family": "json-corpus", "encodings": ["utf-8"]},
            b"[{\"text\":\"a\"},{\"text\":\"b\"}]",
            2,
        ),
        (
            {"parser_family": "conllu", "encodings": ["utf-8"]},
            "1\t語\t語\tNOUN\t_\t_\t0\troot\t_\t_\n".encode(),
            1,
        ),
        (
            {"parser_family": "skk", "encodings": ["euc_jp"]},
            "ご /語/\n".encode("euc_jp"),
            1,
        ),
        (
            {"parser_family": "knp", "encodings": ["utf-8"]},
            b"# S-ID:1\n* 0 -1D\nEOS\n",
            2,
        ),
    ],
)
def test_all_parser_families_scan_declared_payloads(
    profile: dict, payload: bytes, expected: int
) -> None:
    count, _encoding = scan_payload(profile, _open_bytes(payload))
    assert count == expected


def test_declared_encoding_fallback_is_strict_and_recorded() -> None:
    profile = {
        "parser_family": "delimited-table",
        "encodings": ["utf-8", "cp932"],
    }
    count, encoding = scan_payload(profile, _open_bytes("日本語\n".encode("cp932")))
    assert count == 1
    assert encoding == "cp932"


def _artifact(path: Path, inner_entries: dict[str, bytes]) -> None:
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w", compression=zipfile.ZIP_DEFLATED) as inner:
        for name, content in inner_entries.items():
            inner.writestr(name, content)
    raw = inner_buffer.getvalue()
    lock = {
        "source_id": "fixture",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as outer:
        outer.writestr("source-lock.json", json.dumps(lock))
        outer.writestr("raw.zip", raw)


def _profile() -> dict:
    return {
        "artifact_name": "fixture-artifact",
        "source_id": "fixture",
        "rights_lane": "C",
        "public_runtime_eligible": True,
        "parser_family": "json-corpus",
        "payload_globs": ["data/*.json"],
        "encodings": ["utf-8"],
        "source_roles": ["usage"],
    }


def test_artifact_intake_verifies_lock_allowlist_and_full_parser_scan(tmp_path: Path) -> None:
    path = tmp_path / "artifact.zip"
    _artifact(
        path,
        {
            "data/a.json": b"[{\"a\":1},{\"a\":2}]",
            "README.md": b"not selected",
        },
    )
    result = inspect_collected_artifact(
        path,
        {"id": 7, "name": "fixture-artifact", "workflow_run_id": 11},
        _profile(),
        {},
    )
    assert result["factory_ready"] is True
    assert result["parsed_records"] == 2
    assert [item["path"] for item in result["payloads"]] == ["data/a.json"]
    assert result["automatic_approval"] is False
    assert result["automatic_runtime_promotion"] is False


def test_artifact_intake_rejects_traversal_even_when_not_selected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.zip"
    _artifact(path, {"data/a.json": b"[]", "../escape.txt": b"bad"})
    with pytest.raises(ValueError, match="unsafe archive path"):
        inspect_collected_artifact(
            path,
            {"id": 7, "name": "fixture-artifact", "workflow_run_id": 11},
            _profile(),
            {},
        )


def test_collection_intake_validates_direct_and_nested_payloads(tmp_path: Path) -> None:
    nested_buffer = io.BytesIO()
    with zipfile.ZipFile(nested_buffer, "w", compression=zipfile.ZIP_DEFLATED) as nested:
        nested.writestr("data/a.tsv", "語\tA\n".encode())
        nested.writestr("data/b.tsv", "文\tB\n".encode())
    nested_bytes = nested_buffer.getvalue()
    jsonl_bytes = gzip.compress(b'{"surface":"\xe8\xaa\x9e"}\n')
    digests = {
        "nested": hashlib.sha256(nested_bytes).hexdigest(),
        "jsonl": hashlib.sha256(jsonl_bytes).hexdigest(),
    }
    artifact_path = tmp_path / "collection.zip"
    with zipfile.ZipFile(artifact_path, "w", compression=zipfile.ZIP_STORED) as outer:
        outer.writestr("manifest.json", json.dumps(digests))
        outer.writestr("raw/nested.zip", nested_bytes)
        outer.writestr("normalized/data.jsonl.gz", jsonl_bytes)
    profiles = [
        {
            "artifact_kind": "collection",
            "artifact_name": "fixture-collection",
            "source_id": "nested-source",
            "rights_lane": "C",
            "public_runtime_eligible": True,
            "parser_family": "delimited-table",
            "payload_globs": ["raw/nested.zip"],
            "inner_payload_globs": ["data/*.tsv"],
            "minimum_payloads": 2,
            "encodings": ["utf-8"],
            "delimiter": "\t",
            "source_roles": ["usage"],
        },
        {
            "artifact_kind": "collection",
            "artifact_name": "fixture-collection",
            "source_id": "jsonl-source",
            "rights_lane": "R",
            "public_runtime_eligible": False,
            "parser_family": "jsonl",
            "payload_globs": ["normalized/data.jsonl.gz"],
            "encodings": ["utf-8"],
            "source_roles": ["lexical-definition"],
        },
    ]
    results = inspect_collection_artifact(
        artifact_path,
        {"id": 9, "name": "fixture-collection", "workflow_run_id": 12},
        profiles,
        {"max_archive_members": 100},
    )
    assert [row["source_id"] for row in results] == ["nested-source", "jsonl-source"]
    assert results[0]["payloads"][0]["selected_payload_count"] == 2
    assert results[1]["parser_probe_records"] == 1
    assert all(row["factory_ready"] is True for row in results)


def test_intake_manifest_requires_every_source_to_be_ready() -> None:
    source = {
        "source_id": "fixture",
        "logical_source_id": "fixture",
        "rights_lane": "C",
        "public_runtime_eligible": True,
        "parser_family": "jsonl",
        "source_roles": ["lexical-definition"],
        "payloads": [{"path": "data.jsonl.gz"}],
        "parser_probe_records": 1,
        "factory_ready": True,
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
    }
    manifest = {
        "source_intake_schema_version": "1.0.0",
        "source_count": 1,
        "unique_logical_source_count": 1,
        "factory_ready_source_count": 1,
        "sources": [source],
    }
    validate_intake_manifest(manifest)
    source["factory_ready"] = False
    with pytest.raises(ValueError, match="not factory-ready"):
        validate_intake_manifest(manifest)


def test_artifact_matching_prefers_most_specific_harvest_source_key() -> None:
    profiles = [
        {"artifact_name": "wlsp"},
        {"artifact_name": "chj-wlsp"},
    ]
    matches = matching_profiles(
        "source-harvest-wave2-chj-wlsp-deadbeef",
        profiles,
    )
    assert [profile["artifact_name"] for profile in matches] == ["chj-wlsp"]


def test_production_profiles_cover_exact_inventory_and_rights_lanes() -> None:
    profiles = load_profiles(ROOT / "config/source_payload_profiles.json")
    assert len(profiles["sources"]) == 67
    lane_counts: dict[str, int] = {}
    families: set[str] = set()
    for source in profiles["sources"]:
        lane_counts[source["rights_lane"]] = lane_counts.get(source["rights_lane"], 0) + 1
        families.add(source["parser_family"])
    assert sum(lane_counts.values()) == 67
    assert len(
        {source.get("logical_source_id", source["source_id"]) for source in profiles["sources"]}
    ) == 66
    assert families == {
        "commented-sequence",
        "delimited-table",
        "streaming-xml",
        "json-corpus",
        "conllu",
        "skk",
        "knp",
        "jsonl",
        "rdf-xml",
        "archive-index",
    }
