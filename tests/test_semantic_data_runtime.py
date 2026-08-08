from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

from deterministic_japanese_parser_mcp.models import (
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    Token,
)
from deterministic_japanese_parser_mcp.semantic_data_runtime import SemanticDataRuntime

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.pipeline import (  # noqa: E402
    build_review_assets,
    compile_approved,
)


def _source(source_id: str) -> dict:
    return {
        "dataset": "project-fixture",
        "version": "1.0.0",
        "license": "MIT",
        "source_id": source_id,
        "source_url": "https://example.invalid/fixture",
        "source_sha256": "b" * 64,
        "evidence_scope": "runtime_data",
        "attribution": "test fixture",
    }


def _compile_pack(tmp_path: Path, records: list[dict]) -> Path:
    approved_records = []
    for source_record in records:
        record = dict(source_record)
        candidates = record.get("meaning_candidates") or []
        record.setdefault(
            "polarity",
            candidates[0].get("polarity", "neutral") if candidates else "neutral",
        )
        record.setdefault("intensity", 0.5)
        record.setdefault("context_conditions", {})
        record.setdefault("task_candidates", [])
        record.setdefault(
            "external_action_risk", record.get("risk_class") == "action"
        )
        record["approval_scopes"] = {
            "lexical": "approved",
            "semantic": "approved",
            "pragmatic": "approved",
            "task": "approved",
            "external_action": "approved",
        }
        approved_records.append(record)
    pack_root = tmp_path / "domain_packs"
    pack_root.mkdir()
    (pack_root / "fixture.yaml").write_text(
        yaml.safe_dump(
            {"records": approved_records},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    review_root = tmp_path / "review"
    compiled_root = tmp_path / "compiled"
    build_review_assets(
        open_lexicon_root=tmp_path / "open",
        context_root=tmp_path / "context",
        pack_roots=[pack_root],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    compile_approved(review_root, compiled_root, shard_size=100)
    return compiled_root


def _graph(text: str, *, executable: bool = False) -> MeaningGraph:
    span = OriginalSpan(start=0, end=len(text), source_text=text)
    return MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="評価する",
                intent_type="action",
                value=text,
                executable_candidate=executable,
                source_span=span,
            )
        ]
    )


def test_approved_pack_enriches_meaning_graph_and_language_features(
    tmp_path: Path,
) -> None:
    record = {
        "record_id": "SEM-SLANG-001",
        "lemma": "エグい",
        "surfaces": ["エグい"],
        "readings": ["エグイ"],
        "part_of_speech": ["形容詞"],
        "feature_type": "slang",
        "domains": ["general"],
        "meaning_candidates": [
            {
                "candidate_id": "SEM-SLANG-001:positive",
                "label": "非常に優れていて驚く",
                "glosses": ["非常に優れていて驚く"],
                "polarity": "positive",
                "parameters": {
                    "register_labels": ["slang"],
                },
                "evidence_ids": ["E-SLANG-001"],
                "review_status": "approved",
            }
        ],
        "semantic_targets": ["lexicon", "language_feature"],
        "positive_examples": ["この性能はエグい。"],
        "negative_examples": ["野菜にえぐみがある。"],
        "boundary_examples": ["損失がエグい。"],
        "source": _source("SEM-SLANG-001"),
        "review_status": "approved",
    }
    root = _compile_pack(tmp_path, [record])
    runtime = SemanticDataRuntime(root)
    token = Token(
        surface="エグい",
        normalized="エグい",
        reading="エグイ",
        pos=["形容詞"],
        span=OriginalSpan(start=0, end=3, source_text="エグい"),
    )

    graph = runtime.enrich(
        _graph("エグい"),
        tokens=[token],
        original_text="エグい",
        conversation_context=[],
        known_entities=[],
    )

    proposition = graph.propositions[0]
    assert runtime.available is True
    assert proposition.sense_id == "SEM-SLANG-001:positive"
    assert proposition.sense_label == "非常に優れていて驚く"
    assert proposition.polarity == "positive"
    assert proposition.register_labels == ["slang"]
    assert proposition.inference_sources == ["approved-semantic-data-pack"]
    assert graph.language_features[0].entry_id == "SEM-SLANG-001"
    assert graph.language_features[0].status == ItemStatus.RESOLVED
    assert graph.quality_annotations["semantic_data_pack_used"] is True


