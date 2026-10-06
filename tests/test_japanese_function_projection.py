from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from tools.unified_semantic_data import japanese_function_projection as projection


def _record(record_id: str = "CDICT-1", **updates):
    value = {
        "dictionary_id": record_id,
        "lemma": "走る",
        "surfaces": ["走る"],
        "normalized_surfaces": ["走る"],
        "readings": ["はしる"],
        "reading_mappings": [{"reading": "はしる", "restricted_to": ["走る"], "no_kanji": False}],
        "part_of_speech": ["動詞"],
        "morphology": {"conjugation": {"type": "五段"}},
        "domains": ["general"],
        "senses": [
            {
                "sense_id": f"{record_id}:S-1",
                "labels": ["移動する"],
                "glosses": ["足を使って移動する"],
                "context": {"required_any": ["移動"]},
                "source_evidence": [{"source_record_id": "SRC-1"}],
            }
        ],
        "pragmatics": {"examples": {"positive": ["毎朝走る"]}},
        "semantic_facets": {
            "semantic_targets": ["predicate", "syntax", "usage"],
            "usage_labels": ["general"],
        },
        "auxiliary_evidence": {},
    }
    value.update(updates)
    return value


def test_lane_contract_is_stable_and_complete():
    assert projection.LANES == (
        "Orthography/Reading",
        "Noun-Entity",
        "Predicate-Inflection",
        "Function Words",
        "Connective-Modifier",
        "Onomatopoeia",
        "Multiword",
        "Syntax-Case-Clause",
        "Sense-Semantic Relation",
        "Usage-Context-Pragmatics",
        "Document Structure",
        "Evidence-Provenance-Rights",
    )


def test_assignment_uses_only_explicit_record_evidence():
    record = _record(
        part_of_speech=["名詞", "固有名詞"],
        semantic_facets={
            "semantic_targets": [
                "entity",
                "function-word",
                "connective",
                "onomatopoeia",
                "multiword",
                "syntax",
                "lexicon",
                "pragmatics",
                "document-structure",
            ],
            "usage_labels": ["擬音", "慣用表現"],
        },
        approval={"scopes": {"lexical": "approved"}},
    )
    lanes = projection.assign_record_lanes(record)
    assert set(lanes) == set(projection.LANES)
    assert lanes["Noun-Entity"] == ("part_of_speech", "semantic_target")
    assert "semantic_target" in lanes["Onomatopoeia"]
    assert "explicit_usage_or_sense_label" in lanes["Multiword"]
    assert lanes["Evidence-Provenance-Rights"] == ("source_or_approval_evidence",)


def test_assignment_does_not_invent_unrepresented_lanes():
    lanes = projection.assign_record_lanes(
        {
            "dictionary_id": "CDICT-minimal",
            "lemma": "橋",
            "surfaces": ["橋"],
            "readings": ["はし"],
            "part_of_speech": ["名詞"],
        }
    )
    assert set(lanes) == {"Orthography/Reading", "Noun-Entity"}


def test_compile_preserves_rejected_records_and_unknown_fields(monkeypatch, tmp_path: Path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "manifest.json").write_text(json.dumps({"record_count": 2}) + "\n", encoding="utf-8")
    records = [
        _record("CDICT-1", future_field={"opaque": [1, 2, 3]}),
        {"dictionary_id": "CDICT-empty"},
    ]
    monkeypatch.setattr(
        projection,
        "validate_compiled_dictionary_root",
        lambda root: {"record_count": 2, "record_shards": 0},
    )
    monkeypatch.setattr(projection, "_iter_canonical_records", lambda root: iter(records))

    output = tmp_path / "projection"
    manifest = projection.compile_japanese_function_projection(canonical, output)

    assert manifest["canonical_record_count"] == 2
    assert manifest["projected_record_count"] == 1
    assert manifest["rejected_record_count"] == 1
    assert manifest["projected_record_count"] + manifest["rejected_record_count"] == 2
    assert manifest["unmapped_field_count"] == 1
    assert manifest["projection_policy_version"] == projection.PROJECTION_POLICY_VERSION
    assert manifest["scoring_policy_version"] == projection.SCORING_POLICY_VERSION

    connection = sqlite3.connect(output / "projection.sqlite3")
    try:
        reject = connection.execute(
            "SELECT reason FROM rejected_record WHERE record_id='CDICT-empty'"
        ).fetchone()
        unmapped = connection.execute(
            "SELECT source_reference,payload_sha256,reason FROM unmapped_field WHERE record_id='CDICT-1' AND field_name='future_field'"
        ).fetchone()
    finally:
        connection.close()
    assert reject == ("no_supported_projection_lane",)
    assert unmapped[0] == "canonical:CDICT-1:future_field"
    assert unmapped[1] == projection._stable_json_sha256({"opaque": [1, 2, 3]})
    assert unmapped[2] == "field_not_in_projection_policy_v2"


def test_bundle_validation_fails_closed_on_policy_mismatch(monkeypatch, tmp_path: Path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "manifest.json").write_text(json.dumps({"record_count": 1}) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        projection,
        "validate_compiled_dictionary_root",
        lambda root: {"record_count": 1, "record_shards": 0},
    )
    monkeypatch.setattr(projection, "_iter_canonical_records", lambda root: iter([_record()]))
    output = tmp_path / "projection"
    projection.compile_japanese_function_projection(canonical, output)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["projection_policy_version"] = "incompatible"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="projection_policy_version"):
        projection.validate_projection_bundle(output)


def test_compile_replaces_existing_bundle_without_leaving_staging(monkeypatch, tmp_path: Path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "manifest.json").write_text(json.dumps({"record_count": 1}) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        projection,
        "validate_compiled_dictionary_root",
        lambda root: {"record_count": 1, "record_shards": 0},
    )
    monkeypatch.setattr(projection, "_iter_canonical_records", lambda root: iter([_record()]))
    output = tmp_path / "projection"
    projection.compile_japanese_function_projection(canonical, output)
    (output / "old-marker.txt").write_text("old", encoding="utf-8")
    projection.compile_japanese_function_projection(canonical, output)
    assert not (output / "old-marker.txt").exists()
    assert not output.with_name(output.name + ".staging").exists()
    assert not output.with_name(output.name + ".rollback").exists()
