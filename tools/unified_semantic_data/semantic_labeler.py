"""Deterministic build-time semantic meaning enrichment and completeness gate.

This module never calls an LLM and never approves semantic meaning automatically.
It detects records whose meaning candidates are empty or placeholder-only, proposes
candidate meanings from already-approved records and local reference packs, and
writes a semantic-review queue. Final promotion still requires Decision Ledger
approval.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import unicodedata
from typing import Any, Iterable, Iterator

PLACEHOLDER_GLOSSES = frozenset(
    {
        "意味・機能はevidence確認待ち",
        "meaning candidate from wiktionary-derived data; review required",
        "pending review",
        "meaning pending review",
        "unknown meaning",
        "tbd",
    }
)


def normalize_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _stable_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_number}")
            yield value


def _json_line(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_glosses(candidate: dict[str, Any]) -> list[str]:
    values = [
        *_as_list(candidate.get("glosses")),
        *_as_list(candidate.get("definitions")),
        candidate.get("gloss"),
        candidate.get("meaning"),
    ]
    return _stable_unique(str(value or "").strip() for value in values)


def candidate_has_real_meaning(candidate: dict[str, Any]) -> bool:
    for gloss in _candidate_glosses(candidate):
        if normalize_key(gloss) not in PLACEHOLDER_GLOSSES:
            return True
    return False


def record_has_real_meaning(record: dict[str, Any]) -> bool:
    return any(
        candidate_has_real_meaning(candidate)
        for candidate in _as_list(record.get("meaning_candidates"))
        if isinstance(candidate, dict)
    )


def _semantic_status(record: dict[str, Any]) -> str:
    return str(
        ((record.get("approval") or {}).get("scopes") or {}).get(
            "semantic", "needs-evidence"
        )
    )


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    glosses = _candidate_glosses(candidate)
    label = str(candidate.get("label") or (glosses[0] if glosses else "")).strip()
    return {
        "label": label,
        "glosses": glosses,
        "part_of_speech": _stable_unique(
            str(value or "").strip()
            for value in _as_list(candidate.get("part_of_speech"))
        ),
        "domains": _stable_unique(
            str(value or "").strip()
            for value in _as_list(candidate.get("domains"))
        ),
        "polarity": str(candidate.get("polarity") or "unspecified"),
        "intensity": candidate.get("intensity"),
        "parameters": candidate.get("parameters") or {},
        "register": candidate.get("register") or {},
        "context": candidate.get("context") or {},
    }


def _record_reference(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record.get("record_id"),
        "surfaces": _stable_unique(record.get("normalized_surfaces") or record.get("surfaces") or []),
        "readings": _stable_unique(normalize_key(v) for v in _as_list(record.get("readings"))),
        "part_of_speech": _stable_unique(normalize_key(v) for v in _as_list(record.get("part_of_speech"))),
        "domains": _stable_unique(normalize_key(v) for v in _as_list(record.get("domains"))),
        "candidates": [
            _compact_candidate(candidate)
            for candidate in _as_list(record.get("meaning_candidates"))
            if isinstance(candidate, dict) and candidate_has_real_meaning(candidate)
        ],
        "source": record.get("source") or {},
    }


def _load_external_reference(path: Path) -> Iterator[dict[str, Any]]:
    for item in _iter_jsonl(path):
        nested_source = item.get("source") if isinstance(item.get("source"), dict) else {}
        surfaces = _stable_unique(
            [
                str(item.get("surface") or "").strip(),
                *[str(value or "").strip() for value in _as_list(item.get("surfaces"))],
            ]
        )
        glosses = _stable_unique(
            [
                str(item.get("meaning") or "").strip(),
                *[str(value or "").strip() for value in _as_list(item.get("meanings"))],
                *[str(value or "").strip() for value in _as_list(item.get("glosses"))],
            ]
        )
        if not surfaces or not glosses:
            continue
        source_id = str(
            item.get("source_id")
            or item.get("id")
            or f"{path.name}:{surfaces[0]}"
        )
        yield {
            "record_id": f"reference:{source_id}",
            "surfaces": _stable_unique(normalize_key(value) for value in surfaces),
            "readings": _stable_unique(normalize_key(v) for v in _as_list(item.get("readings") or item.get("reading"))),
            "part_of_speech": _stable_unique(normalize_key(v) for v in _as_list(item.get("part_of_speech") or item.get("pos"))),
            "domains": _stable_unique(normalize_key(v) for v in _as_list(item.get("domains") or item.get("domain") or item.get("category"))),
            "candidates": [
                {
                    "label": str(item.get("label") or glosses[0]).strip(),
                    "glosses": glosses,
                    "part_of_speech": _stable_unique(str(v or "").strip() for v in _as_list(item.get("part_of_speech") or item.get("pos"))),
                    "domains": _stable_unique(str(v or "").strip() for v in _as_list(item.get("domains") or item.get("domain") or item.get("category"))),
                    "polarity": str(item.get("polarity") or "unspecified"),
                    "intensity": item.get("intensity"),
                    "parameters": item.get("parameters") or {},
                    "register": item.get("register") or {},
                    "context": item.get("context") or {},
                }
            ],
            "source": {
                **nested_source,
                "dataset": str(item.get("dataset") or nested_source.get("dataset") or "local-semantic-reference"),
                "version": str(item.get("version") or nested_source.get("version") or ""),
                "source_id": source_id,
                "license": str(item.get("license") or nested_source.get("license") or "Master-provided project reference"),
                "source_url": str(item.get("source_url") or nested_source.get("source_url") or ""),
                "source_sha256": str(item.get("source_sha256") or nested_source.get("source_sha256") or ""),
                "attribution": str(item.get("attribution") or nested_source.get("attribution") or ""),
                "path": str(path),
            },
        }


def _reference_score(target: dict[str, Any], reference: dict[str, Any]) -> int:
    target_readings = {normalize_key(v) for v in _as_list(target.get("readings")) if normalize_key(v)}
    target_pos = {normalize_key(v) for v in _as_list(target.get("part_of_speech")) if normalize_key(v)}
    target_domains = {normalize_key(v) for v in _as_list(target.get("domains")) if normalize_key(v)}
    ref_readings = set(reference.get("readings") or [])
    ref_pos = set(reference.get("part_of_speech") or [])
    ref_domains = set(reference.get("domains") or [])

    score = 0
    if target_readings and ref_readings:
        score += 8 if target_readings & ref_readings else -4
    if target_pos and ref_pos:
        score += 4 if target_pos & ref_pos else -2
    if target_domains and ref_domains and target_domains & ref_domains:
        score += 2
    return score


def _proposal_candidates(
    record: dict[str, Any],
    references: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not references:
        return [], []
    target_readings = {
        normalize_key(value)
        for value in _as_list(record.get("readings"))
        if normalize_key(value)
    }
    compatible: list[dict[str, Any]] = []
    for reference in references:
        ref_readings = set(reference.get("readings") or [])
        # Same spelling with a contradictory explicit reading is a different lexical
        # candidate. Preserve it as ambiguity evidence; do not copy its definition.
        if target_readings and ref_readings and not target_readings & ref_readings:
            continue
        compatible.append(reference)
    if not compatible:
        return [], []
    scored = [(reference, _reference_score(record, reference)) for reference in compatible]
    best_score = max(score for _, score in scored)
    selected = [reference for reference, score in scored if score == best_score][:8]

    proposals: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    signatures: set[tuple[str, ...]] = set()
    for reference in selected:
        evidence.append(
            {
                "reference_record_id": reference.get("record_id"),
                "score": best_score,
                "source": reference.get("source") or {},
            }
        )
        for candidate in reference.get("candidates") or []:
            glosses = _candidate_glosses(candidate)
            signature = tuple(glosses)
            if not glosses or signature in signatures:
                continue
            signatures.add(signature)
            proposal = dict(candidate)
            proposal["candidate_id"] = (
                f"{record.get('record_id')}:semantic-enrichment:{len(proposals)+1:03d}"
            )
            proposal["evidence_ids"] = [str(reference.get("record_id"))]
            proposal["review_status"] = "needs-evidence"
            proposal["meaning_source"] = "approved-record-reference"
            proposals.append(proposal)
    return proposals, evidence


def _external_proposals(
    record: dict[str, Any],
    references: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals, evidence = _proposal_candidates(record, references)
    for proposal in proposals:
        proposal["meaning_source"] = "local-reference-pack"
    return proposals, evidence


def _build_reference_indexes(
    review_records_path: Path,
    reference_roots: Iterable[Path],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    internal_refs: dict[str, dict[str, Any]] = {}
    internal_surface: dict[str, list[str]] = defaultdict(list)
    for record in _iter_jsonl(review_records_path):
        if _semantic_status(record) != "approved" or not record_has_real_meaning(record):
            continue
        compact = _record_reference(record)
        record_id = str(compact["record_id"])
        internal_refs[record_id] = compact
        for surface in compact["surfaces"]:
            internal_surface[surface].append(record_id)

    external_refs: dict[str, dict[str, Any]] = {}
    external_surface: dict[str, list[str]] = defaultdict(list)
    paths: list[Path] = []
    for root in reference_roots:
        if root.is_file() and root.suffix == ".jsonl":
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(root.rglob("*.jsonl")))
    for path in sorted(set(paths), key=str):
        for reference in _load_external_reference(path):
            record_id = str(reference["record_id"])
            external_refs[record_id] = reference
            for surface in reference["surfaces"]:
                external_surface[surface].append(record_id)
    return internal_refs, internal_surface, external_refs, external_surface


def _matching_refs(
    record: dict[str, Any],
    refs: dict[str, dict[str, Any]],
    surface_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    ids: list[str] = []
    seen: set[str] = set()
    for surface in _as_list(record.get("normalized_surfaces") or record.get("surfaces")):
        key = normalize_key(surface)
        for record_id in surface_index.get(key, []):
            if record_id in seen or record_id == record.get("record_id"):
                continue
            seen.add(record_id)
            ids.append(record_id)
    return [refs[record_id] for record_id in ids]


def build_semantic_enrichment_queue(
    review_records_path: Path,
    output_root: Path,
    *,
    reference_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    """Inspect every record and write a meaning-enrichment/review queue.

    Existing approved semantics are used only as evidence. Proposed meanings are never
    written back as approved data; a Decision Ledger entry is still required.
    """
    internal_refs, internal_surface, external_refs, external_surface = _build_reference_indexes(
        review_records_path, reference_roots
    )

    output_root.mkdir(parents=True, exist_ok=True)
    queue_path = output_root / "semantic-enrichment-queue.jsonl"
    counters: Counter[str] = Counter()
    source_missing: Counter[str] = Counter()
    dataset_missing: Counter[str] = Counter()
    runtime_incomplete_ids: list[str] = []

    with queue_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in _iter_jsonl(review_records_path):
            counters["total_records"] += 1
            has_meaning = record_has_real_meaning(record)
            semantic_approved = _semantic_status(record) == "approved"
            runtime_eligible = record.get("runtime_eligible") is True

            if has_meaning:
                counters["records_with_real_meaning"] += 1
            else:
                counters["meaning_missing_records"] += 1
                source_missing[str(record.get("source_kind"))] += 1
                dataset_missing[str((record.get("source") or {}).get("dataset"))] += 1

            if runtime_eligible and (not has_meaning or not semantic_approved):
                counters["runtime_semantic_incomplete_records"] += 1
                if len(runtime_incomplete_ids) < 50:
                    runtime_incomplete_ids.append(str(record.get("record_id")))
            if runtime_eligible and not has_meaning:
                counters["runtime_missing_meaning_records"] += 1
            if runtime_eligible and has_meaning and not semantic_approved:
                counters["runtime_existing_meaning_unapproved_records"] += 1

            if has_meaning and (not runtime_eligible or semantic_approved):
                continue

            proposals: list[dict[str, Any]] = []
            evidence: list[dict[str, Any]] = []
            status = "approval-required"
            if not has_meaning:
                internal = _matching_refs(record, internal_refs, internal_surface)
                proposals, evidence = _proposal_candidates(record, internal)
                if proposals:
                    status = "proposed-from-approved-record"
                    counters["proposed_from_approved_records"] += 1
                else:
                    external = _matching_refs(record, external_refs, external_surface)
                    proposals, evidence = _external_proposals(record, external)
                    if proposals:
                        status = "proposed-from-local-reference-pack"
                        counters["proposed_from_reference_packs"] += 1
                    else:
                        status = "unresolved-meaning"
                        counters["unresolved_meaning_records"] += 1

            queue_item = {
                "record_id": record.get("record_id"),
                "input_sha256": record.get("input_sha256"),
                "source_kind": record.get("source_kind"),
                "source": record.get("source") or {},
                "lemma": record.get("lemma"),
                "surfaces": record.get("surfaces") or [],
                "normalized_surfaces": record.get("normalized_surfaces") or [],
                "readings": record.get("readings") or [],
                "part_of_speech": record.get("part_of_speech") or [],
                "domains": record.get("domains") or [],
                "semantic_scope_status": _semantic_status(record),
                "current_meaning_candidates": record.get("meaning_candidates") or [],
                "proposed_meaning_candidates": proposals,
                "semantic_enrichment_status": status,
                "human_review_required": True,
                "review_scope": "semantic",
                "evidence": evidence,
                "runtime_eligible": runtime_eligible,
                "instruction": (
                    "Review proposed meaning evidence and write an explicit semantic "
                    "Decision Ledger entry. Automatic approval/runtime promotion is forbidden."
                ),
            }
            output.write(_json_line(queue_item) + "\n")
            counters["enrichment_queue_records"] += 1

    report = {
        "schema_version": "1.0.0",
        "mode": "deterministic-build-time-semantic-enrichment",
        "boundaries": {
            "all_source_kinds": True,
            "automatic_definition_generation": False,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
            "decision_ledger_required": True,
            "placeholder_glosses_are_not_meanings": True,
            "future_domain_and_user_packs_supported": True,
        },
        **dict(sorted(counters.items())),
        "missing_by_source_kind": dict(sorted(source_missing.items())),
        "missing_by_dataset": dict(sorted(dataset_missing.items())),
        "runtime_incomplete_sample_ids": runtime_incomplete_ids,
        "reference_record_count": len(internal_refs),
        "external_reference_record_count": len(external_refs),
        "queue_file": {
            "path": queue_path.name,
            "bytes": queue_path.stat().st_size,
            "sha256": _sha256_file(queue_path),
        },
    }
    report_path = output_root / "semantic-enrichment-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def require_all_meanings_complete(report: dict[str, Any]) -> None:
    missing = int(report.get("meaning_missing_records", 0))
    runtime_incomplete = int(report.get("runtime_semantic_incomplete_records", 0))
    if missing or runtime_incomplete:
        raise RuntimeError(
            "SEMANTIC_MEANING_REQUIRED: "
            f"meaning_missing_records={missing}; "
            f"runtime_semantic_incomplete_records={runtime_incomplete}; "
            "review semantic-enrichment-queue.jsonl and add explicit Decision Ledger entries"
        )