def test_ambiguous_action_semantics_fail_closed(tmp_path: Path) -> None:
    record = {
        "record_id": "SEM-ACTION-001",
        "lemma": "止めて",
        "surfaces": ["止めて"],
        "readings": ["トメテ"],
        "part_of_speech": ["動詞"],
        "feature_type": "modality",
        "risk_class": "action",
        "meaning_candidates": [
            {
                "candidate_id": "SEM-ACTION-001:stop-process",
                "label": "処理を停止する依頼",
                "parameters": {"speech_act": "request", "force_level": 3},
                "evidence_ids": ["E-ACTION-001-A"],
                "review_status": "approved",
            },
            {
                "candidate_id": "SEM-ACTION-001:prevent-person",
                "label": "人の行動を制止する依頼",
                "parameters": {"speech_act": "request", "force_level": 3},
                "evidence_ids": ["E-ACTION-001-B"],
                "review_status": "approved",
            },
        ],
        "semantic_targets": ["lexicon", "language_feature"],
        "positive_examples": ["処理を止めて。"],
        "negative_examples": ["時計が止まった。"],
        "boundary_examples": ["彼を止めて。"],
        "source": _source("SEM-ACTION-001"),
        "review_status": "approved",
    }
    root = _compile_pack(tmp_path, [record])
    runtime = SemanticDataRuntime(root)
    token = Token(
        surface="止めて",
        normalized="止めて",
        reading="トメテ",
        pos=["動詞"],
        span=OriginalSpan(start=0, end=3, source_text="止めて"),
    )

    graph = runtime.enrich(
        _graph("止めて", executable=True),
        tokens=[token],
        original_text="止めて",
        conversation_context=[],
        known_entities=[],
    )

    proposition = graph.propositions[0]
    assert proposition.sense_id is None
    assert proposition.status == ItemStatus.AMBIGUOUS
    assert proposition.executable_candidate is False
    assert len(proposition.sense_candidates) == 2
    assert graph.unresolved[0]["action_sensitive"] is True
    assert graph.language_features[0].status == ItemStatus.AMBIGUOUS


def test_missing_compiled_pack_is_safe_noop(tmp_path: Path) -> None:
    runtime = SemanticDataRuntime(tmp_path / "missing")
    graph = runtime.enrich(
        _graph("確認する"),
        tokens=[],
        original_text="確認する",
        conversation_context=[],
        known_entities=[],
    )
    assert runtime.available is False
    assert graph.propositions[0].sense_id is None
    assert graph.quality_annotations["semantic_data_pack_used"] is False


def test_lexical_only_pack_never_loads_semantic_record_shards(
    tmp_path: Path,
) -> None:
    record = {
        "record_id": "LEXICAL-ONLY-001",
        "lemma": "確認",
        "surfaces": ["確認"],
        "readings": ["カクニン"],
        "part_of_speech": ["名詞"],
        "meaning_candidates": [
            {
                "candidate_id": "LEXICAL-ONLY-001:sense:001",
                "label": "内容を確かめること",
                "review_status": "needs-evidence",
            }
        ],
        "approval_scopes": {"lexical": "approved"},
        "source": _source("LEXICAL-ONLY-001"),
        "review_status": "needs-evidence",
    }
    pack_root = tmp_path / "open"
    pack_root.mkdir()
    (pack_root / "lexical.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_root = tmp_path / "review"
    compiled_root = tmp_path / "compiled"
    build_review_assets(
        open_lexicon_root=pack_root,
        context_root=tmp_path / "context",
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    compile_approved(review_root, compiled_root, shard_size=100)

    runtime = SemanticDataRuntime(compiled_root)
    assert runtime.record_count == 1
    assert runtime.runtime_record_count == 0

    def fail_if_loaded(_number: int):
        raise AssertionError("lexical-only records must not load semantic shards")

    runtime._load_shard = fail_if_loaded  # type: ignore[method-assign]
    graph = runtime.enrich(
        _graph("確認"),
        tokens=[Token(
            surface="確認",
            normalized="確認",
            reading="カクニン",
            pos=["名詞"],
            span=OriginalSpan(start=0, end=2, source_text="確認"),
        )],
        original_text="確認",
        conversation_context=[],
        known_entities=[],
    )
    assert graph.propositions[0].sense_id is None
    assert graph.quality_annotations["semantic_data_pack_record_count"] == 1
    assert graph.quality_annotations["semantic_data_runtime_record_count"] == 0
