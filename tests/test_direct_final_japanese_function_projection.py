from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from tools.compile_direct_final_japanese_function_projection import (
    compile_direct_final_projection,
)
from tools.unified_semantic_data import japanese_function_projection as projection


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


def test_direct_final_projection_cli_is_executable_from_repository_root():
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/compile_direct_final_japanese_function_projection.py", "--help"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--manifest" in result.stdout
    assert "--input-root" in result.stdout
    assert "--output-root" in result.stdout


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
    assert result["source_category_profiles"]["pos"]["distinct_values"] >= 1
    assert result["source_category_profiles"]["entry_types"]["distinct_values"] >= 1

    db = sqlite3.connect(output / "projection.sqlite3")
    try:
        unmapped = db.execute(
            "SELECT field_name,record_count FROM unmapped_field_summary ORDER BY field_name"
        ).fetchall()
        row_count = db.execute("SELECT COUNT(*) FROM record_projection").fetchone()[0]
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        db.close()
    assert ("metrics", 2) in unmapped
    assert row_count == 2
    assert "record_lane" not in tables
    assert "unmapped_field" not in tables
    assert "record_identity" not in tables
    assert {"record_projection", "unmapped_field_summary"}.issubset(tables)


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
        assert "mismatch" in str(exc)
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



def test_direct_final_projection_maps_explicit_japanese_structure_lanes(tmp_path: Path):
    source = tmp_path / "source"
    rows = [
        _row("DF-ONO", surface="わくわく", lemma="わくわく", reading="ワクワク", entry_types=["擬態語"]),
        _row("DF-MW", surface="腹を割る", lemma="腹を割る", reading="ハラヲワル", entry_types=["慣用表現"]),
        _row("DF-SYN", surface="が", lemma="が", reading="ガ", relations=[{"type": "dependency", "target": "predicate"}]),
        _row("DF-DOC", surface="しかし", lemma="しかし", reading="シカシ", source_roles=["discourse-structure"]),
        _row("DF-USAGE", surface="お召し上がりになる", lemma="召し上がる", reading="メシアガル", usage_labels=["register-formal"]),
    ]
    manifest = _write_bundle(source, rows)
    result = compile_direct_final_projection(
        manifest_path=manifest,
        input_root=source,
        output_root=tmp_path / "projection",
    )
    assert result["lane_counts"]["Onomatopoeia"] >= 1
    assert result["lane_counts"]["Multiword"] >= 1
    assert result["lane_counts"]["Syntax-Case-Clause"] >= 1
    assert result["lane_counts"]["Document Structure"] >= 1
    assert result["lane_counts"]["Usage-Context-Pragmatics"] >= 1


def test_direct_final_projection_maps_explicit_source_and_pos_evidence_to_missing_lanes(tmp_path: Path):
    source = tmp_path / "source"
    rows = [
        _row(
            "DF-ONO-SOURCE",
            surface="わくわく",
            lemma="わくわく",
            reading="ワクワク",
            source_datasets=["j-ono-definitions"],
            entry_types=["lexical"],
            source_roles=["lexical-definition", "usage"],
        ),
        _row(
            "DF-PHRASE",
            surface="腹を割る",
            lemma="腹を割る",
            reading="ハラヲワル",
            pos=["phrase"],
        ),
        _row(
            "DF-DOCUMENT",
            surface="文書",
            lemma="文書",
            reading="ブンショ",
            pos=["document"],
        ),
        _row(
            "DF-INTERJECTION",
            surface="ああ",
            lemma="ああ",
            reading="アア",
            pos=["感動詞"],
            source_datasets=["generic-lexicon"],
        ),
        _row(
            "DF-MIMETIC-POS",
            surface="しんみり",
            lemma="しんみり",
            reading="シンミリ",
            pos=["擬態"],
            source_datasets=["generic-lexicon"],
        ),
    ]
    manifest = _write_bundle(source, rows)
    result = compile_direct_final_projection(
        manifest_path=manifest,
        input_root=source,
        output_root=tmp_path / "projection",
    )
    assert result["lane_counts"]["Onomatopoeia"] == 2
    assert result["lane_counts"]["Multiword"] >= 1
    assert result["lane_counts"]["Document Structure"] >= 1
    assert result["source_category_profiles"]["source_datasets"]["distinct_values"] >= 2
    assert "sense_labels" in result["source_category_profiles"]
    assert result["source_dataset_coverage"]["Onomatopoeia"]["present"] == ["j-ono-definitions"]
    assert result["source_dataset_coverage"]["Onomatopoeia"]["missing"] == []

    db = sqlite3.connect(tmp_path / "projection" / "projection.sqlite3")
    try:
        rows_by_id = {
            record_id: mask
            for record_id, mask in db.execute(
                "SELECT record_id,lane_mask FROM record_projection"
            )
        }
    finally:
        db.close()
    ono_bit = projection.LANE_BITS["Onomatopoeia"]
    assert rows_by_id["DF-ONO-SOURCE"] & ono_bit
    assert rows_by_id["DF-MIMETIC-POS"] & ono_bit
    assert not (rows_by_id["DF-INTERJECTION"] & ono_bit)


