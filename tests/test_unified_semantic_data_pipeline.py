from __future__ import annotations

import argparse
import gzip
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
    with gzip.open(
        compiled_root / "indexes/surface-index.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        surface_index = json.load(handle)
    assert surface_index["形成的評価"] == ["OPEN-001"]
    assert surface_index["校内ルーブリック"] == ["USER-001"]


def test_missing_meaning_is_reviewed_not_promoted(tmp_path: Path) -> None:
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
    assert manifest["runtime_eligible_records"] == 0
    queue = _read_jsonl(review_root / "review-queue.jsonl")
    assert queue[0]["review_blockers"] == ["meaning-candidate-required"]
    assert (review_root / "runtime-candidates.jsonl").read_text(
        encoding="utf-8"
    ) == ""


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
