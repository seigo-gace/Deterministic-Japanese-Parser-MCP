from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.pipeline import (  # noqa: E402
    build_review_assets,
    check_determinism,
    compile_approved,
)


def _source(source_id: str) -> dict:
    return {
        "dataset": "project-fixture",
        "version": "1.0.0",
        "license": "MIT",
        "source_id": source_id,
        "source_url": "https://example.invalid/fixture",
        "source_sha256": "a" * 64,
        "evidence_scope": "runtime_data",
        "attribution": "test fixture",
    }


def _approved_record(record_id: str, surface: str) -> dict:
    return {
        "record_id": record_id,
        "lemma": surface,
        "surfaces": [surface],
        "readings": ["けいせいてきひょうか"],
        "part_of_speech": ["名詞"],
        "domains": ["education"],
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": "学習途中の理解を把握し指導改善へ使う評価",
                "glosses": ["学習途中の理解を把握し指導改善へ使う評価"],
                "domains": ["education"],
                "parameters": {},
                "evidence_ids": [f"evidence:{record_id}"],
                "review_status": "approved",
            }
        ],
        "semantic_targets": ["lexicon"],
        "source": _source(record_id),
        "review_status": "approved",
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_pipeline_accepts_lexicon_context_domain_and_user_sources(tmp_path: Path) -> None:
    open_root = tmp_path / "open"
    context_root = tmp_path / "context"
    domain_root = tmp_path / "domain_packs"
    user_root = tmp_path / "user_packs"
    system_root = tmp_path / "system"
    review_root = tmp_path / "review"
    compiled_root = tmp_path / "compiled"
    open_root.mkdir()
    context_root.mkdir()
    domain_root.mkdir()
    user_root.mkdir()
    system_root.mkdir()

    open_record = _approved_record("OPEN-001", "形成的評価")
    (open_root / "open.jsonl").write_text(
        json.dumps(open_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    context_record = {
        **_approved_record("CTX-001", "エグい"),
        "entry_id": "CTX-001",
        "record_id": None,
        "feature_type": "slang",
        "semantic_targets": ["lexicon", "language_feature"],
        "positive_examples": ["この性能はエグい。"],
        "negative_examples": ["えぐみがある。"],
        "boundary_examples": ["損失がエグい。"],
    }
    (context_root / "context.yaml").write_text(
        yaml.safe_dump(context_record, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    domain_record = _approved_record("DOMAIN-001", "概念地図")
    (domain_root / "education.yaml").write_text(
        yaml.safe_dump(domain_record, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    user_record = _approved_record("USER-001", "校内ルーブリック")
    (user_root / "local.yaml").write_text(
        yaml.safe_dump(user_record, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    manifest = build_review_assets(
        open_lexicon_root=open_root,
        context_root=context_root,
        pack_roots=[domain_root, user_root],
        output_root=review_root,
        system_root=system_root,
    )
    assert manifest["total_records"] == 4
    assert manifest["source_counts"] == {
        "context": 1,
        "domain_pack": 1,
        "open_lexicon": 1,
        "user_pack": 1,
    }
    assert manifest["runtime_eligible_records"] == 4

    compiled = compile_approved(review_root, compiled_root, shard_size=100)
    assert compiled["record_count"] == 4
    assert compiled["approved_only"] is True
    assert compiled["automatic_external_action"] is False
    assert compiled["pack_namespaces"] == {
        "core": 2,
        "domains": 1,
        "user": 1,
    }
    for namespace in ("core", "domains", "user"):
        assert (compiled_root / namespace / "manifest.json").exists()
    with gzip.open(
        compiled_root / "indexes/surface-index.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        surface_index = json.load(handle)
    assert surface_index["形成的評価"] == ["OPEN-001"]
    assert surface_index["校内ルーブリック"] == ["USER-001"]


def test_open_lexicon_without_meaning_compiles_lexical_scope_only(
    tmp_path: Path,
) -> None:
    open_root = tmp_path / "open"
    open_root.mkdir()
    raw = _approved_record("OPEN-UNRESOLVED", "未確定語")
    raw.pop("meaning_candidates")
    (open_root / "open.jsonl").write_text(
        json.dumps(raw, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_root = tmp_path / "review"
    manifest = build_review_assets(
        open_lexicon_root=open_root,
        context_root=tmp_path / "missing-context",
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    assert manifest["total_records"] == 1
    assert manifest["runtime_eligible_records"] == 1
    assert manifest["review_queue_records"] == 0
    queue = _read_jsonl(review_root / "review-queue.jsonl")
    assert queue == []
    approved = _read_jsonl(review_root / "approved-records.jsonl")
    assert approved[0]["approval"]["approved_scopes"] == ["lexical"]
    compiled_root = tmp_path / "compiled"
    compile_approved(review_root, compiled_root, shard_size=100)
    with gzip.open(
        compiled_root / "records/records-0000.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        compiled = json.loads(next(handle))
    assert compiled["meaning_candidates"] == []


def test_context_judgment_is_split_into_bounded_review_batches(
    tmp_path: Path,
) -> None:
    context_root = tmp_path / "context"
    context_root.mkdir()
    for number in range(21):
        raw = _approved_record(f"CTX-{number:03d}", f"候補{number}")
        raw["review_status"] = "needs-evidence"
        raw["feature_type"] = "slang"
        raw["semantic_targets"] = ["lexicon", "language_feature"]
        raw["positive_examples"] = ["肯定例"]
        raw["negative_examples"] = ["否定例"]
        raw["boundary_examples"] = ["境界例"]
        (context_root / f"{number:03d}.yaml").write_text(
            yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8"
        )
    review_root = tmp_path / "review"
    manifest = build_review_assets(
        open_lexicon_root=tmp_path / "open",
        context_root=context_root,
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    assert manifest["review_queue_records"] == 21
    assert manifest["review_batch_count"] == 2
    first = json.loads(
        (review_root / "review-batches/batch-0001.json").read_text(
            encoding="utf-8"
        )
    )
    second = json.loads(
        (review_root / "review-batches/batch-0002.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(first["records"]) == 20
    assert len(second["records"]) == 1
    assert first["runtime_promotion_allowed"] is False


def test_explicit_digest_bound_decision_approves_only_selected_scope(
    tmp_path: Path,
) -> None:
    domain_root = tmp_path / "domain_packs"
    domain_root.mkdir()
    raw = _approved_record("DOMAIN-REVIEW-001", "学習分析")
    raw["review_status"] = "needs-evidence"
    source_path = domain_root / "education.yaml"
    source_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8"
    )
    decision_root = tmp_path / "decisions"
    decision_root.mkdir()
    decision = {
        "decision_id": "DEC-001",
        "record_id": "DOMAIN-REVIEW-001",
        "scope": "semantic",
        "status": "approved",
        "reviewer": "gpt-app-directed-review",
        "decided_at": "2026-08-06T12:00:00+09:00",
        "rationale": "根拠と意味候補を確認した。",
        "input_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }
    (decision_root / "education.jsonl").write_text(
        json.dumps(decision, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    review_root = tmp_path / "review"
    manifest = build_review_assets(
        open_lexicon_root=tmp_path / "open",
        context_root=tmp_path / "context",
        pack_roots=[domain_root],
        output_root=review_root,
        system_root=tmp_path / "system",
        decision_root=decision_root,
    )
    record = _read_jsonl(review_root / "review-records.jsonl")[0]
    assert manifest["decision_count"] == 1
    assert record["approval"]["approved_scopes"] == ["semantic"]
    assert record["approval"]["review_scopes"] == ["lexical"]
    assert manifest["runtime_eligible_records"] == 0


def test_pipeline_is_byte_deterministic(tmp_path: Path) -> None:
    open_root = tmp_path / "open"
    open_root.mkdir()
    (open_root / "open.jsonl").write_text(
        json.dumps(_approved_record("OPEN-DET", "決定性"), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        open_lexicon_root=open_root,
        context_root=tmp_path / "context",
        pack_root=[],
        system_root=tmp_path / "system",
        shard_size=100,
    )
    result = check_determinism(args)
    assert result["status"] == "CHECKED"
    assert len(result["digest"]) == 64
