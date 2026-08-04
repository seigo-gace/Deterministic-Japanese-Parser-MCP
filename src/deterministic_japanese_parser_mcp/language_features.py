from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .literal_index import LiteralIndex
from .models import (
    ItemStatus,
    LanguageFeatureMatch,
    MeaningGraph,
    Proposition,
    SocialContext,
    Token,
)
from .normalizer import span_to_original

_BOUNDARY = re.compile(r"[。！？!?\n]")


def _context_window(text: str, start: int, end: int) -> str:
    left = 0
    for match in _BOUNDARY.finditer(text, 0, start):
        left = match.end()
    right_match = _BOUNDARY.search(text, end)
    right = right_match.start() if right_match else len(text)
    return text[left:right]


def _sentence_final(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    return text[end] in "。！？!?…\n"


def _token_exact(
    tokens: list[Token],
    surface: str,
    start: int,
    end: int,
    mapping,
    original_text: str,
) -> bool:
    original_span = span_to_original(start, end, mapping, original_text)
    return any(
        token.span.start == original_span.start
        and token.span.end == original_span.end
        and (token.normalized == surface or token.surface == surface)
        for token in tokens
    )


def _token_sequence_exact(
    tokens: list[Token],
    surface: str,
    start: int,
    end: int,
    mapping,
    original_text: str,
) -> bool:
    original_span = span_to_original(start, end, mapping, original_text)
    selected = [
        token
        for token in tokens
        if token.span.start >= original_span.start
        and token.span.end <= original_span.end
    ]
    if not selected:
        return False
    selected.sort(key=lambda item: (item.span.start, item.span.end))
    if selected[0].span.start != original_span.start:
        return False
    if selected[-1].span.end != original_span.end:
        return False
    if any(
        left.span.end != right.span.start
        for left, right in zip(selected, selected[1:])
    ):
        return False
    surfaces = "".join(token.surface for token in selected)
    normalized = "".join(token.normalized for token in selected)
    return surface in {surfaces, normalized}


def _exact_utterance(text: str, start: int, end: int) -> bool:
    if text[:start].strip():
        return False
    trailing = text[end:].strip()
    return not trailing or not trailing.strip("。！？!?…")


def _matches_required_social(
    required: dict[str, Any],
    social: SocialContext,
) -> bool:
    if not required:
        return True
    value = social.model_dump(mode="json")
    for key, expected in required.items():
        if key == "speaker_group_equals_addressee_group":
            actual = bool(
                social.speaker_group
                and social.addressee_group
                and social.speaker_group == social.addressee_group
            )
        elif key == "speaker_group_differs_addressee_group":
            actual = bool(
                social.speaker_group
                and social.addressee_group
                and social.speaker_group != social.addressee_group
            )
        else:
            actual = value.get(key)
        if isinstance(expected, list):
            if isinstance(actual, list):
                if not set(expected).intersection(actual):
                    return False
            elif actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _interpretation_score(
    interpretation: dict[str, Any],
    window: str,
    social: SocialContext,
    discourse_state: dict[str, Any],
) -> int | None:
    required_all = interpretation.get("required_all", [])
    required_any = interpretation.get("required_any", [])
    forbidden_any = interpretation.get("forbidden_any", [])
    if any(value not in window for value in required_all):
        return None
    if required_any and not any(value in window for value in required_any):
        return None
    if any(value in window for value in forbidden_any):
        return None
    if not _matches_required_social(
        interpretation.get("required_social", {}), social
    ):
        return None
    required_discourse = interpretation.get("required_discourse", {})
    if any(
        discourse_state.get(key) != value
        for key, value in required_discourse.items()
    ):
        return None
    score = 1
    score += 20 * sum(value in window for value in required_all)
    score += 10 * sum(value in window for value in required_any)
    score += 5 * len(interpretation.get("required_social", {}))
    score += 5 * len(required_discourse)
    return score


def _merge_unique(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *[value for value in right if value]]))


