from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from deterministic_japanese_parser_mcp.models import OriginalSpan, Token
from deterministic_japanese_parser_mcp.open_lexicon_runtime import OpenLexiconRuntime
from deterministic_japanese_parser_mcp.semantic_data_runtime import SemanticDataRuntime
from tools.compile_direct_final_runtime import compile_direct_final_runtime


def _write_jsonl_gzip(path: Path, rows: list[dict]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            for row in rows:
                gz.write(
                    (
                        json.dumps(
                            row,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path, *, factory_used: bool = False) -> Path:
    runtime_rows = [
        {
            "entry_id": "D-1",
            "surface": "橋",
            "lemma": "橋",
            "reading": "ハシ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "direct-final-test",
            "cost": 10,
            "domains": ["general"],
            "source_datasets": ["fixture-a"],
            "rights_lanes": ["R"],
            "aliases": ["はし"],
            "senses": ["bridge"],
            "examples": ["橋を渡る"],
            "evidence_samples": ["fixture-a:1"],
        },
        {
            "entry_id": "D-2",
            "surface": "橋",
            "lemma": "箸",
            "reading": "ハシ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "direct-final-test",
            "cost": 20,
            "domains": ["general"],
            "source_datasets": ["fixture-b"],
            "rights_lanes": ["R"],
            "aliases": [],
            "senses": ["chopsticks"],
            "evidence_samples": ["fixture-b:1"],
        },
        {
            "entry_id": "D-3",
            "surface": "未知語",
            "lemma": "未知語",
            "reading": "ミチゴ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "direct-final-test",
            "cost": 30,
            "domains": ["test"],
            "source_datasets": ["fixture-c"],
            "rights_lanes": ["Q"],
            "aliases": ["未知"],
            "metrics": ["frequency=1"],
        },
    ]
    support_rows = [
        {
            "record_type": "resource-index",
            "source": "fixture-support",
            "payload": {"preserved": True},
        }
    ]
    part = root / "mcp-runtime-final-part-001.jsonl.gz"
    support = root / "mcp-runtime-support.jsonl.gz"
    part_bytes, part_sha = _write_jsonl_gzip(part, runtime_rows)
    support_bytes, support_sha = _write_jsonl_gzip(support, support_rows)
    manifest = {
        "schema_version": "djpmcp.direct-runtime-final.manifest.v1",
        "target": "Deterministic-Japanese-Parser-MCP",
        "date": "2026-08-18",
        "factory_used": factory_used,
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
                "file": part.name,
                "bytes": part_bytes,
                "records": len(runtime_rows),
                "sha256": part_sha,
            }
        ],
        "support_pack": {
            "file": support.name,
            "bytes": support_bytes,
            "records": len(support_rows),
            "sha256": support_sha,
        },
        "validation": {
            "full_json_records_validated": len(runtime_rows),
            "missing_required_core_fields": 0,
            "final_part_count": 1,
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _token(surface: str, *, reading: str | None = None) -> Token:
    return Token(
        surface=surface,
        normalized=surface,
        reading=reading,
        pos=["名詞", "普通名詞", "一般"],
        span=OriginalSpan(start=0, end=len(surface), source_text=surface),
    )


def test_direct_final_compiles_into_existing_runtime_abis(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest_path = _fixture(source_root)
    system_root = tmp_path / "system"

    result = compile_direct_final_runtime(
        manifest_path=manifest_path,
        input_root=source_root,
        system_root=system_root,
        work_root=tmp_path / "work",
        semantic_shard_size=100,
    )

    assert result["factory_used"] is False
    assert result["source_runtime_records"] == 3
    assert result["semantic_records"] == 2

    lexical = OpenLexiconRuntime(system_root / "compiled/open_lexicon")
    assert lexical.available is True
    assert lexical.lookup_backend == "sqlite-index-v1"
    lexical.preload_records()
    assert lexical.records_preloaded is True
    assert len(lexical._shard_cache) == 0

    candidates, total = lexical.exact_lookup("橋")
    assert total == 2
    assert {item.record_id for item in candidates} == {"D-1", "D-2"}
    assert {item.lemma for item in candidates} == {"橋", "箸"}

    annotated = lexical.lookup_token(_token("橋", reading="ハシ"))
    assert annotated.lexical_status == "AMBIGUOUS"
    assert annotated.lexical_candidate_total == 2

    alias_candidates, alias_total = lexical.exact_lookup("未知")
    assert alias_total == 1
    assert alias_candidates[0].record_id == "D-3"

    reading_candidates, reading_total = lexical.reading_lookup("ハシ", surface="橋")
    assert reading_total == 2
    assert {item.record_id for item in reading_candidates} == {"D-1", "D-2"}

    semantic = SemanticDataRuntime(system_root / "compiled/canonical_dictionary_runtime")
    assert semantic.available is True
    assert semantic.record_count == 2
    records = semantic.lookup_token(_token("橋", reading="ハシ"))
    assert {item["record_id"] for item in records} == {"D-1", "D-2"}
    labels = {
        candidate["label"]
        for item in records
        for candidate in item["meaning_candidates"]
    }
    assert labels == {"bridge", "chopsticks"}
    assert all(item["approval"]["approved_scopes"] == ["lexical", "semantic"] for item in records)

    # Alias stays lexical-only; it must not inherit the source sense automatically.
    assert semantic.lookup_token(_token("はし")) == []
    # A row with no source-provided senses must not gain a fabricated meaning.
    assert semantic.lookup_token(_token("未知語", reading="ミチゴ")) == []


def test_direct_final_rejects_factory_output(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest_path = _fixture(source_root, factory_used=True)
    with pytest.raises(ValueError, match="factory_used=false"):
        compile_direct_final_runtime(
            manifest_path=manifest_path,
            input_root=source_root,
            system_root=tmp_path / "system",
            work_root=tmp_path / "work",
            semantic_shard_size=100,
        )
