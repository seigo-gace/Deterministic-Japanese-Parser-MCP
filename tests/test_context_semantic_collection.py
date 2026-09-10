from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_context_semantic_collection import build_collection  # noqa: E402
from unified_semantic_data.pipeline import build_review_assets  # noqa: E402


def test_context_collection_fixes_record_provenance_and_preserves_review_boundary(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    manifest = {
        "collection_version": "fixture-context-v3",
        "total_entries": 2,
    }
    (input_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (input_root / "slang").mkdir()
    source_candidate = {
        "entry_id": "CTX-SOURCE-001",
        "surface": "本真",
        "reading": "ほんま",
        "feature_type": "slang",
        "category": "slang",
        "meaning_candidates": [
            {
                "meaning": "truth; reality",
                "polarity": "neutral",
                "intensity": 0.4,
            }
        ],
        "domain": ["casual", "regional"],
        "source": ["https://example.invalid/honma"],
        "source_version": "fixture-source-v1",
        "license": "CC BY-SA 4.0 / GFDL",
        "review_status": "needs-evidence",
        "positive_examples": ["ほんまや。"],
        "negative_examples": ["本真という字を見た。"],
        "boundary_examples": ["ほんまかもしれない。"],
        "provenance": {
            "origin": "kaikki-wiktionary",
            "constructed_examples": True,
            "meaning_promotion_allowed": False,
        },
    }
    unresolved = {
        "entry_id": "CTX-UNRESOLVED-001",
        "surface": "DD",
        "feature_type": "slang",
        "category": "slang",
        "meaning_candidates": [
            {"meaning": "意味・機能はEvidence確認待ち"}
        ],
        "domain": ["sns"],
        "source": ["research/context_collection/candidates.md"],
        "license": "確認中",
        "review_status": "needs-evidence",
        "positive_examples": ["対象文脈でDDが現れる。"],
        "negative_examples": ["DDという文字列を引用した。"],
        "boundary_examples": ["DDかもしれない。"],
        "provenance": {
            "origin": "existing-v2-candidate",
            "constructed_examples": True,
            "meaning_promotion_allowed": False,
        },
    }
    source_path = input_root / "slang/source.yaml"
    unresolved_path = input_root / "slang/unresolved.yaml"
    source_path.write_text(
        yaml.safe_dump(source_candidate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    unresolved_path.write_text(
        yaml.safe_dump(unresolved, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    output_root = tmp_path / "normalized"
    report = build_collection(
        input_root=input_root,
        output_root=output_root,
        report_path=tmp_path / "report.json",
        expected_records=2,
    )
    assert report["record_count"] == 2
    assert report["source_derived_meaning_candidates"] == 1
    assert report["unresolved_meaning_candidate_shells"] == 1

    normalized_source = yaml.safe_load(
        (output_root / "slang/source.yaml").read_text(encoding="utf-8")
    )
    assert normalized_source["domains"] == ["casual", "regional"]
    assert normalized_source["source"]["version"] == "fixture-source-v1"
    assert normalized_source["source"]["source_sha256"] == hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    assert normalized_source["meaning_candidates"][0]["candidate_kind"] == (
        "source-derived-candidate"
    )
    assert normalized_source["review_status"] == "needs-evidence"

    normalized_unresolved = yaml.safe_load(
        (output_root / "slang/unresolved.yaml").read_text(encoding="utf-8")
    )
    assert normalized_unresolved["meaning_candidates"][0]["candidate_kind"] == (
        "unresolved-shell"
    )
    assert normalized_unresolved["source"]["version"] == "fixture-context-v3"

    review_root = tmp_path / "review"
    review = build_review_assets(
        open_lexicon_root=tmp_path / "open",
        context_root=output_root,
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    assert review["total_records"] == 2
    assert "source-version-required" not in review["review_blocker_counts"]
    assert "source-digest-required" not in review["review_blocker_counts"]
    assert review["runtime_eligible_records"] == 1