class LanguageFeatureRuntime:
    """Read-only runtime for approved, precompiled language feature assets."""

    def __init__(self, compiled_path: Path):
        self.compiled_path = compiled_path
        if not compiled_path.exists():
            self.entries: dict[str, dict[str, Any]] = {}
            self.surface_map: dict[str, list[dict[str, str]]] = {}
            self.index = LiteralIndex(())
            self.asset_sha256 = ""
        else:
            payload = self._load_compiled_payload(compiled_path)
            if payload.get("schema_version") != "1.0.0":
                raise ValueError("unsupported compiled language feature schema")
            self.entries = {
                item["entry_id"]: item for item in payload.get("entries", [])
            }
            self.surface_map = {
                surface: list(values)
                for surface, values in payload.get("surface_map", {}).items()
            }
            self.index = LiteralIndex.from_compiled(payload["literal_index"])
            self.asset_sha256 = payload.get("content_sha256", "")
        self.last_metrics: dict[str, int | str] = {
            "entry_count": len(self.entries),
            "surface_count": len(self.surface_map),
            "candidate_count": 0,
            "match_count": 0,
            "asset_sha256": self.asset_sha256,
        }

    @staticmethod
    def _load_compiled_payload(compiled_path: Path) -> dict[str, Any]:
        """Load immutable base64 chunks and verify every digest before use."""
        if compiled_path.is_file():
            return json.loads(compiled_path.read_text(encoding="utf-8"))
        manifest_path = compiled_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "1.0.0":
            raise ValueError("unsupported language feature chunk manifest")
        if manifest.get("encoding") != "base64-json-utf8":
            raise ValueError("unsupported language feature chunk encoding")
        chunks: list[str] = []
        for part in manifest.get("parts", []):
            path = compiled_path / part["path"]
            content = path.read_text(encoding="ascii").strip()
            digest = hashlib.sha256(content.encode("ascii")).hexdigest()
            if digest != part.get("sha256"):
                raise ValueError(f"language feature chunk digest mismatch: {path}")
            if len(content) != part.get("characters"):
                raise ValueError(f"language feature chunk length mismatch: {path}")
            chunks.append(content)
        raw = base64.b64decode("".join(chunks), validate=True)
        if hashlib.sha256(raw).hexdigest() != manifest.get("compiled_sha256"):
            raise ValueError("compiled language feature payload digest mismatch")
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("content_sha256") != manifest.get(
            "payload_content_sha256"
        ):
            raise ValueError("language feature content digest mismatch")
        if payload.get("entry_count") != manifest.get("entry_count"):
            raise ValueError("language feature entry count mismatch")
        if payload.get("surface_count") != manifest.get("surface_count"):
            raise ValueError("language feature surface count mismatch")
        return payload

    def analyze(
        self,
        normalized_text: str,
        mapping,
        original_text: str,
        *,
        tokens: list[Token],
        social_context: SocialContext,
        discourse_state: dict[str, Any],
    ) -> list[LanguageFeatureMatch]:
        candidates: list[
            tuple[dict[str, Any], dict[str, str], str, int, int]
        ] = []
        for surface, start, end in self.index.find(normalized_text):
            for surface_ref in self.surface_map.get(surface, []):
                entry = self.entries[surface_ref["entry_id"]]
                mode = surface_ref.get("match_mode", "substring")
                if mode == "sentence_final" and not _sentence_final(
                    normalized_text, end
                ):
                    continue
                if mode == "exact" and not _exact_utterance(
                    normalized_text, start, end
                ):
                    continue
                if mode == "token" and not _token_exact(
                    tokens,
                    surface,
                    start,
                    end,
                    mapping,
                    original_text,
                ):
                    continue
                if (
                    entry.get("feature_type") == "sentence_final_particle"
                    and not _token_sequence_exact(
                        tokens,
                        surface,
                        start,
                        end,
                        mapping,
                        original_text,
                    )
                ):
                    continue
                candidates.append((entry, surface_ref, surface, start, end))

        # Sentence-final particles commonly overlap (for example よね / ね).
        # Keep the longest surface ending at the same position so the shorter
        # component does not become a second, false discourse interpretation.
        longest_final: dict[int, int] = {}
        for _, surface_ref, surface, _, end in candidates:
            if surface_ref.get("match_mode") == "sentence_final":
                longest_final[end] = max(longest_final.get(end, 0), len(surface))
        candidates = [
            item
            for item in candidates
            if item[1].get("match_mode") != "sentence_final"
            or len(item[2]) == longest_final.get(item[4], len(item[2]))
        ]

        output: list[LanguageFeatureMatch] = []
        seen: set[tuple[str, int, int]] = set()
        for entry, surface_ref, surface, start, end in sorted(
            candidates,
            key=lambda value: (
                value[3],
                -(value[4] - value[3]),
                value[0]["entry_id"],
            ),
        ):
            del surface_ref
            key = (entry["entry_id"], start, end)
            if key in seen:
                continue
            seen.add(key)
            window = _context_window(normalized_text, start, end)
            scored: list[tuple[int, dict[str, Any]]] = []
            for interpretation in entry.get("interpretations", []):
                score = _interpretation_score(
                    interpretation,
                    window,
                    social_context,
                    discourse_state,
                )
                if score is not None:
                    scored.append((score, interpretation))
            scored.sort(
                key=lambda item: (
                    -item[0],
                    item[1]["interpretation_id"],
                )
            )
            selected = None
            status = ItemStatus(entry.get("fallback_status", "AMBIGUOUS"))
            if scored:
                top_score = scored[0][0]
                top = [item for score, item in scored if score == top_score]
                if len(top) == 1:
                    selected = top[0]
                    status = ItemStatus.RESOLVED
                else:
                    status = ItemStatus.AMBIGUOUS
            original_span = span_to_original(start, end, mapping, original_text)
            output.append(LanguageFeatureMatch(
                entry_id=entry["entry_id"],
                feature_type=entry["feature_type"],
                surface=original_span.source_text or surface,
                interpretation_id=(
                    selected.get("interpretation_id") if selected else None
                ),
                interpretation=(selected.get("label") if selected else None),
                parameters=(selected.get("parameters", {}) if selected else {}),
                register_profile=entry.get("register", {}),
                source_span=original_span,
                status=status,
                candidate_ids=(
                    [item["interpretation_id"] for _, item in scored]
                    or [
                        item["interpretation_id"]
                        for item in entry.get("interpretations", [])
                    ]
                ),
                evidence_ids=[
                    item.get("evidence_id", "")
                    for item in entry.get("evidence", [])
                    if item.get("evidence_id")
                ],
                risk_class=entry.get("risk_class", "semantic"),
            ))
        self.last_metrics = {
            "entry_count": len(self.entries),
            "surface_count": len(self.surface_map),
            "candidate_count": len(candidates),
            "match_count": len(output),
            "asset_sha256": self.asset_sha256,
        }
        return output

    @staticmethod
    def apply_to_graph(
        graph: MeaningGraph,
        matches: list[LanguageFeatureMatch],
    ) -> MeaningGraph:
        if not matches:
            return graph
        clause_ids_by_match: dict[str, set[str]] = {}
        for match in matches:
            clause_ids_by_match[
                match.entry_id + ":" + str(match.source_span.start)
            ] = {
                clause.clause_id
                for clause in graph.clauses
                if match.source_span.start < clause.source_span.end
                and clause.source_span.start < match.source_span.end
            }
        propositions: list[Proposition] = []
        for proposition in graph.propositions:
            related = []
            for match in matches:
                if match.status != ItemStatus.RESOLVED:
                    continue
                direct = (
                    match.source_span.start < proposition.source_span.end
                    and proposition.source_span.start < match.source_span.end
                )
                clause_ids = clause_ids_by_match.get(
                    match.entry_id + ":" + str(match.source_span.start), set()
                )
                same_clause = bool(
                    proposition.clause_id
                    and proposition.clause_id in clause_ids
                )
                if direct or same_clause:
                    related.append(match)
            updates: dict[str, Any] = {}
            for match in related:
                params = match.parameters
                feature_type = match.feature_type
                if feature_type in {"onomatopoeia", "sensory_expression"}:
                    updates["sensory_features"] = {
                        **proposition.sensory_features,
                        **params,
                    }
                if feature_type in {"sociolect", "slang"}:
                    labels = [
                        *proposition.register_labels,
                        *match.register_profile.get("labels", []),
                    ]
                    formality = match.register_profile.get("formality")
                    if formality:
                        labels.append(formality)
                    updates["register_labels"] = _merge_unique([], labels)
                    if match.interpretation_id:
                        updates["sense_id"] = match.interpretation_id
                        updates["sense_label"] = match.interpretation
                        updates["sense_confidence"] = 1.0
                if feature_type == "modality":
                    if params.get("force_level") is not None:
                        updates["force_level"] = int(params["force_level"])
                    if params.get("directness"):
                        updates["directness"] = params["directness"]
                    if params.get("politeness_level") is not None:
                        updates["politeness_level"] = int(
                            params["politeness_level"]
                        )
                    if params.get("speech_act"):
                        updates["speech_act"] = params["speech_act"]
                    if params.get("deontic_force"):
                        updates["deontic_force"] = params["deontic_force"]
                if feature_type in {"honorific", "treatment_expression"}:
                    values = params.get("honorific_classes", [])
                    updates["honorific_classes"] = _merge_unique(
                        proposition.honorific_classes, values
                    )
                    if params.get("social_relation_status"):
                        updates["social_relation_status"] = params[
                            "social_relation_status"
                        ]
                if feature_type in {
                    "discourse_marker",
                    "backchannel",
                    "sentence_final_particle",
                    "information_territory",
                    "interaction_rule",
                }:
                    functions = params.get("interaction_functions", [])
                    updates["interaction_functions"] = _merge_unique(
                        proposition.interaction_functions, functions
                    )
                    updates["pragmatic_markers"] = _merge_unique(
                        proposition.pragmatic_markers,
                        [match.surface, *functions],
                    )
                    if params.get("information_territory"):
                        updates["information_territory"] = params[
                            "information_territory"
                        ]
            propositions.append(
                proposition.model_copy(update=updates)
                if updates
                else proposition
            )
        unresolved = list(graph.unresolved)
        for match in matches:
            if match.status != ItemStatus.RESOLVED:
                unresolved.append({
                    "type": "language_feature",
                    "entry_id": match.entry_id,
                    "feature_type": match.feature_type,
                    "candidate_ids": match.candidate_ids,
                    "status": match.status.value,
                    "source_span": match.source_span.model_dump(),
                })
        quality = dict(graph.quality_annotations)
        quality["language_features"] = {
            "matched": len(matches),
            "resolved": sum(
                item.status == ItemStatus.RESOLVED for item in matches
            ),
            "ambiguous": sum(
                item.status == ItemStatus.AMBIGUOUS for item in matches
            ),
            "feature_types": sorted({item.feature_type for item in matches}),
        }
        updated = graph.model_copy(update={
            "propositions": propositions,
            "language_features": matches,
            "unresolved": unresolved,
            "quality_annotations": quality,
        })
        payload = updated.model_dump(mode="json")
        payload["semantic_hash"] = ""
        digest = hashlib.sha256(json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        return updated.model_copy(update={"semantic_hash": digest})
