from __future__ import annotations

import json
from pathlib import Path
import sys

from deterministic_japanese_parser_mcp.models import (
    MeaningGraph,
    OriginalSpan,
    Proposition,
    Token,
)
from deterministic_japanese_parser_mcp.semantic_candidate_runtime import (
    SemanticCandidateRuntime,
)

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from compile_semantic_candidate_pack import compile_candidates  # noqa: E402


def _record(
    record_id: str,
    surface: str,
    *,
    license_value: str = "CC-BY-SA-4.0",
    candidate_kind: str = "source-derived-candidate",
) -> dict:
    return {
        "schema_version": "1.0.0",
        "record_id": record_id,
        "source_kind": "open_lexicon",
        "lemma": surface,
        "surfaces": [surface],
        "normalized_surfaces": [surface],
        "readings": ["ひょうか"],
        "part_of_speech": ["名詞"],
        "morphology": {"backend": "fixture", "forms": [], "conjugation": {}},
        "domains": ["education"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": "学習結果を判断すること",
                "glosses": ["assessment"],
                "part_of_speech": ["名詞"],
                "domains": ["education"],
                "polarity": "unspecified",
                "parameters": {"force_level": 5},
                "register": {},
                "context": {},
                "evidence_ids": [f"evidence:{record_id}"],
                "review_status": "needs-evidence",
                "candidate_kind": candidate_kind,
            }
        ],
        "semantic_targets": ["lexicon"],
        "parameters": {},
        "register": {},
        "context_conditions": {},
        "examples": {"positive": [], "negative": [], "boundary": []},
        "risk_class": "action",
        "source": {
            "dataset": "fixture",
            "version": "1.0.0",
            "license": license_value,
            "source_id": record_id,
            "source_url": "https://example.invalid/fixture",
            "source_sha256": "a" * 64,
            "evidence_scope": "runtime_data",
            "attribution": "fixture",
        },
        "review_status": "needs-evidence",
        "review_blockers": (
            ["license-required"] if license_value == "確認中" else []
        ),
        "runtime_eligible": False,
        "original_location": {"path": "fixture", "line": 1},
    }


def _write_review_root(root: Path, records: list[dict]) -> None:
    root.mkdir(parents=True)
    text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    (root / "review-records.jsonl").write_text(text, encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"total_records": len(records)}, sort_keys=True),
        encoding="utf-8",
    )


def test_candidate_compiler_excludes_unlicensed_and_placeholder_records(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "review"
    _write_review_root(
        review_root,
        [
            _record("VALID-001", "評価"),
            _record("LICENSE-001", "未許諾", license_value="確認中"),
            _record(
                "PLACEHOLDER-001",
                "未確定",
                candidate_kind="unresolved-shell",
            ),
        ],
    )
    compiled_root = tmp_path / "compiled"
    manifest = compile_candidates(
        review_root=review_root,
        compiled_root=compiled_root,
        shard_size=100,
    )
    assert manifest["record_count"] == 1
    assert manifest["meaning_candidate_count"] == 1
    assert manifest["candidate_only"] is True
    assert manifest["approved_semantic_effects"] is False
    assert manifest["automatic_sense_selection"] is False
    assert manifest["automatic_external_action"] is False


def test_candidate_runtime_exposes_senses_without_selecting_or_applying_parameters(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "review"
    _write_review_root(review_root, [_record("VALID-001", "評価")])
    compiled_root = tmp_path / "compiled"
    compile_candidates(
        review_root=review_root,
        compiled_root=compiled_root,
        shard_size=100,
    )
    runtime = SemanticCandidateRuntime(compiled_root)
    span = OriginalSpan(start=0, end=2, source_text="評価")
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="評価",
                intent_type="action",
                value="評価",
                executable_candidate=True,
                force_level=1,
                source_span=span,
            )
        ]
    )
    token = Token(
        surface="評価",
        normalized="評価",
        reading="ヒョウカ",
        pos=["名詞"],
        span=span,
    )
    enriched = runtime.enrich(
        graph,
        tokens=[token],
        original_text="評価",
        conversation_context=[],
        known_entities=[],
    )
    proposition = enriched.propositions[0]
    assert runtime.available is True
    assert proposition.sense_id is None
    assert proposition.sense_label is None
    assert proposition.force_level == 1
    assert proposition.executable_candidate is True
    assert [item.sense_id for item in proposition.sense_candidates] == [
        "VALID-001:sense:001"
    ]
    assert "source-validated-semantic-candidate-pack" in (
        proposition.inference_sources
    )
    assert enriched.quality_annotations[
        "semantic_candidate_pack_automatic_selection"
    ] is False
    assert enriched.quality_annotations[
        "semantic_candidate_pack_external_action"
    ] is False


def test_missing_candidate_pack_is_safe_noop(tmp_path: Path) -> None:
    runtime = SemanticCandidateRuntime(tmp_path / "missing")
    graph = MeaningGraph()
    enriched = runtime.enrich(
        graph,
        tokens=[],
        original_text="",
        conversation_context=[],
        known_entities=[],
    )
    assert runtime.available is False
    assert enriched.quality_annotations["semantic_candidate_pack_used"] is False
