from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.config import Settings

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.canonical_dictionary import (  # noqa: E402
    compile_canonical_dictionary,
)
from unified_semantic_data.canonical_distribution import (  # noqa: E402
    compile_public_dictionary_view,
)
from unified_semantic_data.canonical_evidence import (  # noqa: E402
    compile_evidence_enriched_dictionary,
)
from unified_semantic_data.canonical_meaning_provenance import (  # noqa: E402
    compile_meaning_provenance_view,
)
from unified_semantic_data.canonical_runtime_projection import (  # noqa: E402
    compile_runtime_projection,
)
from unified_semantic_data.pipeline import (  # noqa: E402
    build_review_assets,
    compile_approved,
)
from unified_semantic_data.semantic_labeler import (  # noqa: E402
    build_semantic_enrichment_queue,
    require_all_meanings_complete,
)
from unified_semantic_data.source_adapter_contract import (  # noqa: E402
    compile_adapter_contract,
)


APPROVAL_SCOPES = (
    "lexical",
    "semantic",
    "pragmatic",
    "task",
    "external_action",
)


def _source(dataset: str, source_id: str, *, license_name: str = "CC BY 4.0") -> dict:
    return {
        "dataset": dataset,
        "version": "fixture-1",
        "license": license_name,
        "source_id": source_id,
        "source_url": f"https://example.invalid/{dataset}/{source_id}",
        "source_sha256": hashlib.sha256(
            f"{dataset}:{source_id}".encode("utf-8")
        ).hexdigest(),
        "attribution": f"synthetic fixture: {dataset}",
        "public_runtime_eligible": "BY-NC" not in license_name,
        "source_meaning_complete": True,
        "license_metadata_complete": True,
    }


def _definition(
    record_id: str,
    *,
    surface: str,
    meaning: str,
    dataset: str,
    license_name: str = "CC BY 4.0",
) -> dict:
    return {
        "adapter_record_id": record_id,
        "source_role": "lexical-definition",
        "surface": surface,
        "readings": ["はし"],
        "reading_mappings": [
            {
                "reading": "はし",
                "restricted_to": [],
                "no_kanji": True,
            }
        ],
        "part_of_speech": "名詞",
        "domains": ["general"],
        "meaning": meaning,
        "source": _source(dataset, record_id, license_name=license_name),
    }


def _synthetic_adapter_rows() -> list[dict]:
    return [
        # 同じ表記・読み・品詞でも、意味と根拠を潰さず複数Senseとして保持する。
        _definition(
            "DEF-BRIDGE",
            surface="はし",
            meaning="川や谷などを越えて両側を結ぶ構造物",
            dataset="synthetic-bridge-dictionary",
        ),
        _definition(
            "DEF-CHOPSTICKS",
            surface="はし",
            meaning="食べ物を挟んで口へ運ぶ一対の細い道具",
            dataset="synthetic-tableware-dictionary",
        ),
        _definition(
            "DEF-EDGE",
            surface="はし",
            meaning="物の中央から最も離れた端の部分",
            dataset="synthetic-position-dictionary",
        ),
        # 内部Masterには残すが、非営利条件の意味は公開Runtimeから除外する。
        _definition(
            "DEF-RESTRICTED",
            surface="限定語",
            meaning="公開配布対象にしてはならない模擬語義",
            dataset="synthetic-restricted-dictionary",
            license_name="CC BY-NC 4.0",
        ),
        # 補助Evidenceは意味を生成せず、既存のCanonical語へだけ接続する。
        {
            "adapter_record_id": "AUX-HASHI-TRANSLATION",
            "source_role": "translation",
            "surface": "はし",
            "readings": ["はし"],
            "part_of_speech": "名詞",
            "payload": {"language": "en", "values": ["bridge", "chopsticks", "edge"]},
            "source": _source("synthetic-translation", "AUX-HASHI-TRANSLATION"),
        },
    ]


