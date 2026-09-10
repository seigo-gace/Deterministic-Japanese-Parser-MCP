#!/usr/bin/env python3
"""Enrich the checked-in 120k lexical snapshot with JMdict sense candidates.

The output is a review-only lexicon input for the unified semantic pipeline.
It never changes the checked-in lexical runtime or auto-approves source glosses.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from typing import Any, Iterable
import unicodedata


def normalize(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def stable(values: Iterable[str]) -> list[str]:
    return sorted({normalize(value) for value in values if normalize(value)})


def texts(element: ET.Element, tag: str) -> list[str]:
    return stable(item.text or "" for item in element.findall(tag))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_jsonl(path: Path):
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"record must be an object: {path}:{line_number}")
            yield item


def load_records(root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_source_id: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    paths = sorted([*root.rglob("*.jsonl"), *root.rglob("*.jsonl.gz")], key=str)
    for path in paths:
        for item in iter_jsonl(path):
            source = item.get("source") or {}
            if source.get("dataset") != "JMdict":
                continue
            source_id = normalize(source.get("source_id"))
            record_id = normalize(item.get("record_id"))
            if not source_id or not record_id:
                raise ValueError(f"JMdict source_id/record_id missing: {path}")
            if source_id in by_source_id:
                raise ValueError(f"duplicate JMdict source_id: {source_id}")
            item = dict(item)
            by_source_id[source_id] = item
            records.append(item)
    return by_source_id, records


def build_candidate(
    sense: ET.Element,
    *,
    record_id: str,
    sequence: str,
    sense_index: int,
    source_version: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    glosses: list[dict[str, str]] = []
    for gloss in sense.findall("gloss"):
        value = normalize(gloss.text)
        if not value:
            continue
        language = gloss.attrib.get(
            "{http://www.w3.org/XML/1998/namespace}lang", "eng"
        )
        glosses.append({"language": language, "text": value})
    if not glosses:
        return None
    english = [item["text"] for item in glosses if item["language"] == "eng"]
    return {
        "candidate_id": f"{record_id}:jmdict:{sequence}:sense:{sense_index:03d}",
        "label": english[0] if english else glosses[0]["text"],
        "glosses": [item["text"] for item in glosses],
        "multilingual_glosses": glosses,
        "part_of_speech": texts(sense, "pos"),
        "domains": texts(sense, "field"),
        "usage_labels": stable([*texts(sense, "misc"), *texts(sense, "dial")]),
        "polarity": "unspecified",
        "intensity": None,
        "parameters": {},
        "register": {},
        "context": {
            "restricted_writings": texts(sense, "stagk"),
            "restricted_readings": texts(sense, "stagr"),
        },
        "relations": {
            "cross_references": texts(sense, "xref"),
            "antonyms": texts(sense, "ant"),
        },
        "evidence_ids": [f"jmdict:{sequence}:sense:{sense_index:03d}"],
        "review_status": "needs-evidence",
        "source": {
            "dataset": "JMdict",
            "version": source_version,
            "license": "CC-BY-SA-4.0",
            "source_id": sequence,
            "source_url": "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz",
            "source_sha256": source_sha256,
            "evidence_scope": "semantic_candidate",
            "attribution": "Electronic Dictionary Research and Development Group",
        },
        "review_note": (
            "Source glosses are meaning candidates. Japanese context, polarity, "
            "intensity and examples require review before runtime promotion."
        ),
    }


def write_gzip_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as handle:
            for record in records:
                handle.write(
                    (
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "record_count": len(records),
    }


def build_semantic_lexicon(
    *,
    input_path: Path,
    lexicon_root: Path,
    output_root: Path,
    report_path: Path,
    source_version: str,
    expected_sha256: str,
    expected_records: int,
    shard_size: int,
) -> dict[str, Any]:
    actual_sha256 = sha256_file(input_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "JMdict source checksum mismatch: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    targets, records = load_records(lexicon_root)
    if len(records) != expected_records:
        raise ValueError(
            f"target count mismatch: expected={expected_records} actual={len(records)}"
        )

    matched: set[str] = set()
    candidate_count = 0
    multi_sense_records = 0
    opener = gzip.open if input_path.name.endswith(".gz") else open
    with opener(input_path, "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "entry":
                continue
            sequence = normalize(element.findtext("ent_seq"))
            record = targets.get(sequence)
            if record is not None:
                candidates: list[dict[str, Any]] = []
                for index, sense in enumerate(element.findall("sense"), 1):
                    candidate = build_candidate(
                        sense,
                        record_id=record["record_id"],
                        sequence=sequence,
                        sense_index=index,
                        source_version=source_version,
                        source_sha256=actual_sha256,
                    )
                    if candidate:
                        candidates.append(candidate)
                if not candidates:
                    raise ValueError(f"no JMdict meanings: {sequence}")
                record["meaning_candidates"] = candidates
                record["review_status"] = "needs-evidence"
                record["approval_scopes"] = {
                    **dict(record.get("approval_scopes") or {}),
                    "lexical": "approved",
                    "semantic": "needs-evidence",
                    "pragmatic": "needs-evidence",
                    "task": "needs-evidence",
                    "external_action": "needs-evidence",
                }
                record["notes"] = list(record.get("notes") or []) + [
                    "Semantic candidates were restored from checksum-locked JMdict; "
                    "runtime promotion remains review-gated."
                ]
                matched.add(sequence)
                candidate_count += len(candidates)
                if len(candidates) > 1:
                    multi_sense_records += 1
            element.clear()

    missing = sorted(set(targets) - matched)
    if missing:
        raise ValueError(
            f"semantic coverage missing={len(missing)} sample={missing[:20]}"
        )
    records.sort(key=lambda item: item["record_id"])
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = []
    for start in range(0, len(records), shard_size):
        outputs.append(
            write_gzip_jsonl(
                output_root / f"jmdict-semantic-{start // shard_size:04d}.jsonl.gz",
                records[start : start + shard_size],
            )
        )
    manifest = {
        "schema_version": "1.0.0",
        "mode": "review-only-semantic-source-overlay",
        "source_version": source_version,
        "source_sha256": actual_sha256,
        "record_count": len(records),
        "meaning_candidate_count": candidate_count,
        "multi_sense_record_count": multi_sense_records,
        "review_status": "needs-evidence",
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
        "outputs": outputs,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--lexicon-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-records", type=int, default=120000)
    parser.add_argument("--shard-size", type=int, default=10000)
    args = parser.parse_args()
    result = build_semantic_lexicon(
        input_path=args.input,
        lexicon_root=args.lexicon_root,
        output_root=args.output_root,
        report_path=args.report,
        source_version=args.source_version,
        expected_sha256=args.expected_sha256,
        expected_records=args.expected_records,
        shard_size=args.shard_size,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