def test_direct_final_projection_dedupes_same_semantic_record_without_collapsing_homophones(tmp_path: Path):
    source = tmp_path / "source"
    same_a = _row(
        "DF-A",
        source_datasets=["source-a"],
        evidence_samples=["sample-a"],
    )
    same_b = _row(
        "DF-B",
        source_datasets=["source-b"],
        evidence_samples=["sample-b"],
    )
    homophone = _row(
        "DF-C",
        surface="箸",
        lemma="箸",
        reading="ハシ",
        senses=[{"gloss": "食事に使う二本一組の道具"}],
        source_datasets=["source-c"],
        evidence_samples=["sample-c"],
    )
    manifest = _write_bundle(source, [same_a, same_b, homophone])
    output = tmp_path / "projection"
    result = compile_direct_final_projection(
        manifest_path=manifest,
        input_root=source,
        output_root=output,
    )
    assert result["canonical_record_count"] == 3
    assert result["projected_record_count"] == 2
    assert result["duplicate_record_count"] == 1
    assert result["rejected_record_count"] == 0
    assert (
        result["projected_record_count"]
        + result["duplicate_record_count"]
        + result["rejected_record_count"]
        == 3
    )
    db = sqlite3.connect(output / "projection.sqlite3")
    try:
        duplicate = db.execute(
            "SELECT duplicate_record_id,canonical_record_id FROM duplicate_record"
        ).fetchone()
        projection_rows = db.execute(
            "SELECT record_id,lane_mask FROM record_projection ORDER BY record_id"
        ).fetchall()
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        db.close()
    assert duplicate == ("DF-B", "DF-A")
    assert [row[0] for row in projection_rows] == ["DF-A", "DF-C"]
    assert all(row[1] > 0 for row in projection_rows)
    assert "record_identity" not in tables
    assert "record_lane" not in tables
    assert "unmapped_field" not in tables
    assert {"record_projection", "unmapped_field_summary", "duplicate_record"}.issubset(tables)
    assert result["boundaries"]["storage_model"] == "single-record-lane-bitmask-v1"
    assert result["boundaries"]["build_identity_persisted"] is False

def test_negative_direct_final_labels_do_not_promote_lanes():
    from tools.compile_direct_final_japanese_function_projection import (
        _explicit_semantic_targets,
    )

    row = _row(
        "DF-NEG",
        pos=["名詞"],
        source_roles=["not an idiom", "非擬音", "non-multiword"],
        entry_types=["not-onomatopoeia"],
        usage_labels=["擬音ではない", "not a compound"],
        semantic_targets=[],
    )
    targets = _explicit_semantic_targets(row)
    assert "onomatopoeia" not in targets
    assert "multiword" not in targets


def test_positive_direct_final_source_roles_still_route():
    from tools.compile_direct_final_japanese_function_projection import (
        _explicit_semantic_targets,
    )

    row = _row(
        "DF-POS",
        pos=["名詞"],
        source_roles=["discourse-structure", "multiword"],
        entry_types=["onomatopoeia"],
        semantic_targets=[],
    )
    targets = _explicit_semantic_targets(row)
    assert {"document-structure", "multiword", "onomatopoeia"}.issubset(targets)


def test_negative_direct_final_tags_do_not_leak_into_compiled_lane_membership():
    from tools.compile_direct_final_japanese_function_projection import _projection_record

    row = _row(
        "DF-NEG-PROJECTION",
        pos=["名詞"],
        source_roles=["非擬音", "not an idiom"],
        entry_types=["not-onomatopoeia"],
        usage_labels=["擬音ではない"],
        semantic_targets=[],
    )
    projected = _projection_record(row, manifest_sha="a" * 64, version="v1")
    lanes = projection.assign_record_lanes(projected)
    assert "onomatopoeia" not in projected["semantic_facets"]["semantic_targets"]
    assert "multiword" not in projected["semantic_facets"]["semantic_targets"]
    assert "Onomatopoeia" not in lanes
    assert "Multiword" not in lanes
    assert "Orthography/Reading" in lanes


