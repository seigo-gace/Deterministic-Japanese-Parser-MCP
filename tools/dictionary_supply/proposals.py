from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

import yaml

from .common import LexiconRecord, normalize_text, stable_id

PROPOSAL_SCHEMA_VERSION = "2.0.0"

_INTENT_MARKERS = {
    "prohibition": (
        "するな", "しないで", "禁止", "不可", "やめて", "触らないで",
    ),
    "preserve": (
        "残せ", "残して", "維持", "壊すな", "変えないで", "そのまま",
    ),
    "modify": (
        "変更", "修正", "更新", "直す", "書き換え", "入れ替え",
    ),
    "remove": (
        "削除", "消す", "外す", "除く", "撤去", "廃止",
    ),
    "comparison": (
        "比較", "比べる", "違い", "どちら", "優劣", "対比",
    ),
    "decision": (
        "決定", "採用", "選ぶ", "確定", "決める", "選定",
    ),
    "verification_criteria": (
        "検証", "確認", "テスト", "証明", "確かめる", "再現",
    ),
    "action": (
        "公開", "反映", "実行", "配布", "送信", "登録", "接続",
    ),
    "condition": (
        "なら", "場合", "とき", "たら", "れば", "条件",
    ),
    "exception": (
        "除く", "以外", "例外", "ただし", "のみ", "だけ",
    ),
    "priority": (
        "先に", "優先", "最初", "第一", "後回し", "急ぎ",
    ),
    "question": (
        "何", "なぜ", "どう", "どこ", "いつ", "誰", "ですか", "なのか",
    ),
}

_IDIOM_CATEGORIES = {"idiom", "phrase", "proverb"}


@dataclass
class Proposal:
    proposal_id: str
    kind: str
    status: str
    payload: dict
    source_record_ids: list[str]
    evidence: list[dict]
    conflicts: list[dict]
    score: int
    review_notes: list[str]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["schema_version"] = PROPOSAL_SCHEMA_VERSION
        return value


def _proposal_id(kind: str, *parts: str) -> str:
    return stable_id(f"PROP-{kind.upper()}", *parts)


def _first_japanese_gloss(record: LexiconRecord) -> str | None:
    for sense in record.senses:
        if (
            sense.get("language") == "ja"
            and normalize_text(sense.get("gloss", ""))
        ):
            return normalize_text(sense["gloss"])
    return None


