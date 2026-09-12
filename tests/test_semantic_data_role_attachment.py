from __future__ import annotations

import gzip
import json
from pathlib import Path

from deterministic_japanese_parser_mcp.models import (
    Argument,
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    Token,
)
from deterministic_japanese_parser_mcp.semantic_data_runtime import SemanticDataRuntime


def _write_json_gzip(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)


def _record(
    record_id: str,
    *,
    lemma: str,
    reading: str,
    part_of_speech: list[str],
    candidates: list[tuple[str, str]],
) -> dict:
    return {
        "record_id": record_id,
        "lemma": lemma,
        "surfaces": [lemma],
        "readings": [reading],
        "part_of_speech": part_of_speech,
        "risk_class": "semantic",
        "semantic_targets": ["lexicon"],
        "meaning_candidates": [
            {
                "candidate_id": candidate_id,
                "label": label,
                "review_status": "approved",
            }
            for candidate_id, label in candidates
        ],
        "approval": {
            "approved_scopes": ["semantic"],
            "blockers_by_scope": {},
        },
    }


def _pack(tmp_path: Path, records: list[dict]) -> SemanticDataRuntime:
    root = tmp_path / "compiled"
    indexes = root / "indexes"
    store = root / "records"
    indexes.mkdir(parents=True)
    store.mkdir(parents=True)

    with gzip.open(store / "records-0000.jsonl.gz", "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    surface_index: dict[str, list[str]] = {}
    reading_index: dict[str, list[str]] = {}
    locator: dict[str, dict[str, int]] = {}
    for line, record in enumerate(records, 1):
        for surface in record["surfaces"]:
            surface_index.setdefault(surface, []).append(record["record_id"])
        for reading in record["readings"]:
            reading_index.setdefault(reading, []).append(record["record_id"])
        locator[record["record_id"]] = {"shard": 0, "line": line}

    (root / "manifest.json").write_text(
        json.dumps(
            {
                "approved_only": True,
                "automatic_external_action": False,
                "preserve_ambiguity": True,
                "record_count": len(records),
                "runtime_record_count": len(records),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for prefix in ("", "runtime-"):
        _write_json_gzip(indexes / f"{prefix}surface-index.json.gz", surface_index)
        _write_json_gzip(indexes / f"{prefix}reading-index.json.gz", reading_index)
        _write_json_gzip(indexes / f"{prefix}record-locator.json.gz", locator)
    return SemanticDataRuntime(root)


def _token(
    surface: str,
    normalized: str,
    reading: str,
    pos: list[str],
    start: int,
    end: int,
) -> Token:
    return Token(
        surface=surface,
        normalized=normalized,
        reading=reading,
        pos=pos,
        span=OriginalSpan(start=start, end=end, source_text=surface),
    )


def test_argument_sense_does_not_overwrite_predicate_sense(tmp_path: Path) -> None:
    runtime = _pack(
        tmp_path,
        [
            _record(
                "SEM-NEKO-001",
                lemma="猫",
                reading="ネコ",
                part_of_speech=["名詞"],
                candidates=[("SEM-NEKO-001:animal", "ネコ科の哺乳類")],
            ),
            _record(
                "SEM-TABERU-001",
                lemma="食べる",
                reading="タベル",
                part_of_speech=["動詞"],
                candidates=[("SEM-TABERU-001:ingest", "食物を口から取り入れる")],
            ),
        ],
    )
    text = "猫が魚を食べた"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="食べる",
                intent_type="observation",
                value=text,
                source_span=OriginalSpan(start=0, end=len(text), source_text=text),
                arguments=[
                    Argument(
                        role="agent",
                        value="猫",
                        span=OriginalSpan(start=0, end=1, source_text="猫"),
                    )
                ],
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[
            _token("猫", "猫", "ネコ", ["名詞", "普通名詞", "一般"], 0, 1),
            _token("食べ", "食べる", "タベ", ["動詞"], 4, 6),
        ],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    assert proposition.sense_id == "SEM-TABERU-001:ingest"
    assert proposition.sense_label == "食物を口から取り入れる"
    agent = proposition.arguments[0]
    assert agent.sense_id == "SEM-NEKO-001:animal"
    assert agent.sense_label == "ネコ科の哺乳類"


def test_argument_only_match_leaves_predicate_sense_unset(tmp_path: Path) -> None:
    runtime = _pack(
        tmp_path,
        [
            _record(
                "SEM-UI-001",
                lemma="UI",
                reading="ユーアイ",
                part_of_speech=["名詞"],
                candidates=[("SEM-UI-001:interface", "利用者と接する部分")],
            )
        ],
    )
    text = "UIは残せ"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="維持する",
                intent_type="preserve",
                value="UI",
                source_span=OriginalSpan(start=0, end=len(text), source_text=text),
                arguments=[
                    Argument(
                        role="object",
                        value="UI",
                        span=OriginalSpan(start=0, end=2, source_text="UI"),
                    )
                ],
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[_token("UI", "UI", "ユーアイ", ["名詞", "普通名詞", "一般"], 0, 2)],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    # 維持する is a canonical intent predicate with no lexical match, so the
    # object sense must stay on the object instead of naming the predicate.
    assert proposition.sense_id is None
    assert proposition.sense_label is None
    assert proposition.arguments[0].sense_id == "SEM-UI-001:interface"
    assert "approved-semantic-data-pack" in proposition.inference_sources


def test_suru_noun_heads_its_light_verb_predicate(tmp_path: Path) -> None:
    runtime = _pack(
        tmp_path,
        [
            _record(
                "SEM-HENKOU-001",
                lemma="変更",
                reading="ヘンコウ",
                part_of_speech=["名詞"],
                candidates=[("SEM-HENKOU-001:change", "内容を別のものにすること")],
            )
        ],
    )
    text = "APIを変更しろ"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="変更する",
                intent_type="observation",
                value=text,
                source_span=OriginalSpan(start=0, end=len(text), source_text=text),
                arguments=[
                    Argument(
                        role="object",
                        value="API",
                        span=OriginalSpan(start=0, end=3, source_text="API"),
                    )
                ],
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[
            _token(
                "変更",
                "変更",
                "ヘンコウ",
                ["名詞", "普通名詞", "サ変可能"],
                4,
                6,
            )
        ],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    assert proposition.sense_id == "SEM-HENKOU-001:change"
    assert proposition.arguments[0].sense_id is None


def test_clause_sense_still_attaches_without_role_structure(tmp_path: Path) -> None:
    runtime = _pack(
        tmp_path,
        [
            _record(
                "SEM-HASHI-001",
                lemma="橋",
                reading="ハシ",
                part_of_speech=["名詞"],
                candidates=[("SEM-HASHI-001:bridge", "両岸を結ぶ構造物")],
            )
        ],
    )
    text = "橋"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="評価する",
                intent_type="observation",
                value=text,
                source_span=OriginalSpan(start=0, end=1, source_text=text),
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[_token("橋", "橋", "ハシ", ["名詞", "普通名詞", "一般"], 0, 1)],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    # No argument spans and no head token, so the clause is the only site left.
    assert enriched.propositions[0].sense_id == "SEM-HASHI-001:bridge"


def test_tied_candidates_report_confidence_below_resolved_floor(
    tmp_path: Path,
) -> None:
    runtime = _pack(
        tmp_path,
        [
            _record(
                "SEM-WATARU-001",
                lemma="渡る",
                reading="ワタル",
                part_of_speech=["動詞"],
                candidates=[
                    ("SEM-WATARU-001:cross", "横切って向こう側へ行く"),
                    ("SEM-WATARU-001:travel", "各地を転々と旅行する"),
                ],
            )
        ],
    )
    text = "渡る"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="渡る",
                intent_type="observation",
                value=text,
                source_span=OriginalSpan(start=0, end=2, source_text=text),
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[_token("渡る", "渡る", "ワタル", ["動詞"], 0, 2)],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    # Both readings score the same, so the order came from the candidate id.
    # The reported confidence must stay under the resolved floor.
    assert len(proposition.sense_candidates) == 2
    assert (
        proposition.sense_candidates[0].score
        == proposition.sense_candidates[1].score
    )
    assert 0.0 < proposition.sense_confidence < 0.70
    assert enriched.quality_annotations["semantic_data_pack_ambiguous_count"] == 1


def test_ambiguous_action_argument_stays_fail_closed(tmp_path: Path) -> None:
    record = _record(
        "SEM-SORE-001",
        lemma="それ",
        reading="ソレ",
        part_of_speech=["代名詞"],
        candidates=[
            ("SEM-SORE-001:file", "直前に触れた対象"),
            ("SEM-SORE-001:topic", "すでに話題にした事柄"),
        ],
    )
    record["risk_class"] = "action"
    runtime = _pack(tmp_path, [record])
    text = "それを切って"
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="切る",
                intent_type="modify",
                value=text,
                executable_candidate=True,
                source_span=OriginalSpan(start=0, end=len(text), source_text=text),
                arguments=[
                    Argument(
                        role="object",
                        value="それ",
                        span=OriginalSpan(start=0, end=2, source_text="それ"),
                    )
                ],
            )
        ]
    )

    enriched = runtime.enrich(
        graph,
        tokens=[_token("それ", "それ", "ソレ", ["代名詞"], 0, 2)],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    argument = proposition.arguments[0]
    assert argument.sense_id is None
    assert argument.status == ItemStatus.AMBIGUOUS
    assert argument.sense_candidates
    assert proposition.executable_candidate is False
    assert any(
        item.get("type") == "semantic_data_pack" and item.get("action_sensitive")
        for item in enriched.unresolved
    )
