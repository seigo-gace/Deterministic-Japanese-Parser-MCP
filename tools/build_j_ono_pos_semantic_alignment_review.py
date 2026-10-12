#!/usr/bin/env python3
"""Build review-only J-Ono ↔ JMdict sense/POS alignment evidence.

This tool narrows the 94 strong surface+reading POS candidates to explicit review
material. It never decides semantic equivalence, assigns POS, approves lexical
scope, or promotes runtime data.

The PR #26 Review Queue is immutable, checksum-locked evidence. Only the minimal
JMdict sense fields needed for review are copied into this transient evidence
artifact; authoritative payload ownership remains unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_J_ONO_RECORDS = 837
EXPECTED_PRIORITY_RECORDS = 94
EXPECTED_DISTINCT_JMDICT_RECORDS = 64
DEFAULT_PR26_QUEUE_SHA256 = (
    "29afe10d8d7f2696ff5bcbee9aefedcd2e438e4ff76c138386bc8504d606db17"
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"row must be object: {path}:{line_number}")
            rows.append(row)
    return rows


def _stream_pr26_records(
    path: Path,
    wanted: set[str],
    *,
    expected_sha256: str,
) -> tuple[dict[str, dict[str, Any]], str]:
    digest = hashlib.sha256()
    found: dict[str, dict[str, Any]] = {}
    with Path(path).open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            digest.update(raw)
            if not raw.strip():
                continue
            row = json.loads(raw.decode("utf-8"))
            if not isinstance(row, dict):
                raise ValueError(f"PR26 row must be object: {path}:{line_number}")
            record_id = str(row.get("record_id") or "").strip()
            if record_id in wanted:
                if record_id in found:
                    raise ValueError(f"duplicate PR26 record_id: {record_id}")
                found[record_id] = row
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise ValueError(
            "J_ONO_POS_ALIGNMENT_PR26_QUEUE_DIGEST_MISMATCH:"
            f"expected={expected_sha256}:actual={actual}"
        )
    missing = sorted(wanted - set(found))
    if missing:
        raise ValueError(
            "J_ONO_POS_ALIGNMENT_PR26_RECORDS_MISSING:" + ",".join(missing[:20])
        )
    return found, actual


def _jono_semantic_evidence(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    evidence = payload.get("j_ono_source_evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    resolved_meanings: list[dict[str, Any]] = []
    for item in evidence.get("resolved_meaning_evidence") or []:
        if not isinstance(item, dict):
            continue
        meaning = str(item.get("meaning") or "").strip()
        if not meaning:
            continue
        resolved_meanings.append({
            "meaning": meaning,
            "source_record_id": str(item.get("source_record_id") or "").strip(),
            "source_definition_index": int(item.get("source_definition_index") or 0),
            "via_refer": bool(item.get("via_refer")),
        })
    if not resolved_meanings:
        resolved_meanings = [
            {
                "meaning": str(value).strip(),
                "source_record_id": str(
                    (row.get("source") or {}).get("source_record_id") or ""
                ).strip(),
                "source_definition_index": 0,
                "via_refer": False,
            }
            for value in row.get("meanings") or []
            if str(value).strip()
        ]

    return {
        "resolved_meanings": resolved_meanings,
        "equivalents": sorted({
            str(value).strip()
            for value in evidence.get("equivalents") or []
            if str(value).strip()
        }),
        "semantic_type_code": str(evidence.get("semantic_type_code") or "").strip(),
        "semantic_type_label": str(evidence.get("semantic_type_label") or "").strip(),
        "refer": str(evidence.get("refer") or "").strip(),
    }


def _jmdict_sense_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in row.get("meaning_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
        result.append({
            "candidate_id": str(candidate.get("candidate_id") or "").strip(),
            "glosses": [
                str(value).strip()
                for value in candidate.get("glosses") or []
                if str(value).strip()
            ],
            "part_of_speech": sorted({
                str(value).strip()
                for value in candidate.get("part_of_speech") or []
                if str(value).strip()
            }),
            "evidence_ids": sorted({
                str(value).strip()
                for value in candidate.get("evidence_ids") or []
                if str(value).strip()
            }),
            "source_id": str(source.get("source_id") or "").strip(),
            "source_sha256": str(source.get("source_sha256") or "").strip(),
        })
    return result


def build_alignment_review(
    *,
    jono_records_path: Path,
    pos_review_queue_path: Path,
    pr26_review_queue_path: Path,
    output_path: Path,
    report_path: Path,
    expected_pr26_sha256: str = DEFAULT_PR26_QUEUE_SHA256,
    expected_jono_records: int = EXPECTED_J_ONO_RECORDS,
    expected_priority_records: int = EXPECTED_PRIORITY_RECORDS,
    expected_distinct_jmdict_records: int = EXPECTED_DISTINCT_JMDICT_RECORDS,
) -> dict[str, Any]:
    jono_rows = _read_jsonl(jono_records_path)
    if len(jono_rows) != expected_jono_records:
        raise ValueError(
            "J_ONO_POS_ALIGNMENT_SOURCE_COUNT_MISMATCH:"
            f"expected={expected_jono_records}:actual={len(jono_rows)}"
        )
    jono_by_id: dict[str, dict[str, Any]] = {}
    for row in jono_rows:
        rid = str(row.get("adapter_record_id") or "").strip()
        if not rid or rid in jono_by_id:
            raise ValueError(f"invalid/duplicate J-Ono adapter_record_id: {rid!r}")
        jono_by_id[rid] = row

    pos_rows = _read_jsonl(pos_review_queue_path)
    priority = [
        row
        for row in pos_rows
        if row.get("review_bucket") == "STRONG_UNIQUE_REVIEW_PRIORITY"
    ]
    if len(priority) != expected_priority_records:
        raise ValueError(
            "J_ONO_POS_ALIGNMENT_PRIORITY_COUNT_MISMATCH:"
            f"expected={expected_priority_records}:actual={len(priority)}"
        )

    wanted_jmdict: set[str] = set()
    for row in priority:
        rid = str(row.get("adapter_record_id") or "").strip()
        if rid not in jono_by_id:
            raise ValueError(f"POS priority references unknown J-Ono record: {rid}")
        refs = {
            str(value).strip()
            for value in row.get("open_lexicon_record_ids") or []
            if str(value).strip()
        }
        if not refs:
            raise ValueError(f"POS priority has no JMdict record reference: {rid}")
        wanted_jmdict.update(refs)

    if len(wanted_jmdict) != expected_distinct_jmdict_records:
        raise ValueError(
            "J_ONO_POS_ALIGNMENT_JMDICT_REFERENCE_COUNT_MISMATCH:"
            f"expected={expected_distinct_jmdict_records}:actual={len(wanted_jmdict)}"
        )

    jmdict, queue_sha = _stream_pr26_records(
        pr26_review_queue_path,
        wanted_jmdict,
        expected_sha256=expected_pr26_sha256,
    )

    outputs: list[dict[str, Any]] = []
    sense_count = 0
    for item in sorted(priority, key=lambda value: str(value["adapter_record_id"])):
        rid = str(item["adapter_record_id"])
        candidate_pos = sorted({
            str(value).strip()
            for value in item.get("candidate_pos") or []
            if str(value).strip()
        })
        if len(candidate_pos) != 1:
            raise ValueError(f"priority row must have one candidate POS: {rid}")
        jmdict_refs = sorted({
            str(value).strip()
            for value in item.get("open_lexicon_record_ids") or []
            if str(value).strip()
        })
        jmdict_records: list[dict[str, Any]] = []
        for ref in jmdict_refs:
            source = jmdict[ref]
            source_pos = sorted({
                str(value).strip()
                for value in source.get("part_of_speech") or []
                if str(value).strip()
            })
            if source_pos != candidate_pos:
                raise ValueError(
                    f"J_ONO_POS_ALIGNMENT_POS_DRIFT:{rid}:{ref}:"
                    f"expected={candidate_pos}:actual={source_pos}"
                )
            senses = _jmdict_sense_evidence(source)
            if not senses:
                raise ValueError(f"JMdict review record has no sense evidence: {ref}")
            sense_count += len(senses)
            jmdict_records.append({
                "record_id": ref,
                "lemma": str(source.get("lemma") or "").strip(),
                "readings": sorted({
                    str(value).strip()
                    for value in source.get("readings") or []
                    if str(value).strip()
                }),
                "part_of_speech": source_pos,
                "sense_evidence": senses,
            })

        outputs.append({
            "adapter_record_id": rid,
            "source_record_id": str(
                (jono_by_id[rid].get("source") or {}).get("source_record_id") or ""
            ).strip(),
            "candidate_pos": candidate_pos,
            "jono_semantic_evidence": _jono_semantic_evidence(jono_by_id[rid]),
            "jmdict_record_evidence": jmdict_records,
            "review_contract": (
                "Explicitly judge whether at least one checksum-locked JMdict sense "
                "matches the J-Ono source-authored meaning before any lexical POS decision."
            ),
            "semantic_alignment_status": "NEEDS_EXPLICIT_REVIEW",
            "automatic_semantic_alignment": False,
            "automatic_pos_fill": False,
            "automatic_approval": False,
            "runtime_promotion": False,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in outputs:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )

    report = {
        "status": "J_ONO_POS_SEMANTIC_ALIGNMENT_REVIEW_READY",
        "review_record_count": len(outputs),
        "distinct_jmdict_record_count": len(jmdict),
        "jmdict_sense_candidate_count": sense_count,
        "pr26_review_queue_sha256": queue_sha,
        "evidence_model": "checksum-locked-jono-plus-jmdict-sense-review",
        "semantic_alignment_judgement": False,
        "automatic_pos_fill": False,
        "automatic_approval": False,
        "runtime_promotion": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jono-records", type=Path, required=True)
    parser.add_argument("--pos-review-queue", type=Path, required=True)
    parser.add_argument("--pr26-review-queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--expected-pr26-sha256",
        default=DEFAULT_PR26_QUEUE_SHA256,
    )
    args = parser.parse_args()
    report = build_alignment_review(
        jono_records_path=args.jono_records,
        pos_review_queue_path=args.pos_review_queue,
        pr26_review_queue_path=args.pr26_review_queue,
        output_path=args.output,
        report_path=args.report,
        expected_pr26_sha256=args.expected_pr26_sha256,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
