"""Common normalization and adapter logic for unified semantic data."""
from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Iterator
import unicodedata

import yaml

SCHEMA_VERSION = "2.0.0"
COMPILER_VERSION = "2.0.0"
ALLOWED_REVIEW_STATUS = {"approved", "needs-evidence", "rejected", "hold"}
APPROVAL_SCOPES = ("lexical", "semantic", "pragmatic", "task", "external_action")
ALLOWED_POLARITIES = {"positive", "negative", "neutral"}
UNKNOWN_LICENSE_MARKERS = ("unknown", "unlicensed", "private", "pending", "tbd", "確認中")
SEMANTIC_TARGETS = {
    "lexicon",
    "language_feature",
    "metaphor",
    "metonymy",
    "synonym",
    "intent_rule",
    "task_template",
    "gold_case",
}

try:
    from sudachipy import dictionary, tokenizer as sudachi_tokenizer
except ImportError:  # pragma: no cover
    dictionary = None
    sudachi_tokenizer = None


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value)).casefold()


def _open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with _open_text(path) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record must be an object: {path}:{line_number}")
            value["_source_path"] = str(path)
            value["_source_line"] = line_number
            yield value


def _iter_yaml_or_json(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value is None:
        return
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        values = value["records"]
    elif isinstance(value, dict) and isinstance(value.get("entries"), list):
        values = value["entries"]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    for index, item in enumerate(values, 1):
        if not isinstance(item, dict):
            raise ValueError(f"pack record must be an object: {path}:{index}")
        item = dict(item)
        item["_source_path"] = str(path)
        item["_source_line"] = index
        yield item


@dataclass
class Morphology:
    lemma: str
    readings: list[str]
    part_of_speech: list[str]
    forms: list[dict[str, Any]]


class MorphologyAnalyzer:
    def __init__(self) -> None:
        self.backend = "fallback"
        self._tokenizer = None
        self._mode = None
        if dictionary is not None:
            self._tokenizer = dictionary.Dictionary(dict="core").create()
            self._mode = sudachi_tokenizer.Tokenizer.SplitMode.C
            self.backend = "sudachi-core"

    def analyze(self, surface: str) -> Morphology:
        surface = normalize_text(surface)
        if not surface:
            return Morphology("", [], [], [])
        if self._tokenizer is None:
            return Morphology(surface, [], [], [{"surface": surface, "lemma": surface}])
        morphemes = list(self._tokenizer.tokenize(surface, self._mode))
        forms: list[dict[str, Any]] = []
        readings: list[str] = []
        pos: list[str] = []
        lemmas: list[str] = []
        for morpheme in morphemes:
            reading = normalize_text(morpheme.reading_form())
            lemma = normalize_text(morpheme.dictionary_form() or morpheme.normalized_form())
            part = ":".join(value for value in morpheme.part_of_speech() if value != "*")
            forms.append({
                "surface": normalize_text(morpheme.surface()),
                "normalized": normalize_text(morpheme.normalized_form()),
                "lemma": lemma,
                "reading": reading,
                "part_of_speech": part,
            })
            if reading:
                readings.append(reading)
            if part:
                pos.append(part)
            if lemma:
                lemmas.append(lemma)
        lemma = lemmas[0] if len(lemmas) == 1 else surface
        return Morphology(lemma, _stable_unique(readings), _stable_unique(pos), forms)


def _source_object(raw: dict[str, Any], dataset_default: str) -> dict[str, Any]:
    source = raw.get("source") or {}
    provenance = raw.get("provenance") or {}
    source_refs = _as_list(raw.get("source_refs"))
    if isinstance(source, list):
        source_refs = [*source_refs, *source]
        source = {}
    if not isinstance(source, dict):
        source = {"source_url": source}
    source_path = Path(str(raw.get("_source_path") or ""))
    source_digest = normalize_text(
        source.get("source_sha256") or provenance.get("source_sha256")
    )
    if not source_digest and source_path.is_file():
        source_digest = _sha256_file(source_path)
    source_url = normalize_text(source.get("source_url") or raw.get("source_url"))
    if not source_url:
        source_url = next(
            (
                normalize_text(value)
                for value in source_refs
                if normalize_text(value).startswith(("https://", "http://"))
            ),
            "",
        )
    license_value = normalize_text(
        raw.get("license") or source.get("license") or provenance.get("license")
    )
    return {
        "dataset": normalize_text(source.get("dataset") or provenance.get("origin") or dataset_default),
        "version": normalize_text(
            source.get("version")
            or raw.get("source_version")
            or provenance.get("version")
        ),
        "license": license_value,
        "source_id": normalize_text(source.get("source_id") or provenance.get("source_id") or raw.get("entry_id") or raw.get("record_id")),
        "source_url": source_url,
        "source_sha256": source_digest,
        "evidence_scope": normalize_text(source.get("evidence_scope") or provenance.get("evidence_scope") or "runtime_data"),
        "attribution": normalize_text(source.get("attribution") or provenance.get("attribution")),
    }


def _meaning_candidates(raw: dict[str, Any], record_id: str, lemma: str, pos: list[str], domains: list[str]) -> tuple[list[dict[str, Any]], bool]:
    source_values: list[Any] = []
    for key in ("meaning_candidates", "senses", "interpretations", "meanings"):
        source_values.extend(_as_list(raw.get(key)))
    candidates: list[dict[str, Any]] = []
    for index, value in enumerate(source_values, 1):
        if isinstance(value, str):
            label = normalize_text(value)
            item = {"label": label, "glosses": [label] if label else []}
        elif isinstance(value, dict):
            item = dict(value)
            label = normalize_text(
                item.get("label") or item.get("interpretation") or item.get("gloss") or item.get("meaning")
            )
            glosses = _stable_unique([
                *[normalize_text(x) for x in _as_list(item.get("glosses"))],
                *[normalize_text(x) for x in _as_list(item.get("definitions"))],
                normalize_text(item.get("gloss")),
                normalize_text(item.get("meaning")),
            ])
            item["label"] = label or (glosses[0] if glosses else lemma)
            item["glosses"] = glosses
        else:
            continue
        item["candidate_id"] = normalize_text(item.get("candidate_id") or item.get("sense_id") or f"{record_id}:sense:{index:03d}")
        item["part_of_speech"] = _stable_unique([*pos, *_as_list(item.get("part_of_speech"))])
        item["domains"] = _stable_unique([*domains, *_as_list(item.get("domains"))])
        item["polarity"] = normalize_text(item.get("polarity") or "unspecified")
        item["intensity"] = item.get("intensity")
        item["parameters"] = item.get("parameters") or {}
        item["register"] = item.get("register") or {}
        item["context"] = item.get("context") or {}
        item["evidence_ids"] = _stable_unique(_as_list(item.get("evidence_ids")))
        item["review_status"] = normalize_text(item.get("review_status") or raw.get("review_status") or "needs-evidence")
        candidates.append(item)
    candidates.sort(key=lambda item: item["candidate_id"])
    if candidates:
        return candidates, True
    return ([{
        "candidate_id": f"{record_id}:sense:unresolved",
        "label": lemma,
        "glosses": [],
        "part_of_speech": pos,
        "domains": domains,
        "polarity": "unspecified",
        "intensity": None,
        "parameters": {},
        "register": {},
        "context": {},
        "evidence_ids": [],
        "review_status": "needs-evidence",
    }], False)


def _semantic_targets(raw: dict[str, Any], source_kind: str) -> list[str]:
    explicit = _stable_unique(_as_list(raw.get("semantic_targets") or raw.get("targets")))
    if explicit:
        unknown = sorted(set(explicit) - SEMANTIC_TARGETS)
        if unknown:
            raise ValueError(f"unknown semantic_targets: {unknown}")
        return explicit
    feature_type = normalize_text(raw.get("feature_type") or raw.get("category"))
    targets = ["lexicon"]
    if source_kind == "context" or feature_type:
        targets.append("language_feature")
    if feature_type in {"metaphor", "metonymy"}:
        targets.append(feature_type)
    return sorted(set(targets))


def _build_record(raw: dict[str, Any], *, source_kind: str, analyzer: MorphologyAnalyzer) -> dict[str, Any]:
    record_id = normalize_text(raw.get("record_id") or raw.get("entry_id") or raw.get("id"))
    surface_values = [
        normalize_text(raw.get("surface")),
        normalize_text(raw.get("lemma")),
        *[normalize_text(value) for value in _as_list(raw.get("surfaces"))],
        *[normalize_text(value) for value in _as_list(raw.get("variants"))],
        *[normalize_text(value) for value in _as_list(raw.get("forms")) if isinstance(value, str)],
    ]
    surfaces = _stable_unique(surface_values)
    if not record_id or not surfaces:
        location = f"{raw.get('_source_path')}:{raw.get('_source_line')}"
        raise ValueError(f"record id and surface are required: {location}")
    has_reading = bool(_as_list(raw.get("readings")) or _as_list(raw.get("reading_mappings")))
    has_pos = bool(_as_list(raw.get("part_of_speech") or raw.get("pos")))
    has_lemma = bool(normalize_text(raw.get("lemma") or raw.get("normalized_form")))
    morphology = (
        Morphology(normalize_text(raw.get("lemma") or raw.get("normalized_form") or surfaces[0]), [], [], [])
        if has_reading and has_pos and has_lemma
        else analyzer.analyze(surfaces[0])
    )
    lemma = normalize_text(raw.get("lemma") or raw.get("normalized_form") or morphology.lemma or surfaces[0])
    readings = _stable_unique([
        *[normalize_text(value) for value in _as_list(raw.get("readings"))],
        *[normalize_text(value.get("reading")) for value in _as_list(raw.get("reading_mappings")) if isinstance(value, dict)],
        *morphology.readings,
    ])
    part_of_speech = _stable_unique([
        *[normalize_text(value) for value in _as_list(raw.get("part_of_speech") or raw.get("pos"))],
        normalize_text(raw.get("source_pos")),
        *morphology.part_of_speech,
    ])
    domains = _stable_unique([
        *[normalize_text(value) for value in _as_list(raw.get("domains"))],
        normalize_text(raw.get("domain")),
        normalize_text(raw.get("category")) if source_kind == "domain_pack" else "",
    ])
    usage_labels = _stable_unique([
        *[normalize_text(value) for value in _as_list(raw.get("usage_labels"))],
        *[normalize_text(value) for value in _as_list((raw.get("provenance") or {}).get("source_tags"))],
    ])
    source = _source_object(raw, {"open_lexicon": "open-lexicon", "context": "context-v3"}.get(source_kind, source_kind))
    meaning_candidates, semantic_content_present = _meaning_candidates(raw, record_id, lemma, part_of_speech, domains)
    polarity = normalize_text(raw.get("polarity") or "unspecified")
    intensity = raw.get("intensity", raw.get("strength"))
    if polarity != "unspecified" and polarity not in ALLOWED_POLARITIES:
        raise ValueError(f"invalid polarity for {record_id}: {polarity}")
    if intensity is not None and (
        isinstance(intensity, bool)
        or not isinstance(intensity, (int, float))
        or not 0.0 <= float(intensity) <= 1.0
    ):
        raise ValueError(f"invalid intensity for {record_id}: {intensity}")
    review_status = normalize_text(raw.get("review_status") or "needs-evidence")
    if review_status not in ALLOWED_REVIEW_STATUS:
        review_status = "needs-evidence"
    blockers_by_scope: dict[str, list[str]] = {
        scope: [] for scope in APPROVAL_SCOPES
    }
    if not readings:
        blockers_by_scope["lexical"].append("reading-required")
    if not part_of_speech:
        blockers_by_scope["lexical"].append("part-of-speech-required")
    if not semantic_content_present:
        blockers_by_scope["semantic"].append("meaning-candidate-required")
    if polarity == "unspecified":
        blockers_by_scope["semantic"].append("polarity-required")
    if intensity is None:
        blockers_by_scope["semantic"].append("intensity-required")
    raw_context = raw.get("context_conditions")
    if raw.get("_force_judgment_review") or not isinstance(raw_context, dict):
        blockers_by_scope["pragmatic"].append("context-review-required")
    if not isinstance(raw_context, dict):
        raw_context = {}
    if "task_candidates" not in raw:
        blockers_by_scope["task"].append("task-review-required")
    if not isinstance(raw.get("external_action_risk"), bool):
        blockers_by_scope["external_action"].append(
            "external-action-risk-review-required"
        )
    license_folded = source["license"].casefold()
    if not source["license"] or any(marker in license_folded for marker in UNKNOWN_LICENSE_MARKERS):
        blockers_by_scope["lexical"].append("license-required")
    if not source["dataset"]:
        blockers_by_scope["lexical"].append("source-dataset-required")
    if not source["version"]:
        blockers_by_scope["lexical"].append("source-version-required")
    if not source["source_sha256"]:
        blockers_by_scope["lexical"].append("source-digest-required")
    elif not re.fullmatch(r"[0-9a-fA-F]{64}", source["source_sha256"]):
        blockers_by_scope["lexical"].append("source-digest-invalid")
    examples = {
        "positive": _as_list(raw.get("positive_examples")),
        "negative": _as_list(raw.get("negative_examples")),
        "boundary": _as_list(raw.get("boundary_examples")),
    }
    if "language_feature" in _semantic_targets(raw, source_kind):
        for name, values in examples.items():
            if not values:
                blockers_by_scope["pragmatic"].append(f"{name}-example-required")

    explicit_scopes = raw.get("approval_scopes") or {}
    if not isinstance(explicit_scopes, dict):
        explicit_scopes = {}
    lexical_status = normalize_text(explicit_scopes.get("lexical") or review_status)
    if lexical_status not in ALLOWED_REVIEW_STATUS:
        lexical_status = "needs-evidence"
    scope_status: dict[str, str] = {
        "lexical": lexical_status,
        "semantic": normalize_text(
            explicit_scopes.get("semantic") or "needs-evidence"
        ),
        "pragmatic": normalize_text(
            explicit_scopes.get("pragmatic") or "needs-evidence"
        ),
        "task": normalize_text(
            explicit_scopes.get("task") or "needs-evidence"
        ),
        "external_action": normalize_text(
            explicit_scopes.get("external_action") or "needs-evidence"
        ),
    }
    for scope, status in list(scope_status.items()):
        if status not in {*ALLOWED_REVIEW_STATUS, "not-applicable"}:
            scope_status[scope] = "needs-evidence"
    approved_scopes = sorted(
        scope
        for scope, status in scope_status.items()
        if status == "approved" and not blockers_by_scope[scope]
    )
    review_scopes = sorted(
        scope
        for scope, status in scope_status.items()
        if status not in {"approved", "not-applicable", "rejected"}
        or bool(blockers_by_scope[scope])
    )
    blockers = sorted(
        {item for values in blockers_by_scope.values() for item in values}
    )
    runtime_eligible = "lexical" in approved_scopes
    input_value = {
        key: value for key, value in raw.items() if not key.startswith("_source_")
    }
    input_digest = _sha256_bytes(_json_line(input_value).encode("utf-8"))
    if source_kind == "domain_pack":
        pack_namespace = "domains"
    elif source_kind == "user_pack":
        pack_namespace = "user"
    else:
        pack_namespace = "core"
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "source_kind": source_kind,
        "pack_namespace": pack_namespace,
        "lemma": lemma,
        "surfaces": surfaces,
        "normalized_surfaces": _stable_unique(normalize_key(value) for value in surfaces),
        "readings": readings,
        "reading_mappings": _as_list(raw.get("reading_mappings")),
        "part_of_speech": part_of_speech,
        "morphology": {
            "backend": analyzer.backend,
            "forms": morphology.forms,
            "conjugation": raw.get("conjugation") or {},
        },
        "domains": domains,
        "usage_labels": usage_labels,
        "feature_type": normalize_text(raw.get("feature_type") or raw.get("category")),
        "meaning_candidates": meaning_candidates,
        "polarity": polarity,
        "intensity": float(intensity) if intensity is not None else None,
        "semantic_targets": _semantic_targets(raw, source_kind),
        "parameters": raw.get("parameters") or {},
        "register": raw.get("register") or {},
        "context_conditions": {
            "required_any": _as_list(
                raw_context.get("required_any", raw.get("required_any"))
            ),
            "required_all": _as_list(
                raw_context.get("required_all", raw.get("required_all"))
            ),
            "forbidden_any": _as_list(
                raw_context.get("forbidden_any", raw.get("forbidden_any"))
            ),
            "required_social": _as_list(
                raw_context.get("required_social", raw.get("required_social"))
            ),
            "required_discourse": _as_list(
                raw_context.get(
                    "required_discourse", raw.get("required_discourse")
                )
            ),
        },
        "task_candidates": _as_list(raw.get("task_candidates")),
        "examples": examples,
        "risk_class": normalize_text(raw.get("risk_class") or ("action" if raw.get("external_action_risk") else "semantic")),
        "external_action_risk": (
            bool(raw.get("external_action_risk"))
            if isinstance(raw.get("external_action_risk"), bool)
            else None
        ),
        "source": source,
        "review_status": review_status,
        "approval": {
            "scopes": scope_status,
            "approved_scopes": approved_scopes,
            "review_scopes": review_scopes,
            "blockers_by_scope": {
                scope: sorted(set(values))
                for scope, values in blockers_by_scope.items()
            },
        },
        "review_blockers": sorted(set(blockers)),
        "runtime_eligible": runtime_eligible,
        "input_sha256": input_digest,
        "original_location": {
            "path": normalize_text(raw.get("_source_path")),
            "line": raw.get("_source_line"),
        },
    }
