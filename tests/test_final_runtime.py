from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from deterministic_japanese_parser_mcp.final_runtime import (
    FinalRuntimeLexicon,
    build_final_runtime_index,
)
from deterministic_japanese_parser_mcp.models import OriginalSpan, Token


def _write_jsonl_gzip(path: Path, rows: list[dict]) -> tuple[int, str]:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_manifest(root: Path) -> Path:
    runtime_rows = [
        {
            "entry_id": "DJPMCP-1",
            "surface": "生",
            "lemma": "生",
            "reading": "ナマ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "mcp_final_20260818",
            "cost": 10,
            "domains": ["food"],
            "source_datasets": ["fixture-a"],
            "entry_types": ["lexical"],
            "rights_lanes": ["R"],
        },
        {
            "entry_id": "DJPMCP-2",
            "surface": "生",
            "lemma": "生きる",
            "reading": "セイ",
            "pos": ["名詞-普通名詞-一般"],
            "dictionary": "mcp_final_20260818",
            "cost": 20,
            "domains": ["general"],
            "source_datasets": ["fixture-b"],
            "entry_types": ["lexical"],
            "rights_lanes": ["R"],
        },
        {
            "entry_id": "DJPMCP-3",
            "surface": "蛍石",
            "lemma": "蛍石",
            "reading": "ホタルイシ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "mcp_final_20260818",
            "cost": 10,
            "domains": ["frequency"],
            "source_datasets": ["bccwj-wsd-frequency"],
            "entry_types": ["lexical"],
            "rights_lanes": ["R"],
            "senses": ["蛍石の意味候補"],
            "aliases": ["フローライト"],
            "examples": ["蛍石を観察する。"],
            "translations": ["fluorite"],
            "relations": ["related:mineral"],
            "metrics": ["frequency=10"],
            "source_roles": ["lexical-evidence"],
            "evidence_count": 2,
            "evidence_occurrences": 3,
            "evidence_samples": ["蛍石"],
        },
    ]
    support_rows = [
        {"record_type": "resource-index", "source": "fixture"},
        {"record_type": "orphan-translation", "source": "fixture"},
    ]
    runtime_path = root / "mcp-runtime-final-part-001.jsonl.gz"
    support_path = root / "mcp-runtime-support.jsonl.gz"
    runtime_bytes, runtime_sha = _write_jsonl_gzip(runtime_path, runtime_rows)
    support_bytes, support_sha = _write_jsonl_gzip(support_path, support_rows)
    manifest = {
        "target": "Deterministic-Japanese-Parser-MCP",
        "date": "2026-08-18",
        "factory_used": False,
        "runtime_schema": {
            "required_core_fields": [
                "surface",
                "lemma",
                "reading",
                "pos",
                "dictionary",
                "cost",
                "entry_id",
            ]
        },
        "parts": [
            {
                "file": runtime_path.name,
                "bytes": runtime_bytes,
                "records": len(runtime_rows),
                "sha256": runtime_sha,
            }
        ],
        "support_pack": {
            "file": support_path.name,
            "bytes": support_bytes,
            "records": len(support_rows),
            "sha256": support_sha,
        },
        "validation": {
            "final_part_count": 1,
            "missing_required_core_fields": 0,
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def test_build_and_lookup_preserve_ambiguity_and_support(tmp_path: Path):
    manifest = _fixture_manifest(tmp_path)
    index = tmp_path / "runtime-index.sqlite3"

    result = build_final_runtime_index(manifest, index)
    runtime = FinalRuntimeLexicon(index)
    candidates, total = runtime.exact_lookup("生", max_candidates=8)

    assert result == {
        "index": str(index),
        "record_count": 3,
        "support_record_count": 2,
        "part_count": 1,
        "status": "PASS",
    }
    assert runtime.available is True
    assert runtime.record_count == 3
    assert runtime.support_record_count == 2
    assert total == 2
    assert [item.record_id for item in candidates] == ["DJPMCP-1", "DJPMCP-2"]
    assert {item.readings[0] for item in candidates} == {"ナマ", "セイ"}
    assert runtime.support_type_counts() == {
        "orphan-translation": 1,
        "resource-index": 1,
    }


def test_token_lookup_maps_completed_runtime_fields_without_semantic_promotion(tmp_path: Path):
    manifest = _fixture_manifest(tmp_path)
    index = tmp_path / "runtime-index.sqlite3"
    build_final_runtime_index(manifest, index)
    runtime = FinalRuntimeLexicon(index)
    token = Token(
        surface="蛍石",
        normalized="蛍石",
        reading="ホタルイシ",
        pos=["名詞"],
        span=OriginalSpan(start=0, end=2, source_text="蛍石"),
    )

    annotated = runtime.lookup_token(token)

    assert annotated.lexical_status == "MATCHED"
    assert annotated.lexical_candidate_total == 1
    candidate = annotated.lexical_candidates[0]
    assert candidate.record_id == "DJPMCP-3"
    assert candidate.lemma == "蛍石"
    assert candidate.readings == ["ホタルイシ"]
    assert candidate.part_of_speech == ["名詞-普通名詞-一般"]
    assert candidate.domains == ["frequency"]
    assert candidate.source_dataset == "bccwj-wsd-frequency"
    payload = runtime.record_payload("DJPMCP-3")
    assert payload is not None
    assert payload["senses"] == ["蛍石の意味候補"]
    assert payload["aliases"] == ["フローライト"]
    assert payload["examples"] == ["蛍石を観察する。"]
    assert payload["translations"] == ["fluorite"]
    assert payload["relations"] == ["related:mineral"]
    assert payload["metrics"] == ["frequency=10"]
    assert payload["source_roles"] == ["lexical-evidence"]
    assert payload["rights_lanes"] == ["R"]
    assert payload["evidence_count"] == 2
    assert payload["evidence_occurrences"] == 3
    assert payload["evidence_samples"] == ["蛍石"]
    assert payload["entry_types"] == ["lexical"]


def test_hash_mismatch_rejects_untrusted_final_part(tmp_path: Path):
    manifest_path = _fixture_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["parts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    index = tmp_path / "runtime-index.sqlite3"

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_final_runtime_index(manifest_path, index)

    assert not index.exists()
    assert not (tmp_path / "runtime-index.sqlite3.tmp").exists()
