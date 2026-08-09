from __future__ import annotations

from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryFile
from threading import Lock
from typing import Any, BinaryIO, Iterable
import unicodedata

from .grammar_kernel import ACTION_INTENTS, CONSTRAINT_INTENTS
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
    return hashlib.sha256(
        graph.model_dump_json(exclude={"semantic_hash"}).encode("utf-8")
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
        self._record_store: BinaryIO | None = None
        self._record_offsets: dict[str, tuple[int, int]] = {}
        self._record_store_lock = Lock()
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
        runtime_required = {
            "surface": index_root / "runtime-surface-index.json.gz",
            "reading": index_root / "runtime-reading-index.json.gz",
            "locator": index_root / "runtime-record-locator.json.gz",
        }
        if "runtime_record_count" in manifest:
            runtime_missing = [
                str(path) for path in runtime_required.values() if not path.exists()
            ]
            if runtime_missing:
                raise FileNotFoundError(
                    "compiled semantic runtime indexes are incomplete: "
                    + ", ".join(runtime_missing)
                )
            selected_indexes = runtime_required
            expected_locator_count = int(manifest["runtime_record_count"])
        else:
            # Backward compatibility for compiler manifests created before
            # runtime-only lookup indexes were introduced.
            selected_indexes = required
            expected_locator_count = int(manifest.get("record_count", 0))

        self.manifest = manifest
        self.surface_index = _load_json_gzip(selected_indexes["surface"])
        self.reading_index = _load_json_gzip(selected_indexes["reading"])
        self.record_locator = _load_json_gzip(selected_indexes["locator"])
        if len(self.record_locator) != expected_locator_count:
            raise ValueError("semantic data record locator count mismatch")

        runtime_shards = {
            int(location["shard"])
            for location in self.record_locator.values()
        }
        if len(runtime_shards) > self.shard_cache_size:
            self._prepare_random_access_store()

        self.available = True
        self.last_metrics["semantic_pack_available"] = 1

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("record_count", 0))

    @property
    def runtime_record_count(self) -> int:
        return int(self.manifest.get("runtime_record_count", self.record_count))

    @staticmethod
    def _validated_record(
        item: dict[str, Any],
        *,
        path: Path,
        line_number: int,
        expected_record_id: str | None = None,
    ) -> dict[str, Any]:
        record_id = item.get("record_id")
        if not record_id:
            raise ValueError(f"semantic record_id missing: {path}:{line_number}")
        if expected_record_id is not None and record_id != expected_record_id:
            raise ValueError(
                "semantic record locator mismatch: "
                f"expected={expected_record_id} actual={record_id} "
                f"path={path}:{line_number}"
            )
        approval = item.get("approval") or {}
        approved_scopes = approval.get("approved_scopes") or []
        if not approved_scopes:
            raise ValueError(f"semantic record has no approved scope: {record_id}")
        blocked = approval.get("blockers_by_scope") or {}
        if any(blocked.get(scope) for scope in approved_scopes):
            raise ValueError(
                f"approved semantic record contains scoped blocker: {record_id}"
            )
        return item

    def _prepare_random_access_store(self) -> None:
        """Materialize runtime rows once to avoid repeated full-shard JSON parsing.

        The compiled locator already identifies the exact line for every runtime
        record. When runtime records span more shards than the bounded parsed
        shard cache can retain, repeatedly parsing 10k-record gzip shards causes
        deterministic cache thrashing. This store scans each required shard once
        as bytes, keeps only runtime rows in a temporary seekable file, and
        records byte offsets. Runtime semantics and approval validation remain
        unchanged; individual rows are JSON-decoded and validated on access.
        """

        line_map_by_shard: dict[int, dict[int, str]] = {}
        for record_id, location in self.record_locator.items():
            shard = int(location["shard"])
            line_number = int(location["line"])
            shard_lines = line_map_by_shard.setdefault(shard, {})
            if line_number in shard_lines:
                raise ValueError(
                    "semantic runtime locator line collision: "
                    f"shard={shard} line={line_number}"
                )
            shard_lines[line_number] = record_id

        store = TemporaryFile(mode="w+b")
        offsets: dict[str, tuple[int, int]] = {}
        offset = 0
        try:
            for shard, requested_lines in sorted(line_map_by_shard.items()):
                path = self.root / "records" / f"records-{shard:04d}.jsonl.gz"
                if not path.exists():
                    raise FileNotFoundError(path)
                with gzip.open(path, "rb") as handle:
                    for line_number, line in enumerate(handle, 1):
                        record_id = requested_lines.get(line_number)
                        if record_id is None:
                            continue
                        offsets[record_id] = (offset, len(line))
                        store.write(line)
                        offset += len(line)
            if len(offsets) != len(self.record_locator):
                missing = sorted(set(self.record_locator) - set(offsets))
                raise ValueError(
                    "semantic runtime locator could not materialize all records: "
                    f"missing={missing[:20]}"
                )
            store.flush()
        except Exception:
            store.close()
            raise

        self._record_store = store
        self._record_offsets = offsets

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
                item = self._validated_record(
                    json.loads(line),
                    path=path,
                    line_number=line_number,
                )
                records[item["record_id"]] = item
        self._shards[number] = records
        self._shards.move_to_end(number)
        while len(self._shards) > self.shard_cache_size:
            self._shards.popitem(last=False)
        return records

    def _record(self, record_id: str) -> dict[str, Any]:
        location = self.record_locator.get(record_id)
        if location is None:
            raise KeyError(record_id)

        if self._record_store is not None:
            span = self._record_offsets.get(record_id)
            if span is None:
                raise KeyError(record_id)
            offset, length = span
            with self._record_store_lock:
                self._record_store.seek(offset)
                payload = self._record_store.read(length)
            if len(payload) != length:
                raise ValueError(
                    f"semantic runtime record cache truncated: {record_id}"
                )
            path = (
                self.root
                / "records"
                / f"records-{int(location['shard']):04d}.jsonl.gz"
            )
            return self._validated_record(
                json.loads(payload),
                path=path,
                line_number=int(location["line"]),
                expected_record_id=record_id,
            )

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
        if token_pos and record_pos and any(
            part in record_pos for part in token_pos.split("-") if part
        ):
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
            (
                domain
                for domain in domains
                if domain and domain.casefold() in context_text.casefold()
            ),
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
    def _apply_parameters(
        proposition: Proposition,
        candidate: dict[str, Any],
    ) -> Proposition:
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
                update[key] = list(
                    dict.fromkeys([*getattr(proposition, key), *values])
                )
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
        update_hash: bool = True,
    ) -> MeaningGraph:
        if not self.available:
            quality = {
                **graph.quality_annotations,
                "semantic_data_pack_used": False,
                "semantic_data_pack_record_count": 0,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            if update_hash:
                return updated.model_copy(update={
                    "semantic_hash": _stable_hash(updated),
                })
            return updated

        if self.runtime_record_count == 0:
            quality = {
                **graph.quality_annotations,
                "semantic_data_pack_used": True,
                "semantic_data_pack_record_count": self.record_count,
                "semantic_data_runtime_record_count": 0,
                "semantic_data_pack_match_count": 0,
                "semantic_data_pack_resolved_count": 0,
                "semantic_data_pack_ambiguous_count": 0,
                "semantic_data_pack_automatic_external_action": False,
            }
            self.last_metrics = {
                "semantic_pack_available": 1,
                "semantic_pack_match_count": 0,
                "semantic_pack_resolved_count": 0,
                "semantic_pack_ambiguous_count": 0,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            if update_hash:
                return updated.model_copy(update={
                    "semantic_hash": _stable_hash(updated),
                })
            return updated

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
                or any(
                    argument.span and _overlap(token.span, argument.span)
                    for argument in proposition.arguments
                )
            ]
            ranked: list[
                tuple[int, str, dict[str, Any], dict[str, Any], list[str]]
            ] = []
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
                    ranked.append(
                        (score, candidate["candidate_id"], record, candidate, evidence)
                    )
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
                # The system semantic profile runs before the approved data pack
                # and may already have a stronger, context-specific resolution.
                # A later lexical/context pack can add coverage, but it must not
                # replace an already resolved sense with a weaker generic sense.
                if proposition.sense_id is not None:
                    continue
                if selected:
                    proposition = proposition.model_copy(update={
                        "sense_id": top[1],
                        "sense_label": top[3].get("label") or top[1],
                        "sense_confidence": min(
                            0.99,
                            0.70 + max(0, margin) / 100,
                        ),
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
                    # Grammar-derived action and constraint intents are already
                    # structural decisions. Ordinary lexical/semantic polysemy
                    # remains available as lexical evidence but must not turn a
                    # resolved structural proposition into an ambiguous one.
                    # Action/social-risk ambiguity still crosses this boundary
                    # and remains fail-closed for external execution.
                    structural_intent = (
                        proposition.intent_type in ACTION_INTENTS
                        or proposition.intent_type in CONSTRAINT_INTENTS
                    )
                    if structural_intent and not action_sensitive:
                        continue
                    proposition = proposition.model_copy(update={
                        "sense_id": None,
                        "sense_label": None,
                        "sense_confidence": 0.0,
                        "sense_candidates": sense_candidates,
                        "status": ItemStatus.AMBIGUOUS,
                        "executable_candidate": (
                            False
                            if action_sensitive
                            else proposition.executable_candidate
                        ),
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
                selected_candidate = (
                    top[3]
                    if selected and top[2]["record_id"] == record["record_id"]
                    else None
                )
                language_features.append(LanguageFeatureMatch(
                    entry_id=record["record_id"],
                    feature_type=record.get("feature_type") or "semantic_data",
                    surface=token.surface,
                    interpretation_id=(
                        selected_candidate.get("candidate_id")
                        if selected_candidate
                        else None
                    ),
                    interpretation=(
                        selected_candidate.get("label")
                        if selected_candidate
                        else None
                    ),
                    parameters=(selected_candidate or {}).get("parameters", {}),
                    register_profile=(selected_candidate or {}).get(
                        "register",
                        record.get("register", {}),
                    ),
                    source_span=token.span,
                    status=(
                        ItemStatus.RESOLVED
                        if selected_candidate
                        else ItemStatus.AMBIGUOUS
                    ),
                    candidate_ids=[
                        item[1]
                        for item in ranked
                        if item[2]["record_id"] == record["record_id"]
                    ],
                    evidence_ids=(selected_candidate or {}).get("evidence_ids", []),
                    risk_class=record.get("risk_class", "semantic"),
                ))

        quality = {
            **graph.quality_annotations,
            "semantic_data_pack_used": True,
            "semantic_data_pack_record_count": self.record_count,
            "semantic_data_runtime_record_count": self.runtime_record_count,
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
        if update_hash:
            updated = updated.model_copy(update={
                "semantic_hash": _stable_hash(updated),
            })
        self.last_metrics = {
            "semantic_pack_available": 1,
            "semantic_pack_match_count": match_count,
            "semantic_pack_resolved_count": resolved_count,
            "semantic_pack_ambiguous_count": ambiguous_count,
        }
        return updated
