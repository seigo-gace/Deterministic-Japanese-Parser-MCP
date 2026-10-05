from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

from tools.compile_direct_final_japanese_function_projection import (
    compile_direct_final_projection,
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_bundle(root: Path, rows: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    part = root / "mcp-runtime-final-part-001.jsonl.gz"
    with gzip.open(part, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    support = root / "mcp-runtime-support.jsonl.gz"
    with gzip.open(support, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "support"}) + "\n")
    manifest = {
        "schema_version": "djpmcp.direct-runtime-final.manifest.v1",
        "target": "Deterministic-Japanese-Parser-MCP",
        "factory_used": False,
        "date": "2026-08-18",
        "runtime_schema": {
            "required_core_fields": [
                "surface", "lemma", "reading", "pos", "dictionary", "cost", "entry_id"
            ]
        },
        "validation": {
            "missing_required_core_fields": 0,
            "final_part_count": 1,
            "full_json_records_validated": len(rows),
        },
        "parts": [
            {
                "file": part.name,
                "bytes": part.stat().st_size,
                "sha256": _sha(part),
                "records": len(rows),
            }
        ],
        "support_pack": {
            "file": support.name,
            "bytes": support.stat().st_size,
            "sha256": _sha(support),
            "records": 1,
        },
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _row(entry_id: str, **updates):
    row = {
        "entry_id": entry_id,
        "surface": "橋",
        "lemma": "橋",
        "reading": "ハシ",
        "pos": ["名詞", "普通名詞", "一般"],
        "dictionary": "direct-final",
        "cost": 100,
        "aliases": [],
        "domains": ["general"],
        "senses": [{"gloss": "川などに架ける構造物"}],
        "examples": ["橋を渡る"],
        "relations": [{"type": "related", "target": "建造物"}],
        "source_datasets": ["source-a"],
        "source_roles": ["lexical-definition"],
        "rights_lanes": ["public-runtime"],
        "evidence_samples": ["sample-a"],
        "entry_types": ["lexical"],
        "metrics": {"frequency": 3},
    }
    row.update(updates)
    return row


def test_direct_final_projection_preserves_all_source_rows_and_audits_unmapped_fields(tmp_path: Path):
    source = tmp_path / "source"
    rows = [
        _row("DF-1"),
        _row(
            "DF-2",
            surface="を",
            lemma="を",
            reading="ヲ",
            pos=["助詞", "格助詞"],
            senses=[],
            relations=[],
            examples=[],
            metrics={"frequency": 9},
        ),
    ]
    manifest = _write_bundle(source, rows)
    output = tmp_path / "projection"
    result = compile_direct_final_projection(
        manifest_path=manifest,
        input_root=source,
        output_root=output,
    )

    assert result["canonical_record_count"] == 2
    assert result["observed_canonical_record_count"] == 2
    assert result["projected_record_count"] + result["rejected_record_count"] == 2
    assert result["projected_record_count"] == 2
    assert result["lane_counts"]["Orthography/Reading"] == 2
    assert result["lane_counts"]["Noun-Entity"] == 1
    assert result["lane_counts"]["Function Words"] == 1
    assert result["lane_counts"]["Sense-Semantic Relation"] >= 1
    assert result["lane_counts"]["Evidence-Provenance-Rights"] == 2
    assert result["boundaries"]["meaning_generation"] is False
    assert result["boundaries"]["full_source_conservation_required"] is True

    db = sqlite3.connect(output / "projection.sqlite3")
    try:
        unmapped = db.execute(
            "SELECT record_id,field_name,reason FROM unmapped_field ORDER BY record_id,field_name"
        ).fetchall()
    finally:
        db.close()
    assert ("DF-1", "metrics", "direct_final_field_not_consumed_by_projection_adapter_v1") in unmapped
    assert ("DF-2", "metrics", "direct_final_field_not_consumed_by_projection_adapter_v1") in unmapped


def test_direct_final_projection_fails_closed_when_manifest_count_disagrees(tmp_path: Path):
    source = tmp_path / "source"
    manifest = _write_bundle(source, [_row("DF-1")])
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["validation"]["full_json_records_validated"] = 2
    manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        compile_direct_final_projection(
            manifest_path=manifest,
            input_root=source,
            output_root=tmp_path / "projection",
        )
    except ValueError as exc:
        assert "source count mismatch" in str(exc)
    else:
        raise AssertionError("manifest/source count mismatch must fail closed")


def test_direct_final_projection_does_not_leave_staging_or_rollback(tmp_path: Path):
    source = tmp_path / "source"
    manifest = _write_bundle(source, [_row("DF-1")])
    output = tmp_path / "projection"
    compile_direct_final_projection(manifest_path=manifest, input_root=source, output_root=output)
    compile_direct_final_projection(manifest_path=manifest, input_root=source, output_root=output)
    assert not output.with_name(output.name + ".staging").exists()
    assert not output.with_name(output.name + ".rollback").exists()
