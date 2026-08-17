from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from deterministic_japanese_parser_mcp.final_runtime import build_final_runtime_index
from deterministic_japanese_parser_mcp.final_runtime_bridge import FinalRuntimeLexicon
from deterministic_japanese_parser_mcp.models import OriginalSpan, Token


def _write_jsonl_gzip(path: Path, rows: list[dict]) -> tuple[int, str]:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path) -> Path:
    runtime_rows = [
        {
            "entry_id": "DJPMCP-rich-1",
            "surface": "蛍石",
            "lemma": "蛍石",
            "reading": "ホタルイシ",
            "pos": "名詞-普通名詞-一般",
            "dictionary": "mcp_final_20260818",
            "cost": 10,
            "domains": ["frequency"],
            "source_datasets": ["bccwj-wsd-frequency"],
            "senses": [{"gloss": "fluorite"}],
            "aliases": ["ほたるいし"],
            "examples": ["蛍石を観察する"],
            "translations": [{"lang": "en", "text": "fluorite"}],
            "relations": [{"type": "domain", "target": "mineral"}],
            "metrics": ["frequency=10", "pmw=0.081"],
            "source_roles": ["lexicon"],
            "rights_lanes": ["R"],
            "entry_types": ["lexical"],
            "evidence_count": 1,
            "evidence_occurrences": 1,
            "evidence_samples": ["sample-1"],
        }
    ]
    support_rows = [
        {
            "record_type": "resource-index",
            "source": "support-fixture",
            "payload": {"kept": True},
        }
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
                "records": 1,
                "sha256": runtime_sha,
            }
        ],
        "support_pack": {
            "file": support_path.name,
            "bytes": support_bytes,
            "records": 1,
            "sha256": support_sha,
        },
        "validation": {
            "final_part_count": 1,
            "missing_required_core_fields": 0,
        },
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_bridge_exposes_completed_runtime_rich_fields_in_mcp_model(tmp_path: Path):
    manifest = _manifest(tmp_path)
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
    candidate = annotated.lexical_candidates[0]
    dumped = annotated.model_dump()

    assert annotated.lexical_status == "MATCHED"
    assert candidate.runtime_data["senses"] == [{"gloss": "fluorite"}]
    assert candidate.runtime_data["aliases"] == ["ほたるいし"]
    assert candidate.runtime_data["examples"] == ["蛍石を観察する"]
    assert candidate.runtime_data["translations"] == [{"lang": "en", "text": "fluorite"}]
    assert candidate.runtime_data["relations"] == [{"type": "domain", "target": "mineral"}]
    assert candidate.runtime_data["metrics"] == ["frequency=10", "pmw=0.081"]
    assert candidate.runtime_data["source_roles"] == ["lexicon"]
    assert candidate.runtime_data["rights_lanes"] == ["R"]
    assert candidate.runtime_data["evidence_count"] == 1
    assert candidate.runtime_data["entry_types"] == ["lexical"]
    assert dumped["lexical_candidates"][0]["runtime_data"] == candidate.runtime_data


def test_bridge_exposes_support_pack_without_fabricating_lexical_entries(tmp_path: Path):
    manifest = _manifest(tmp_path)
    index = tmp_path / "runtime-index.sqlite3"
    build_final_runtime_index(manifest, index)
    runtime = FinalRuntimeLexicon(index)

    assert runtime.support_records(record_type="resource-index") == [
        {
            "payload": {"kept": True},
            "record_type": "resource-index",
            "source": "support-fixture",
        }
    ]
