from __future__ import annotations

from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from .models import MeaningGraph, OriginalSpan, Proposition, SenseCandidate, Token


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", value).casefold()


def _load_json_gzip(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _overlap(left: OriginalSpan, right: OriginalSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _stable_hash(graph: MeaningGraph) -> str:
    payload = graph.model_dump(exclude={"semantic_hash"}, mode="json")
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class SemanticCandidateRuntime:
    """Expose source-validated review-pending meanings without selecting them."""

    def __init__(self, root: Path, *, shard_cache_size: int = 4):
        self.root = Path(root)
        self.available = False
        self.manifest: dict[str, Any] = {}
        self.surface_index: dict[str, list[str]] = {}
        self.reading_index: dict[str, list[str]] = {}
        self.record_locator: dict[str, dict[str, int]] = {}
        self.shard_cache_size = max(1, shard_cache_size)
        self._shards: OrderedDict[int, dict[str, dict[str, Any]]] = OrderedDict()
        self.last_metrics: dict[str, int | float] = {
            "semantic_candidate_pack_available": 0,
            "semantic_candidate_pack_record_count": 0,
            "semantic_candidate_pack_match_count": 0,
            "semantic_candidate_pack_sense_count": 0,
        }

        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {
            "candidate_only": True,
            "approved_semantic_effects": False,
            "automatic_sense_selection": False,
            "automatic_parameter_application": False,
            "automatic_external_action": False,
            "preserve_ambiguity": True,
        }
        for name, expected in required.items():
            if manifest.get(name) is not expected:
                raise ValueError(
                    f"semantic candidate pack safety flag mismatch: {name}"
                )
        index_root = self.root / "indexes"
        paths = {
            "surface": index_root / "surface-index.json.gz",
            "reading": index_root / "reading-index.json.gz",
            "locator": index_root / "record-locator.json.gz",
        }
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "compiled semantic candidate indexes are incomplete: "
                + ", ".join(missing)
            )
        self.manifest = manifest
        self.surface_index = _load_json_gzip(paths["surface"])
        self.reading_index = _load_json_gzip(paths["reading"])
        self.record_locator = _load_json_gzip(paths["locator"])
        if len(self.record_locator) != int(manifest.get("record_count", 0)):
            raise ValueError("semantic candidate locator count mismatch")
        self.available = True
        self.last_metrics = {
            "semantic_candidate_pack_available": 1,
            "semantic_candidate_pack_record_count": int(
                manifest.get("record_count", 0)
            ),
            "semantic_candidate_pack_match_count": 0,
            "semantic_candidate_pack_sense_count": 0,
        }

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("record_count", 0))

    def _load_shard(self, number: int) -> dict[str, dict[str, Any]]:
        cached = self._shards.get(number)
        if cached is not None:
            self._shards.move_to_end(number)
            return cached
        path = self.root / "records" / f"records-{number:04d}.jsonl.gz"
        if not path.exists():
            raise FileNotFoundError(path)
        records: dict[str, dict[str, Any]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                item = json.loads(line)
                record_id = item.get("record_id")
                if not record_id:
                    raise ValueError(
                        f"candidate record_id missing: {path}:{line_number}"
                    )
                if item.get("runtime_mode") != "candidate-only":
                    raise ValueError(
                        f"non-candidate record in candidate pack: {record_id}"
                    )
                if item.get("automatic_sense_selection_allowed") is not False:
                    raise ValueError(
                        f"candidate sense selection boundary missing: {record_id}"
                    )
                records[record_id] = item
        self._shards[number] = records
        self._shards.move_to_end(number)
        while len(self._shards) > self.shard_cache_size:
            self._shards.popitem(last=False)
        return records

    def _record(self, record_id: str) -> dict[str, Any]:
        location = self.record_locator.get(record_id)
        if location is None:
            raise KeyError(record_id)
        record = self._load_shard(int(location["shard"])).get(record_id)
        if record is None:
            raise KeyError(record_id)
        return record

    def lookup_token(
        self,
        token: Token,
        *,
        max_records: int = 16,
    ) -> list[dict[str, Any]]:
        if not self.available:
            return []
        record_ids: list[str] = []
        for value in (token.surface, token.normalized):
            for record_id in self.surface_index.get(_normalize(value), []):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        if not record_ids and token.reading:
            for record_id in self.reading_index.get(
                _normalize(token.reading), []
            ):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        return [self._record(record_id) for record_id in record_ids[:max_records]]

    @staticmethod
    def _score(
        record: dict[str, Any],
        candidate: dict[str, Any],
        *,
        token: Token,
        context_text: str,
    ) -> tuple[int, list[str]]:
        score = 50
        evidence = [
            "source_validated_candidate_only",
            f"candidate_record:{record['record_id']}",
        ]
        token_pos = " ".join(token.pos).casefold()
        record_pos = " ".join(record.get("part_of_speech", [])).casefold()
        if token_pos and record_pos:
            token_families = {
                value for value in re.split(r"[^\w一-龥ぁ-んァ-ヶ]+", token_pos)
                if len(value) >= 2
            }
            if any(value in record_pos for value in token_families):
                score += 10
                evidence.append("candidate_pos_match")
        domains = [
            *record.get("domains", []),
            *candidate.get("domains", []),
        ]
        matched_domain = next(
            (
                str(domain)
                for domain in domains
                if str(domain)
                and str(domain).casefold() in context_text.casefold()
            ),
            None,
        )
        if matched_domain:
            score += 5
            evidence.append(f"candidate_domain:{matched_domain}")
        if candidate.get("evidence_ids"):
            score += 1
            evidence.append("candidate_source_evidence")
        return score, evidence

    @staticmethod
    def _related_indices(
        propositions: list[Proposition], token: Token
    ) -> list[int]:
        return [
            index
            for index, proposition in enumerate(propositions)
            if _overlap(token.span, proposition.source_span)
            or any(
                argument.span and _overlap(token.span, argument.span)
                for argument in proposition.arguments
            )
        ]

    def enrich(
        self,
        graph: MeaningGraph,
        *,
        tokens: list[Token],
        original_text: str,
        conversation_context: list[str],
        known_entities: list[str],
    ) -> MeaningGraph:
        if not self.available:
            quality = {
                **graph.quality_annotations,
                "semantic_candidate_pack_used": False,
                "semantic_candidate_pack_record_count": 0,
                "semantic_candidate_pack_automatic_selection": False,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            return updated.model_copy(update={"semantic_hash": _stable_hash(updated)})

        context_text = "\n".join(
            [original_text, *conversation_context, *known_entities]
        )
        propositions = list(graph.propositions)
        matched_records: set[str] = set()
        exposed_senses = 0

        for token in tokens:
            records = self.lookup_token(token)
            if not records:
                continue
            related = self._related_indices(propositions, token)
            if not related:
                continue
            generated: list[SenseCandidate] = []
            for record in records:
                matched_records.add(record["record_id"])
                for candidate in record.get("meaning_candidates", []):
                    score, evidence = self._score(
                        record,
                        candidate,
                        token=token,
                        context_text=context_text,
                    )
                    generated.append(
                        SenseCandidate(
                            sense_id=candidate["candidate_id"],
                            label=(
                                candidate.get("label")
                                or next(
                                    iter(candidate.get("glosses") or []),
                                    candidate["candidate_id"],
                                )
                            ),
                            score=score,
                            evidence=evidence,
                        )
                    )
            generated.sort(key=lambda item: (-item.score, item.sense_id))
            for index in related:
                proposition = propositions[index]
                by_id = {
                    item.sense_id: item
                    for item in proposition.sense_candidates
                }
                for item in generated:
                    current = by_id.get(item.sense_id)
                    if current is None or item.score > current.score:
                        by_id[item.sense_id] = item
                candidates = sorted(
                    by_id.values(),
                    key=lambda item: (-item.score, item.sense_id),
                )[:32]
                exposed_senses += len(candidates)
                propositions[index] = proposition.model_copy(update={
                    "sense_candidates": candidates,
                    "inference_sources": list(dict.fromkeys([
                        *proposition.inference_sources,
                        "source-validated-semantic-candidate-pack",
                    ])),
                })

        quality = {
            **graph.quality_annotations,
            "semantic_candidate_pack_used": True,
            "semantic_candidate_pack_record_count": self.record_count,
            "semantic_candidate_pack_match_count": len(matched_records),
            "semantic_candidate_pack_sense_count": exposed_senses,
            "semantic_candidate_pack_automatic_selection": False,
            "semantic_candidate_pack_parameter_application": False,
            "semantic_candidate_pack_external_action": False,
        }
        updated = graph.model_copy(update={
            "propositions": propositions,
            "quality_annotations": quality,
        })
        updated = updated.model_copy(update={"semantic_hash": _stable_hash(updated)})
        self.last_metrics = {
            "semantic_candidate_pack_available": 1,
            "semantic_candidate_pack_record_count": self.record_count,
            "semantic_candidate_pack_match_count": len(matched_records),
            "semantic_candidate_pack_sense_count": exposed_senses,
        }
        return updated
