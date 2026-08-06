from __future__ import annotations

from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

from .models import (
    ItemStatus,
    LanguageFeatureMatch,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    SenseCandidate,
    Token,
)


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


def _contains_all(text: str, values: Iterable[str]) -> bool:
    folded = text.casefold()
    return all(str(value).casefold() in folded for value in values if str(value))


def _contains_any(text: str, values: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(str(value).casefold() in folded for value in values if str(value))


class SemanticDataRuntime:
    """Approved-only runtime for unified lexical and context data packs.

    This runtime applies reviewed meaning candidates to MeaningGraph
    propositions. It preserves ambiguity and never creates external actions.
    """

    def __init__(self, root: Path, *, shard_cache_size: int = 4):
        self.root = Path(root)
        self.available = False
        self.manifest: dict[str, Any] = {}
        self.surface_index: dict[str, list[str]] = {}
        self.reading_index: dict[str, list[str]] = {}
        self.record_locator: dict[str, dict[str, int]] = {}
        self.shard_cache_size = max(1, shard_cache_size)
        self._shards: OrderedDict[int, dict[str, dict[str, Any]]] = OrderedDict()
        self.last_metrics: dict[str, int | float | str] = {
            "semantic_pack_available": 0,
            "semantic_pack_match_count": 0,
            "semantic_pack_resolved_count": 0,
            "semantic_pack_ambiguous_count": 0,
        }

        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("approved_only") is not True:
            raise ValueError("semantic data pack must be approved-only")
        if manifest.get("automatic_external_action") is not False:
            raise ValueError("semantic data pack external-action boundary is invalid")
        if manifest.get("preserve_ambiguity") is not True:
            raise ValueError("semantic data pack must preserve ambiguity")
        index_root = self.root / "indexes"
        required = {
            "surface": index_root / "surface-index.json.gz",
            "reading": index_root / "reading-index.json.gz",
            "locator": index_root / "record-locator.json.gz",
        }
        missing = [str(path) for path in required.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "compiled semantic data indexes are incomplete: " + ", ".join(missing)
            )
        self.manifest = manifest
        self.surface_index = _load_json_gzip(required["surface"])
        self.reading_index = _load_json_gzip(required["reading"])
        self.record_locator = _load_json_gzip(required["locator"])
        if len(self.record_locator) != int(manifest.get("record_count", 0)):
            raise ValueError("semantic data record locator count mismatch")
        self.available = True
        self.last_metrics["semantic_pack_available"] = 1

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
                    raise ValueError(f"semantic record_id missing: {path}:{line_number}")
                approval = item.get("approval") or {}
                approved_scopes = approval.get("approved_scopes") or []
                if not approved_scopes:
                    raise ValueError(
                        f"semantic record has no approved scope: {record_id}"
                    )
                blocked = approval.get("blockers_by_scope") or {}
                if any(blocked.get(scope) for scope in approved_scopes):
                    raise ValueError(
                        f"approved semantic record contains scoped blocker: {record_id}"
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
        item = self._load_shard(int(location["shard"])).get(record_id)
        if item is None:
            raise KeyError(record_id)
        return item

    def lookup_token(self, token: Token, *, max_candidates: int = 32) -> list[dict[str, Any]]:
        if not self.available:
            return []
        keys = [_normalize(token.surface), _normalize(token.normalized)]
        record_ids: list[str] = []
        for key in keys:
            for record_id in self.surface_index.get(key, []):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        if not record_ids and token.reading:
            for record_id in self.reading_index.get(_normalize(token.reading), []):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        return [self._record(record_id) for record_id in record_ids[:max_candidates]]

    @staticmethod
    def _context_score(
        record: dict[str, Any],
        candidate: dict[str, Any],
        *,
        token: Token,
        context_text: str,
    ) -> tuple[int, list[str]]:
        score = 100
        evidence = ["semantic_pack_surface_match"]
        record_pos = " ".join(record.get("part_of_speech", [])).casefold()
        token_pos = " ".join(token.pos).casefold()
        if token_pos and record_pos and any(part in record_pos for part in token_pos.split("-") if part):
            score += 20
            evidence.append("semantic_pack_pos_match")

        conditions = dict(record.get("context_conditions") or {})
        candidate_context = candidate.get("context") or {}
        for key in ("required_any", "required_all", "forbidden_any"):
            if key in candidate_context:
                conditions[key] = [
                    *conditions.get(key, []),
                    *candidate_context.get(key, []),
                ]
        required_all = conditions.get("required_all", [])
        required_any = conditions.get("required_any", [])
        forbidden_any = conditions.get("forbidden_any", [])
        if required_all:
            if not _contains_all(context_text, required_all):
                return -10000, ["semantic_pack_required_all_missing"]
            score += 40
            evidence.append("semantic_pack_required_all")
        if required_any:
            if not _contains_any(context_text, required_any):
                return -10000, ["semantic_pack_required_any_missing"]
            score += 25
            evidence.append("semantic_pack_required_any")
        if forbidden_any and _contains_any(context_text, forbidden_any):
            return -10000, ["semantic_pack_forbidden_context"]

        domains = [*record.get("domains", []), *candidate.get("domains", [])]
        matched_domain = next(
            (domain for domain in domains if domain and domain.casefold() in context_text.casefold()),
            None,
        )
        if matched_domain:
            score += 10
            evidence.append(f"semantic_pack_domain:{matched_domain}")
        if candidate.get("evidence_ids"):
            score += 1
            evidence.append("semantic_pack_evidence_complete")
        return score, evidence

    @staticmethod
    def _apply_parameters(proposition: Proposition, candidate: dict[str, Any]) -> Proposition:
        parameters = dict(candidate.get("parameters") or {})
        allowed_scalar = {
            "force_level",
            "directness",
            "politeness_level",
            "speech_act",
            "epistemic_status",
            "information_territory",
        }
        update: dict[str, Any] = {}
        for key in allowed_scalar:
            if key in parameters and parameters[key] is not None:
                update[key] = parameters[key]
        polarity = candidate.get("polarity")
        if polarity in {"positive", "negative"}:
            update["polarity"] = polarity
        list_fields = {
            "register_labels",
            "honorific_classes",
            "interaction_functions",
            "pragmatic_markers",
        }
        for key in list_fields:
            values = parameters.get(key)
            if values:
                update[key] = list(dict.fromkeys([*getattr(proposition, key), *values]))
        if parameters.get("sensory_features"):
            update["sensory_features"] = {
                **proposition.sensory_features,
                **parameters["sensory_features"],
            }
        return proposition.model_copy(update=update) if update else proposition

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
                "semantic_data_pack_used": False,
                "semantic_data_pack_record_count": 0,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            return updated.model_copy(update={"semantic_hash": _stable_hash(updated)})

        context_text = "\n".join([original_text, *conversation_context, *known_entities])
        propositions = list(graph.propositions)
        language_features = list(graph.language_features)
        unresolved = list(graph.unresolved)
        match_count = 0
        resolved_count = 0
        ambiguous_count = 0

        for token in tokens:
            records = self.lookup_token(token)
            if not records:
                continue
            related_indices = [
                index
                for index, proposition in enumerate(propositions)
                if _overlap(token.span, proposition.source_span)
                or any(argument.span and _overlap(token.span, argument.span) for argument in proposition.arguments)
            ]
            ranked: list[tuple[int, str, dict[str, Any], dict[str, Any], list[str]]] = []
            for record in records:
                for candidate in record.get("meaning_candidates", []):
                    if candidate.get("review_status") != "approved":
                        continue
                    score, evidence = self._context_score(
                        record,
                        candidate,
                        token=token,
                        context_text=context_text,
                    )
                    if score <= -10000:
                        continue
                    ranked.append((score, candidate["candidate_id"], record, candidate, evidence))
            if not ranked:
                continue
            ranked.sort(key=lambda item: (-item[0], item[1], item[2]["record_id"]))
            match_count += 1
            sense_candidates = [
                SenseCandidate(
                    sense_id=item[1],
                    label=item[3].get("label") or item[1],
                    score=item[0],
                    evidence=item[4],
                )
                for item in ranked
            ]
            top = ranked[0]
            margin = top[0] - ranked[1][0] if len(ranked) > 1 else top[0]
            selected = len(ranked) == 1 or margin >= 20
            if selected:
                resolved_count += 1
            else:
                ambiguous_count += 1

            for index in related_indices:
                proposition = propositions[index]
                if selected:
                    proposition = proposition.model_copy(update={
                        "sense_id": top[1],
                        "sense_label": top[3].get("label") or top[1],
                        "sense_confidence": min(0.99, 0.70 + max(0, margin) / 100),
                        "sense_candidates": sense_candidates,
                        "evidence_ids": list(dict.fromkeys([
                            *proposition.evidence_ids,
                            *top[3].get("evidence_ids", []),
                            f"semantic-pack:{top[2]['record_id']}",
                        ])),
                        "inference_sources": list(dict.fromkeys([
                            *proposition.inference_sources,
                            "approved-semantic-data-pack",
                        ])),
                    })
                    proposition = self._apply_parameters(proposition, top[3])
                else:
                    action_sensitive = any(
                        item[2].get("risk_class") in {"action", "social"}
                        for item in ranked
                    )
                    proposition = proposition.model_copy(update={
                        "sense_id": None,
                        "sense_label": None,
                        "sense_confidence": 0.0,
                        "sense_candidates": sense_candidates,
                        "status": ItemStatus.AMBIGUOUS,
                        "executable_candidate": False if action_sensitive else proposition.executable_candidate,
                    })
                    unresolved.append({
                        "type": "semantic_data_pack",
                        "surface": token.surface,
                        "candidate_ids": [item[1] for item in ranked],
                        "status": ItemStatus.AMBIGUOUS.value,
                        "action_sensitive": action_sensitive,
                    })
                propositions[index] = proposition

            for record in records:
                if "language_feature" not in record.get("semantic_targets", []):
                    continue
                selected_candidate = top[3] if selected and top[2]["record_id"] == record["record_id"] else None
                language_features.append(LanguageFeatureMatch(
                    entry_id=record["record_id"],
                    feature_type=record.get("feature_type") or "semantic_data",
                    surface=token.surface,
                    interpretation_id=selected_candidate.get("candidate_id") if selected_candidate else None,
                    interpretation=selected_candidate.get("label") if selected_candidate else None,
                    parameters=(selected_candidate or {}).get("parameters", {}),
                    register_profile=(selected_candidate or {}).get("register", record.get("register", {})),
                    source_span=token.span,
                    status=ItemStatus.RESOLVED if selected_candidate else ItemStatus.AMBIGUOUS,
                    candidate_ids=[item[1] for item in ranked if item[2]["record_id"] == record["record_id"]],
                    evidence_ids=(selected_candidate or {}).get("evidence_ids", []),
                    risk_class=record.get("risk_class", "semantic"),
                ))

        quality = {
            **graph.quality_annotations,
            "semantic_data_pack_used": True,
            "semantic_data_pack_record_count": self.record_count,
            "semantic_data_pack_match_count": match_count,
            "semantic_data_pack_resolved_count": resolved_count,
            "semantic_data_pack_ambiguous_count": ambiguous_count,
            "semantic_data_pack_automatic_external_action": False,
        }
        updated = graph.model_copy(update={
            "propositions": propositions,
            "language_features": language_features,
            "unresolved": unresolved,
            "quality_annotations": quality,
        })
        updated = updated.model_copy(update={"semantic_hash": _stable_hash(updated)})
        self.last_metrics = {
            "semantic_pack_available": 1,
            "semantic_pack_match_count": match_count,
            "semantic_pack_resolved_count": resolved_count,
            "semantic_pack_ambiguous_count": ambiguous_count,
        }
        return updated
