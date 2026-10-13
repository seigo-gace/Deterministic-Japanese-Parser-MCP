#!/usr/bin/env python3
"""Prepare explicit GPT CHAT J-Ono semantic Decision Ledger entries.

This tool expands one exact, digest-bound GPT CHAT review authorization into
per-record semantic decisions. It never applies decisions, never edits source
records, never approves lexical/POS, and never promotes runtime data.

The authorization is valid only for the exact review queue and exact audit
reports reviewed by GPT CHAT. Any digest, count, blocker, provenance, or
candidate-trace drift fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _norm(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value or "")).strip(),
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL object required: {path}:{line_number}")
        rows.append(value)
    return rows


def _evidence_summary(record: dict[str, Any]) -> tuple[list[str], list[str], int, bool]:
    evidence = record.get("review_evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"review_evidence missing: {record.get('record_id')}")
    semantic_types: set[str] = set()
    for value in (
        evidence.get("semantic_type_code"),
        evidence.get("semantic_type_label"),
    ):
        text = _norm(value)
        if text:
            semantic_types.add(text)
    equivalents: set[str] = {
        _norm(value)
        for value in evidence.get("equivalents") or []
        if _norm(value)
    }
    refer = bool(_norm(evidence.get("refer")))
    for item in evidence.get("resolved_meaning_evidence") or []:
        if not isinstance(item, dict):
            continue
        for value in (
            item.get("semantic_type_code"),
            item.get("semantic_type_label"),
        ):
            text = _norm(value)
            if text:
                semantic_types.add(text)
        for value in item.get("equivalents") or []:
            text = _norm(value)
            if text:
                equivalents.add(text)
        if bool(item.get("via_refer")):
            refer = True
    meanings = [
        _norm(candidate.get("label"))
        for candidate in record.get("meaning_candidates") or []
        if isinstance(candidate, dict) and _norm(candidate.get("label"))
    ]
    return sorted(meanings), sorted(semantic_types), len(equivalents), refer


def _validate_record(record: dict[str, Any]) -> int:
    rid = _norm(record.get("record_id"))
    if not rid:
        raise ValueError("J_ONO_CHAT_REVIEW_RECORD_ID_MISSING")
    approval = record.get("approval")
    if not isinstance(approval, dict):
        raise ValueError(f"J_ONO_CHAT_REVIEW_APPROVAL_MISSING:{rid}")
    blockers = approval.get("blockers_by_scope") or {}
    if list(blockers.get("semantic") or []):
        raise ValueError(f"J_ONO_CHAT_REVIEW_SEMANTIC_BLOCKED:{rid}")
    if "semantic" not in set(approval.get("review_scopes") or []):
        raise ValueError(f"J_ONO_CHAT_REVIEW_SEMANTIC_SCOPE_MISSING:{rid}")
    if approval.get("scopes", {}).get("lexical") == "approved":
        raise ValueError(f"J_ONO_CHAT_REVIEW_LEXICAL_PREAPPROVED:{rid}")
    if record.get("runtime_eligible") is True:
        raise ValueError(f"J_ONO_CHAT_REVIEW_RUNTIME_PREELIGIBLE:{rid}")

    requirements = record.get("review_requirements") or {}
    if requirements.get("polarity") is not False:
        raise ValueError(f"J_ONO_CHAT_REVIEW_POLARITY_PATCH_REQUIRED:{rid}")
    if requirements.get("intensity") is not False:
        raise ValueError(f"J_ONO_CHAT_REVIEW_INTENSITY_PATCH_REQUIRED:{rid}")

    source = record.get("source") or {}
    if not _norm(source.get("source_id")).startswith("j-ono-definitions:"):
        raise ValueError(f"J_ONO_CHAT_REVIEW_SOURCE_ID_INVALID:{rid}")
    if not _norm(source.get("source_sha256")):
        raise ValueError(f"J_ONO_CHAT_REVIEW_SOURCE_DIGEST_MISSING:{rid}")

    evidence = record.get("review_evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"J_ONO_CHAT_REVIEW_EVIDENCE_MISSING:{rid}")
    if evidence.get("kind") != "j-ono-source-authored-review-evidence":
        raise ValueError(f"J_ONO_CHAT_REVIEW_EVIDENCE_KIND_INVALID:{rid}")
    if evidence.get("automatic_semantic_interpretation") is not False:
        raise ValueError(f"J_ONO_CHAT_REVIEW_AUTO_SEMANTIC_BOUNDARY:{rid}")

    resolved = {
        _norm(item.get("meaning"))
        for item in evidence.get("resolved_meaning_evidence") or []
        if isinstance(item, dict) and _norm(item.get("meaning"))
    }
    if not resolved:
        raise ValueError(f"J_ONO_CHAT_REVIEW_RESOLVED_MEANING_MISSING:{rid}")

    candidates = record.get("meaning_candidates") or []
    if not candidates:
        raise ValueError(f"J_ONO_CHAT_REVIEW_CANDIDATE_MISSING:{rid}")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"J_ONO_CHAT_REVIEW_CANDIDATE_INVALID:{rid}:{index}")
        if candidate.get("meaning_source") != "source-authored-adapter-record":
            raise ValueError(f"J_ONO_CHAT_REVIEW_CANDIDATE_SOURCE_INVALID:{rid}:{index}")
        values = {_norm(candidate.get("label"))}
        values.update(
            _norm(value)
            for value in candidate.get("glosses") or []
            if _norm(value)
        )
        values.discard("")
        if not values.intersection(resolved):
            raise ValueError(
                f"J_ONO_CHAT_REVIEW_CANDIDATE_NOT_TRACEABLE:{rid}:{index}"
            )
    input_sha = _norm(record.get("input_sha256"))
    if len(input_sha) != 64 or any(ch not in "0123456789abcdef" for ch in input_sha):
        raise ValueError(f"J_ONO_CHAT_REVIEW_INPUT_DIGEST_INVALID:{rid}")
    return len(candidates)


def _decision_for(
    record: dict[str, Any],
    *,
    reviewer: str,
    decided_at: str,
) -> dict[str, Any]:
    rid = str(record["record_id"])
    meanings, semantic_types, equivalent_count, refer = _evidence_summary(record)
    short_types = ", ".join(semantic_types[:4]) if semantic_types else "source-resolved"
    joined_meanings = " | ".join(meanings)
    rationale = (
        "Explicit GPT CHAT review of exact frozen-source J-Ono evidence. "
        f"Resolved meaning(s): {joined_meanings}. "
        f"Semantic type evidence: {short_types}; "
        f"equivalents={equivalent_count}; refer_provenance={'yes' if refer else 'no'}. "
        "All approved semantic candidates trace to source-authored resolved meaning "
        "evidence and this record has no semantic blocker. No polarity/intensity "
        "patch is required. Approve semantic scope only; lexical/POS remains "
        "separately evidence-blocked."
    )
    key = hashlib.sha256(
        (rid + "\0" + str(record["input_sha256"])).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "decision_id": f"GPTCHAT-20261011-JONO-{key}-SEM",
        "record_id": rid,
        "scope": "semantic",
        "status": "approved",
        "reviewer": reviewer,
        "decided_at": decided_at,
        "rationale": rationale,
        "input_sha256": str(record["input_sha256"]),
    }


def prepare_decisions(
    review_queue: Path,
    authorization_path: Path,
    effectiveness_report_path: Path,
    review_audit_report_path: Path,
    existing_ledger_path: Path,
    output_ledger_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    authorization = _read_json(authorization_path)
    queue_bytes = Path(review_queue).read_bytes()
    effectiveness_bytes = Path(effectiveness_report_path).read_bytes()
    audit_bytes = Path(review_audit_report_path).read_bytes()

    expected_queue_sha = str(authorization["review_queue_sha256"])
    if _sha256_bytes(queue_bytes) != expected_queue_sha:
        raise ValueError("J_ONO_CHAT_REVIEW_QUEUE_DIGEST_MISMATCH")
    if _sha256_bytes(effectiveness_bytes) != str(
        authorization["source_evidence_effectiveness_report_sha256"]
    ):
        raise ValueError("J_ONO_CHAT_REVIEW_EFFECTIVENESS_DIGEST_MISMATCH")
    if _sha256_bytes(audit_bytes) != str(
        authorization["review_audit_report_sha256"]
    ):
        raise ValueError("J_ONO_CHAT_REVIEW_AUDIT_DIGEST_MISMATCH")

    effectiveness = _read_json(effectiveness_report_path)
    semantic = effectiveness.get("semantic_evidence") or {}
    expected_pairs = int(authorization["expected_semantic_pair_count"])
    expected_full_clusters = int(authorization["expected_full_cluster_reduction"])
    if (
        semantic.get("distinguished_pairs") != expected_pairs
        or semantic.get("total_pairs") != expected_pairs
    ):
        raise ValueError("J_ONO_CHAT_REVIEW_PAIR_EVIDENCE_MISMATCH")
    if semantic.get("clusters_with_full_pair_reduction") != expected_full_clusters:
        raise ValueError("J_ONO_CHAT_REVIEW_CLUSTER_EVIDENCE_MISMATCH")
    boundaries = effectiveness.get("interpretation_boundary") or {}
    for key in (
        "automatic_merge",
        "automatic_meaning_judgement",
        "automatic_pos_fill",
        "automatic_approval",
        "runtime_promotion",
    ):
        if boundaries.get(key) is not False:
            raise ValueError(f"J_ONO_CHAT_REVIEW_BOUNDARY_BROKEN:{key}")

    audit = _read_json(review_audit_report_path)
    expected_records = int(authorization["expected_record_count"])
    if (
        audit.get("records") != expected_records
        or audit.get("review_queue_records") != expected_records
    ):
        raise ValueError("J_ONO_CHAT_REVIEW_AUDIT_RECORD_COUNT_MISMATCH")
    if audit.get("approved_records") != 0 or audit.get("runtime_eligible_records") != 0:
        raise ValueError("J_ONO_CHAT_REVIEW_PREMATURE_APPROVAL_OR_RUNTIME")

    rows = _read_jsonl(review_queue)
    if len(rows) != int(authorization["expected_record_count"]):
        raise ValueError("J_ONO_CHAT_REVIEW_RECORD_COUNT_MISMATCH")
    ids = [str(row.get("record_id") or "") for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("J_ONO_CHAT_REVIEW_DUPLICATE_RECORD_ID")

    candidate_count = sum(_validate_record(row) for row in rows)
    if candidate_count != int(authorization["expected_meaning_candidate_count"]):
        raise ValueError("J_ONO_CHAT_REVIEW_CANDIDATE_COUNT_MISMATCH")

    existing_text = Path(existing_ledger_path).read_text(encoding="utf-8")
    existing = _read_jsonl(existing_ledger_path)
    existing_ids = {str(item.get("decision_id") or "") for item in existing}
    existing_record_scopes = {
        (str(item.get("record_id") or ""), str(item.get("scope") or ""))
        for item in existing
    }
    for rid in ids:
        if (rid, "semantic") in existing_record_scopes:
            raise ValueError(f"J_ONO_CHAT_REVIEW_EXISTING_SEMANTIC_DECISION:{rid}")

    reviewer = str(authorization["reviewer"])
    decided_at = str(authorization["decided_at"])
    decisions = [
        _decision_for(record, reviewer=reviewer, decided_at=decided_at)
        for record in sorted(rows, key=lambda item: str(item["record_id"]))
    ]
    new_ids = [item["decision_id"] for item in decisions]
    if len(set(new_ids)) != len(new_ids) or existing_ids.intersection(new_ids):
        raise ValueError("J_ONO_CHAT_REVIEW_DUPLICATE_DECISION_ID")

    append_text = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for item in decisions
    )
    combined = existing_text
    if combined and not combined.endswith("\n"):
        combined += "\n"
    combined += append_text
    Path(output_ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_ledger_path).write_text(combined, encoding="utf-8", newline="\n")

    report = {
        "status": "J_ONO_CHAT_SEMANTIC_DECISIONS_PREPARED",
        "authorization_reviewed_head": authorization["reviewed_head"],
        "authorization_reviewed_run_id": authorization["reviewed_run_id"],
        "review_queue_sha256": expected_queue_sha,
        "existing_decision_count": len(existing),
        "new_semantic_decision_count": len(decisions),
        "total_decision_count": len(existing) + len(decisions),
        "meaning_candidate_count": candidate_count,
        "semantic_approved_records": len(decisions),
        "lexical_approved_records": 0,
        "decision_patch_count": sum("patch" in item for item in decisions),
        "automatic_approval": False,
        "decision_application": False,
        "runtime_promotion": False,
        "combined_ledger_sha256": _sha256_bytes(combined.encode("utf-8")),
        "combined_ledger_bytes": len(combined.encode("utf-8")),
    }
    Path(report_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-queue", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--effectiveness-report", type=Path, required=True)
    parser.add_argument("--review-audit-report", type=Path, required=True)
    parser.add_argument("--existing-ledger", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = prepare_decisions(
        args.review_queue,
        args.authorization,
        args.effectiveness_report,
        args.review_audit_report,
        args.existing_ledger,
        args.output_ledger,
        args.report,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