def test_negated_source_role_cannot_become_usage_evidence():
    from tools.compile_direct_final_japanese_function_projection import (
        _explicit_usage_labels,
    )

    row = _row(
        "DF-NEG-USAGE",
        usage_labels=["source-authored-positive-label"],
        source_roles=["not usage", "non-context", "no-pragmatic", "register-unverified"],
        entry_types=["not style"],
    )
    labels = _explicit_usage_labels(row)
    assert "source-authored-positive-label" in labels
    assert "not usage" not in labels
    assert "non-context" not in labels
    assert "no-pragmatic" not in labels
    assert "not style" not in labels


def test_registered_usage_role_is_still_preserved():
    from tools.compile_direct_final_japanese_function_projection import (
        _explicit_usage_labels,
    )

    labels = _explicit_usage_labels(
        _row("DF-POS-USAGE", usage_labels=[], source_roles=["register-formal", "usage"])
    )
    assert "register-formal" in labels
    assert "usage" in labels


def test_orthography_only_records_are_tracked_as_unresolved_reading_use(tmp_path: Path):
    source = tmp_path / "source"
    rows = [
        _row(
            "DF-UNRESOLVED",
            pos=[],
            senses=[],
            relations=[],
            entry_types=[],
            source_roles=[],
            semantic_targets=[],
            usage_labels=[],
            pragmatics={},
        ),
        _row("DF-NOUN", pos=["名詞"], senses=[], relations=[], entry_types=[]),
    ]
    manifest_path = _write_bundle(source, rows)
    result = compile_direct_final_projection(
        manifest_path=manifest_path,
        input_root=source,
        output_root=tmp_path / "projection",
    )
    assert result["canonical_record_count"] == 2
    assert result["projected_record_count"] == 2
    assert result["purpose_unresolved_record_count"] == 1
    validated = projection.validate_projection_bundle(tmp_path / "projection")
    assert validated["purpose_unresolved_record_count"] == 1
    db = sqlite3.connect(tmp_path / "projection" / "projection.sqlite3")
    try:
        unresolved = list(db.execute(
            "SELECT record_id,reason FROM purpose_unresolved_record ORDER BY record_id"
        ))
    finally:
        db.close()
    assert unresolved == [("DF-UNRESOLVED", "no_supported_japanese_reading_use")]


def test_expression_attributes_coexist_with_grammar_and_lexical_lanes(tmp_path: Path):
    from tools.compile_direct_final_japanese_function_projection import (
        _explicit_expression_attributes,
    )

    source = tmp_path / "source"
    rows = [
        _row("DF-SLANG", surface="アオハル", entry_types=["slang"], usage_labels=["若者語"], pos=["名詞"]),
        _row("DF-DIALECT", surface="西", entry_types=["dialect"], usage_labels=["口語"], pos=["名詞"]),
        _row("DF-ONO", surface="ゴロゴロ", entry_types=["onomatopoeia"], usage_labels=["slang"], pos=["副詞"]),
        _row("DF-NEG", surface="不採用", entry_types=["not slang"], usage_labels=["非擬音"], pos=["名詞"]),
    ]
    assert _explicit_expression_attributes(rows[0]) == ["slang"]
    assert _explicit_expression_attributes(rows[1]) == ["colloquial", "dialect"]
    assert _explicit_expression_attributes(rows[2]) == ["onomatopoeia", "slang"]
    assert _explicit_expression_attributes(rows[3]) == []
    manifest_path = _write_bundle(source, rows)
    result = compile_direct_final_projection(
        manifest_path=manifest_path,
        input_root=source,
        output_root=tmp_path / "projection",
    )
    assert result["expression_attribute_counts"] == {
        "colloquial": 1, "dialect": 1, "onomatopoeia": 1, "slang": 2,
    }
    validated = projection.validate_projection_bundle(tmp_path / "projection")
    assert validated["expression_attribute_counts"] == result["expression_attribute_counts"]
    db = sqlite3.connect(tmp_path / "projection" / "projection.sqlite3")
    try:
        pairs = set(db.execute(
            "SELECT record_id,attribute FROM record_expression_attribute"
        ))
        noun_mask = db.execute(
            "SELECT lane_mask FROM record_projection WHERE record_id='DF-SLANG'"
        ).fetchone()[0]
    finally:
        db.close()
    assert ("DF-SLANG", "slang") in pairs
    assert ("DF-DIALECT", "dialect") in pairs
    assert ("DF-DIALECT", "colloquial") in pairs
    assert ("DF-ONO", "slang") in pairs
    assert ("DF-ONO", "onomatopoeia") in pairs
    assert all(record_id != "DF-NEG" for record_id, _ in pairs)
    assert noun_mask & projection.LANE_BITS["Noun-Entity"]