def _read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.name.endswith(".gz") else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _decision_patch(scope: str, record: dict) -> dict:
    if scope == "semantic":
        return {
            "polarity": "neutral",
            "intensity": 0.0,
            "semantic_targets": ["lexicon"],
        }
    if scope == "pragmatic":
        forbidden_by_source = {
            "DEF-BRIDGE": ["机", "食べる"],
            "DEF-CHOPSTICKS": ["机", "渡る"],
            "DEF-EDGE": ["渡る", "食べる"],
        }
        source_id = str((record.get("source") or {}).get("source_id") or "")
        return {
            "context_conditions": {
                "required_any": [],
                "required_all": [],
                "forbidden_any": forbidden_by_source.get(source_id, []),
                "required_social": [],
                "required_discourse": [],
            },
            "examples": {
                "positive": ["文脈から『はし』の意味を選ぶ。"],
                "negative": ["根拠なしに一つの意味へ固定しない。"],
                "boundary": ["『はし』だけでは複数の意味が残る。"],
            },
        }
    if scope == "task":
        return {"task_candidates": []}
    if scope == "external_action":
        return {"external_action_risk": False}
    return {}


def _write_fixture_decisions(review_root: Path, decision_root: Path) -> None:
    decisions: list[dict] = []
    for record in _read_jsonl(review_root / "review-records.jsonl"):
        for scope in APPROVAL_SCOPES:
            decisions.append(
                {
                    "decision_id": f"SYNTH-{record['record_id']}-{scope}",
                    "record_id": record["record_id"],
                    "scope": scope,
                    "status": "approved",
                    "reviewer": "synthetic-fixture-reviewer",
                    "decided_at": "2026-08-14T00:00:00Z",
                    "rationale": (
                        "模擬データに埋め込んだ期待値を検証するための明示Decision。"
                        "自動承認ではない。"
                    ),
                    "input_sha256": record["input_sha256"],
                    "patch": _decision_patch(scope, record),
                }
            )
    _write_jsonl(decision_root / "decision-ledger.jsonl", decisions)


def _compile_synthetic_factory(root: Path) -> dict[str, Path | dict]:
    adapter_input = root / "input/adapter.jsonl"
    _write_jsonl(adapter_input, _synthetic_adapter_rows())

    adapter_root = root / "adapter"
    adapter_manifest = compile_adapter_contract([adapter_input], adapter_root)
    assert adapter_manifest["boundaries"]["automatic_approval"] is False
    assert adapter_manifest["boundaries"]["runtime_promotion"] is False

    empty_context = root / "context"
    empty_system = root / "system"
    open_lexicon_root = root / "open-lexicon"
    empty_context.mkdir(parents=True)
    empty_system.mkdir(parents=True)
    open_lexicon_root.mkdir(parents=True)
    shutil.copy2(
        adapter_root / "lexical-candidates.jsonl",
        open_lexicon_root / "lexical-candidates.jsonl",
    )

    review_root = root / "review"
    first_review_manifest = build_review_assets(
        open_lexicon_root=open_lexicon_root,
        context_root=empty_context,
        pack_roots=[],
        output_root=review_root,
        system_root=empty_system,
        bulk_review=True,
    )
    assert first_review_manifest["total_records"] == 4
    assert first_review_manifest["review_queue_records"] == 4
    assert first_review_manifest["boundaries"]["automatic_approval"] is False

    decision_root = root / "decisions"
    _write_fixture_decisions(review_root, decision_root)
    reviewed_manifest = build_review_assets(
        open_lexicon_root=open_lexicon_root,
        context_root=empty_context,
        pack_roots=[],
        output_root=review_root,
        system_root=empty_system,
        decision_root=decision_root,
        bulk_review=True,
    )
    assert reviewed_manifest["review_queue_records"] == 0
    assert reviewed_manifest["decision_count"] == 4 * len(APPROVAL_SCOPES)

    semantic_report = build_semantic_enrichment_queue(
        review_root / "review-records.jsonl",
        review_root,
        reference_roots=[adapter_root / "semantic-reference.jsonl"],
    )
    require_all_meanings_complete(semantic_report)

    compiled_root = root / "compiled-semantic"
    canonical_root = root / "canonical"
    provenance_root = root / "canonical-provenance"
    enriched_root = root / "canonical-enriched"
    public_root = root / "canonical-public"
    runtime_root = root / "canonical-runtime"
    compile_approved(review_root, compiled_root, shard_size=100)
    canonical_manifest = compile_canonical_dictionary(
        review_root, canonical_root, shard_size=100
    )
    provenance_manifest = compile_meaning_provenance_view(
        review_root, canonical_root, provenance_root, shard_size=100
    )
    enriched_manifest = compile_evidence_enriched_dictionary(
        provenance_root,
        [adapter_root / "canonical-evidence.jsonl"],
        enriched_root,
        shard_size=100,
    )
    public_manifest = compile_public_dictionary_view(
        enriched_root, public_root, shard_size=100
    )
    runtime_manifest = compile_runtime_projection(
        public_root, runtime_root, shard_size=100
    )
    return {
        "adapter_root": adapter_root,
        "review_root": review_root,
        "canonical_root": canonical_root,
        "provenance_root": provenance_root,
        "enriched_root": enriched_root,
        "public_root": public_root,
        "runtime_root": runtime_root,
        "canonical_manifest": canonical_manifest,
        "provenance_manifest": provenance_manifest,
        "enriched_manifest": enriched_manifest,
        "public_manifest": public_manifest,
        "runtime_manifest": runtime_manifest,
    }