def _intent_candidates(texts: Iterable[str]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    joined = "\n".join(
        normalize_text(item) for item in texts if item
    )
    for intent, markers in _INTENT_MARKERS.items():
        for marker in markers:
            if marker in joined:
                candidates.append((intent, marker))
                break
    return candidates


def _score(record: LexiconRecord, *, kind: str) -> int:
    score = 0
    if record.senses:
        score += 25
    if _first_japanese_gloss(record):
        score += 25
    if record.readings:
        score += 10
    if record.part_of_speech or record.lexical_category:
        score += 10
    if record.synonyms or record.antonyms or record.related:
        score += 10
    if kind == "metaphor" and (
        record.lexical_category in _IDIOM_CATEGORIES
        or any(item in _IDIOM_CATEGORIES for item in record.part_of_speech)
    ):
        score += 20
    return min(score, 100)


def build_proposals(
    records: Iterable[LexiconRecord],
    *,
    existing_metaphor_surfaces: set[str] | None = None,
    existing_rule_patterns: set[str] | None = None,
    existing_synonym_surfaces: set[str] | None = None,
) -> list[Proposal]:
    existing_metaphor_surfaces = existing_metaphor_surfaces or set()
    existing_rule_patterns = existing_rule_patterns or set()
    existing_synonym_surfaces = existing_synonym_surfaces or set()
    proposals: list[Proposal] = []

    for record in records:
        record.validate()
        source_evidence = [{
            "dataset": record.source.dataset,
            "version": record.source.version,
            "license": record.source.license,
            "source_id": record.source.source_id,
            "source_url": record.source.source_url,
            "source_sha256": record.source.source_sha256,
            "attribution": record.source.attribution,
        }]
        proposals.append(Proposal(
            proposal_id=_proposal_id("lexicon", record.record_id),
            kind="lexicon",
            status="needs_review",
            payload={"record": record.to_dict()},
            source_record_ids=[record.record_id],
            evidence=source_evidence,
            conflicts=[],
            score=_score(record, kind="lexicon"),
            review_notes=[],
        ))

        gloss = _first_japanese_gloss(record)
        category_values = {
            record.lexical_category,
            *record.part_of_speech,
        }
        if gloss and category_values.intersection(_IDIOM_CATEGORIES):
            surfaces = [record.lemma, *record.surfaces]
            conflicts = [
                {
                    "type": "existing_metaphor_surface",
                    "surface": surface,
                }
                for surface in surfaces
                if surface in existing_metaphor_surfaces
            ]
            proposals.append(Proposal(
                proposal_id=_proposal_id(
                    "metaphor", record.record_id, gloss
                ),
                kind="metaphor",
                status="needs_review",
                payload={
                    "expression": record.lemma,
                    "aliases": [
                        item
                        for item in record.surfaces
                        if item != record.lemma
                    ],
                    "interpretation": gloss,
                    "context": [
                        *record.domains,
                        *record.usage_labels,
                    ],
                    "context_policy": (
                        "required_any"
                        if len(record.lemma) <= 3
                        and (record.domains or record.usage_labels)
                        else "optional"
                    ),
                    "domain": (
                        record.domains[0]
                        if record.domains
                        else "general"
                    ),
                    "version": "generated-review",
                },
                source_record_ids=[record.record_id],
                evidence=source_evidence,
                conflicts=conflicts,
                score=_score(record, kind="metaphor"),
                review_notes=[
                    "Confirm that the expression is non-literal in the target context."
                ],
            ))

        if record.synonyms or len(record.surfaces) > 1:
            surfaces = [
                item
                for item in [*record.surfaces, *record.synonyms]
                if item != record.lemma
            ]
            conflicts = [
                {
                    "type": "existing_synonym_surface",
                    "surface": surface,
                }
                for surface in surfaces
                if surface in existing_synonym_surfaces
            ]
            proposals.append(Proposal(
                proposal_id=_proposal_id("synonym", record.record_id),
                kind="synonym",
                status="needs_review",
                payload={
                    "canonical": record.lemma,
                    "surfaces": surfaces,
                    "sense_ids": [
                        item.get("sense_id")
                        for item in record.senses
                    ],
                },
                source_record_ids=[record.record_id],
                evidence=source_evidence,
                conflicts=conflicts,
                score=_score(record, kind="synonym"),
                review_notes=[
                    "Remove near-synonyms that are not interchangeable in the same sense."
                ],
            ))

        texts = [
            record.lemma,
            *record.surfaces,
            *[
                item.get("gloss", "")
                for item in record.senses
            ],
        ]
        for intent, marker in _intent_candidates(texts):
            literal = record.lemma
            pattern = (
                rf"(?P<target>.+?)(?:を|に|は)?{re.escape(literal)}"
                rf"(?:する|しろ|して|してください|してくれ)?[。！？!?]?$"
            )
            conflicts = []
            if pattern in existing_rule_patterns:
                conflicts.append({
                    "type": "existing_rule_pattern",
                    "pattern": pattern,
                })
            proposals.append(Proposal(
                proposal_id=_proposal_id(
                    "rule", record.record_id, intent, marker
                ),
                kind="rule",
                status="needs_review",
                payload={
                    "intent": intent,
                    "rule": {
                        "id": stable_id(
                            "AUTO-RULE",
                            record.record_id,
                            intent,
                        ),
                        "pattern": pattern,
                        "priority": 20,
                        "value": "{target}",
                        "index_literals": [literal],
                    },
                    "marker": marker,
                },
                source_record_ids=[record.record_id],
                evidence=source_evidence,
                conflicts=conflicts,
                score=max(
                    20,
                    _score(record, kind="rule") - 20,
                ),
                review_notes=[
                    "Rule proposal is never auto-approved; verify target capture, scope and negative examples."
                ],
            ))

    unique: dict[str, Proposal] = {}
    for proposal in proposals:
        existing = unique.get(proposal.proposal_id)
        if existing is None or proposal.score > existing.score:
            unique[proposal.proposal_id] = proposal
    return sorted(
        unique.values(),
        key=lambda item: (
            -item.score,
            item.kind,
            item.proposal_id,
        ),
    )


def write_bundle(
    path: Path,
    *,
    batch_id: str,
    proposals: Iterable[Proposal],
    input_files: Iterable[Path],
) -> dict:
    values = [item.to_dict() for item in proposals]
    counts = Counter(item["kind"] for item in values)
    payload = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "batch_id": batch_id,
        "status": "needs_review",
        "input_files": [str(item) for item in input_files],
        "counts": dict(sorted(counts.items())),
        "proposals": values,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    payload["bundle_sha256"] = hashlib.sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return payload


def load_bundle(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if value.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported proposal schema: {value.get('schema_version')}"
        )
    ids: set[str] = set()
    for proposal in value.get("proposals", []):
        proposal_id = proposal.get("proposal_id")
        if not proposal_id:
            raise ValueError("proposal_id is required")
        if proposal_id in ids:
            raise ValueError(f"duplicate proposal_id: {proposal_id}")
        ids.add(proposal_id)
        if proposal.get("status") not in {
            "needs_review",
            "approved",
            "rejected",
            "blocked",
        }:
            raise ValueError(
                "invalid proposal status: "
                f"{proposal_id}: {proposal.get('status')}"
            )
    return value
