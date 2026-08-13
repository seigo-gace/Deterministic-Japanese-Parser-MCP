from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.semantic_labeler import (  # noqa: E402
    build_semantic_enrichment_queue,
    candidate_has_real_meaning,
    require_all_meanings_complete,
)


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


def _record(
    record_id: str,
    surface: str,
    gloss: str,
    *,
    semantic: str,
    runtime_eligible: bool,
    source_kind: str = "context",
) -> dict:
    return {
        "record_id": record_id,
        "input_sha256": "a" * 64,
        "source_kind": source_kind,
        "source": {"dataset": "test", "source_id": record_id},
        "lemma": surface,
        "surfaces": [surface],
        "normalized_surfaces": [surface],
        "readings": [],
        "part_of_speech": ["noun"],
        "domains": [],
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": gloss,
                "glosses": [gloss],
                "review_status": semantic,
            }
        ],
        "approval": {"scopes": {"semantic": semantic}},
        "runtime_eligible": runtime_eligible,
    }


def test_placeholder_is_not_real_meaning() -> None:
    assert not candidate_has_real_meaning(
        {"glosses": ["意味・機能はEvidence確認待ち"]}
    )
    assert not candidate_has_real_meaning(
        {"glosses": ["Meaning candidate from Wiktionary-derived data; review required"]}
    )
    assert candidate_has_real_meaning({"glosses": ["実際の意味"]})


def test_enrichment_uses_approved_record_without_auto_approval(tmp_path: Path) -> None:
    review = tmp_path / "review-records.jsonl"
    _write_jsonl(
        review,
        [
            _record("REF", "めんこい", "かわいい、愛らしい", semantic="approved", runtime_eligible=True, source_kind="open_lexicon"),
            _record("TARGET", "めんこい", "意味・機能はEvidence確認待ち", semantic="needs-evidence", runtime_eligible=False),
        ],
    )
    report = build_semantic_enrichment_queue(review, tmp_path / "out")
    assert report["meaning_missing_records"] == 1
    assert report["proposed_from_approved_records"] == 1
    rows = [json.loads(line) for line in (tmp_path / "out/semantic-enrichment-queue.jsonl").read_text(encoding="utf-8").splitlines()]
    target = next(row for row in rows if row["record_id"] == "TARGET")
    assert target["human_review_required"] is True
    assert target["semantic_enrichment_status"] == "proposed-from-approved-record"
    assert target["proposed_meaning_candidates"][0]["glosses"] == ["かわいい、愛らしい"]
    assert target["proposed_meaning_candidates"][0]["review_status"] == "needs-evidence"


def test_future_reference_pack_is_generic_not_slang_only(tmp_path: Path) -> None:
    review = tmp_path / "review-records.jsonl"
    _write_jsonl(
        review,
        [_record("MED", "心筋梗塞", "意味・機能はEvidence確認待ち", semantic="needs-evidence", runtime_eligible=False, source_kind="domain_pack")],
    )
    ref_root = tmp_path / "reference"
    ref_root.mkdir()
    _write_jsonl(
        ref_root / "medical.jsonl",
        [{"surface": "心筋梗塞", "meaning": "心筋への血流が途絶えて心筋が壊死する病態", "domain": "medical", "source_id": "medical-mi"}],
    )
    report = build_semantic_enrichment_queue(review, tmp_path / "out", reference_roots=[ref_root])
    assert report["proposed_from_reference_packs"] == 1
    row = json.loads((tmp_path / "out/semantic-enrichment-queue.jsonl").read_text(encoding="utf-8").strip())
    assert row["record_id"] == "MED"
    assert row["proposed_meaning_candidates"][0]["glosses"] == ["心筋への血流が途絶えて心筋が壊死する病態"]


def test_compile_gate_rejects_missing_or_unapproved_runtime_meaning(tmp_path: Path) -> None:
    review = tmp_path / "review-records.jsonl"
    _write_jsonl(
        review,
        [_record("R1", "候補", "実際の意味", semantic="needs-evidence", runtime_eligible=True)],
    )
    report = build_semantic_enrichment_queue(review, tmp_path / "out")
    try:
        require_all_meanings_complete(report)
    except RuntimeError as exc:
        assert "runtime_semantic_incomplete_records=1" in str(exc)
    else:
        raise AssertionError("semantic completeness gate must fail")


def test_same_surface_conflicting_reading_does_not_copy_wrong_meaning(tmp_path: Path) -> None:
    review = tmp_path / "review-records.jsonl"
    target = _record(
        "TARGET", "生", "pending review", semantic="needs-evidence", runtime_eligible=False
    )
    target["readings"] = ["なま"]
    _write_jsonl(review, [target])
    reference = tmp_path / "reference.jsonl"
    _write_jsonl(
        reference,
        [
            {
                "surface": "生",
                "readings": ["せい"],
                "meaning": "生命または生きること",
                "source_id": "sei",
            }
        ],
    )
    report = build_semantic_enrichment_queue(
        review, tmp_path / "out", reference_roots=[reference]
    )
    assert report.get("proposed_from_reference_packs", 0) == 0
    row = json.loads(
        (tmp_path / "out/semantic-enrichment-queue.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert row["semantic_enrichment_status"] == "unresolved-meaning"
    assert row["proposed_meaning_candidates"] == []