def _compiled_payloads(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_synthetic_data_runs_through_complete_dictionary_factory(
    tmp_path: Path,
) -> None:
    first = _compile_synthetic_factory(tmp_path / "first")
    second = _compile_synthetic_factory(tmp_path / "second")

    canonical_manifest = first["canonical_manifest"]
    public_manifest = first["public_manifest"]
    runtime_manifest = first["runtime_manifest"]
    assert isinstance(canonical_manifest, dict)
    assert isinstance(public_manifest, dict)
    assert isinstance(runtime_manifest, dict)
    assert canonical_manifest["record_count"] == 2
    assert canonical_manifest["sense_count"] == 4
    assert public_manifest["record_count"] == 1
    assert public_manifest["license_exclusion_count"] >= 1
    assert runtime_manifest["record_count"] == 1
    assert runtime_manifest["approved_only"] is True
    assert runtime_manifest["automatic_external_action"] is False
    assert runtime_manifest["reading_mapping_count"] == 1
    assert runtime_manifest["contextual_candidate_count"] == 3

    canonical_rows = _read_jsonl(
        Path(first["canonical_root"]) / "records/dictionary-0000.jsonl.gz"
    )
    hashi_master = next(row for row in canonical_rows if row["lemma"] == "はし")
    assert len(hashi_master["senses"]) == 3
    assert len({tuple(item["glosses"]) for item in hashi_master["senses"]}) == 3
    assert hashi_master["source_evidence_count"] == 3
    assert hashi_master["reading_mappings"] == [
        {
            "reading": "はし",
            "restricted_to": [],
            "no_kanji": True,
        }
    ]

    enriched_rows = _read_jsonl(
        Path(first["enriched_root"]) / "records/dictionary-0000.jsonl.gz"
    )
    hashi_enriched = next(row for row in enriched_rows if row["lemma"] == "はし")
    assert hashi_enriched["auxiliary_evidence_count"] == 1
    assert hashi_enriched["auxiliary_evidence"]["translation"][0][
        "evidence_id"
    ] == "AUX-HASHI-TRANSLATION"

    public_rows = _read_jsonl(
        Path(first["public_root"]) / "records/dictionary-0000.jsonl.gz"
    )
    assert [row["lemma"] for row in public_rows] == ["はし"]
    assert all(
        "BY-NC" not in source["license"]
        for row in public_rows
        for source in row["source_evidence"]
    )

    runtime_root = Path(first["runtime_root"])
    runtime_rows = _read_jsonl(runtime_root / "records/records-0000.jsonl.gz")
    assert len(runtime_rows[0]["meaning_candidates"]) == 3
    assert {
        candidate["glosses"][0]
        for candidate in runtime_rows[0]["meaning_candidates"]
    } == {
        "川や谷などを越えて両側を結ぶ構造物",
        "食べ物を挟んで口へ運ぶ一対の細い道具",
        "物の中央から最も離れた端の部分",
    }
    assert runtime_rows[0]["reading_mappings"] == hashi_master["reading_mappings"]
    assert runtime_rows[0]["context_conditions"]["required_any"] == []
    contexts_by_gloss = {
        candidate["glosses"][0]: candidate["context"]
        for candidate in runtime_rows[0]["meaning_candidates"]
    }
    assert contexts_by_gloss["川や谷などを越えて両側を結ぶ構造物"][
        "forbidden_any"
    ] == ["机", "食べる"]
    assert contexts_by_gloss["食べ物を挟んで口へ運ぶ一対の細い道具"][
        "forbidden_any"
    ] == ["机", "渡る"]
    assert contexts_by_gloss["物の中央から最も離れた端の部分"][
        "forbidden_any"
    ] == ["渡る", "食べる"]

    settings = Settings(
        system_dict_dir=ROOT / "dictionaries/system",
        user_dict_dir=ROOT / "dictionaries/user",
        semantic_data_runtime_dir=runtime_root,
        hard_deadline_ms=5000,
    )
    engine = ParserEngine(settings)
    response = engine.analyze(AnalyzeRequest(original_text="はし", deadline_ms=5000))
    assert engine.semantic_data.root == runtime_root
    assert response.meaning_graph.quality_annotations[
        "semantic_data_pack_used"
    ] is True
    assert response.meaning_graph.quality_annotations[
        "semantic_data_pack_match_count"
    ] >= 1
    assert response.meaning_graph.quality_annotations[
        "semantic_data_pack_resolved_count"
    ] == 0
    assert response.meaning_graph.quality_annotations[
        "semantic_data_pack_ambiguous_count"
    ] >= 1

    expected_senses = {
        "はしを渡る": "川や谷などを越えて両側を結ぶ構造物",
        "はしで食べる": "食べ物を挟んで口へ運ぶ一対の細い道具",
        "机のはしに置く": "物の中央から最も離れた端の部分",
    }
    for text, expected_label in expected_senses.items():
        contextual = engine.analyze(
            AnalyzeRequest(original_text=text, deadline_ms=5000)
        )
        assert contextual.meaning_graph.quality_annotations[
            "semantic_data_pack_resolved_count"
        ] >= 1
        assert any(
            proposition.sense_label == expected_label
            for proposition in contextual.meaning_graph.propositions
        )

    # 同じ模擬入力を再実行しても、最終辞書とRuntimeはByte単位で同一。
    for key in (
        "canonical_root",
        "provenance_root",
        "enriched_root",
        "public_root",
        "runtime_root",
    ):
        assert _compiled_payloads(Path(first[key])) == _compiled_payloads(
            Path(second[key])
        )


def test_synthetic_factory_fails_closed_before_review(tmp_path: Path) -> None:
    adapter_input = tmp_path / "adapter.jsonl"
    _write_jsonl(adapter_input, _synthetic_adapter_rows()[:1])
    adapter_root = tmp_path / "adapter"
    compile_adapter_contract([adapter_input], adapter_root)
    open_lexicon_root = tmp_path / "open-lexicon"
    open_lexicon_root.mkdir()
    shutil.copy2(
        adapter_root / "lexical-candidates.jsonl",
        open_lexicon_root / "lexical-candidates.jsonl",
    )
    review_root = tmp_path / "review"
    manifest = build_review_assets(
        open_lexicon_root=open_lexicon_root,
        context_root=tmp_path / "missing-context",
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "missing-system",
        bulk_review=True,
    )
    semantic_report = build_semantic_enrichment_queue(
        review_root / "review-records.jsonl",
        review_root,
        reference_roots=[adapter_root / "semantic-reference.jsonl"],
    )
    assert manifest["review_queue_records"] == 1
    assert semantic_report.get("runtime_semantic_incomplete_records", 0) == 0
    assert _read_jsonl(review_root / "approved-records.jsonl") == []
