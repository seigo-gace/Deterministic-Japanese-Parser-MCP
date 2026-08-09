from __future__ import annotations

import json
from pathlib import Path

from tools.unified_semantic_data.factory_foundation import (
    build_foundation_assets,
    can_reuse_pipeline,
    canonical_text,
    content_fingerprint,
    lexical_identity,
    lookup_projection,
    stable_partition,
    write_factory_state,
)


def _write_review_records(root: Path, records: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    (root / "review-records.jsonl").write_text(text, encoding="utf-8")
    (root / "approved-records.jsonl").write_text(text, encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"review_queue_records": 0}), encoding="utf-8"
    )


def _record(record_id: str, surface: str) -> dict:
    return {
        "record_id": record_id,
        "lemma": surface,
        "normalized_surfaces": [surface],
        "readings": ["テスト"],
        "part_of_speech": ["名詞"],
        "forms": [
            {
                "surface": surface,
                "normalized": surface,
                "lemma": surface,
                "reading": "テスト",
                "part_of_speech": "名詞",
            }
        ],
        "source": {"dataset": "fixture", "version": "1", "source_id": record_id},
    }


def test_normalization_layers_do_not_collapse_evidence_and_lookup() -> None:
    value = "①　Ａ"
    assert canonical_text(value) == "① Ａ"
    assert lookup_projection(value) == "1a"


def test_lexical_identity_is_stable_and_separates_lookup_projection() -> None:
    left = lexical_identity(_record("r-1", "ＡＢＣ"))
    right = lexical_identity(_record("r-1", "ＡＢＣ"))
    assert left == right
    assert left["orthographic_forms"] == ["ＡＢＣ"]
    assert left["lookup_forms"] == ["abc"]
    assert left["lexeme_id"].startswith("lex:")


def test_stable_partition_depends_only_on_record_key_and_partition_count() -> None:
    before = stable_partition("record-100", 64)
    assert before == stable_partition("record-100", 64)
    # Adding some unrelated record has no input into the partition function.
    _ = stable_partition("new-record", 64)
    assert before == stable_partition("record-100", 64)


def test_foundation_build_reuses_unchanged_partition_bytes(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    records = [_record("r-1", "東京"), _record("r-2", "大阪")]
    _write_review_records(review_root, records)

    first = build_foundation_assets(review_root, partition_count=16)
    second = build_foundation_assets(review_root, partition_count=16)

    assert first["record_count"] == 2
    assert second["record_count"] == 2
    assert second["stage_hash"] == first["stage_hash"]
    assert second["written_partitions"] == 0
    assert second["reused_partitions"] == second["active_partition_count"]
    assert second["boundaries"]["automatic_approval"] is False


def test_content_fingerprint_is_path_location_independent(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("same", encoding="utf-8")
    (right / "a.txt").write_text("same", encoding="utf-8")

    left_hash = content_fingerprint(
        [("source", left)], parameters={"version": 1}
    )
    right_hash = content_fingerprint(
        [("source", right)], parameters={"version": 1}
    )
    assert left_hash == right_hash


def test_factory_state_reuse_requires_matching_hash_and_outputs(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    compiled_root = tmp_path / "compiled"
    _write_review_records(review_root, [_record("r-1", "東京")])
    foundation = build_foundation_assets(review_root, partition_count=8)
    compiled_root.mkdir()
    (compiled_root / "manifest.json").write_text("{}", encoding="utf-8")
    state_path = review_root / ".factory-state.json"
    write_factory_state(
        state_path,
        input_fingerprint="abc",
        foundation_manifest=foundation,
        compiled=True,
    )

    assert can_reuse_pipeline(
        state_path,
        input_fingerprint="abc",
        review_root=review_root,
        compiled_root=compiled_root,
        require_compiled=True,
    )
    assert not can_reuse_pipeline(
        state_path,
        input_fingerprint="different",
        review_root=review_root,
        compiled_root=compiled_root,
        require_compiled=True,
    )
