#!/usr/bin/env python3
"""Compile direct-final MCP data into the existing runtime ABIs.

Build-time only: no Factory, no meaning generation, and no second runtime.
Lexical identity is compiled for OpenLexiconRuntime. Only source-provided
``senses`` are projected into the existing SemanticDataRuntime ABI.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterable, Iterator
import unicodedata

DIRECT_SCHEMA = "djpmcp.direct-runtime-final.manifest.v1"
TARGET = "Deterministic-Japanese-Parser-MCP"
OPEN_BACKEND = "sqlite-index-v1"
REQUIRED = {"surface", "lemma", "reading", "pos", "dictionary", "cost", "entry_id"}


def _unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(v).strip() for v in values if v is not None and str(v).strip()})


def _key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value or "").split()).casefold()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _gzip_text(path: Path, chunks: Iterable[str]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_hash = hashlib.sha256()
    raw_bytes = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            for chunk in chunks:
                data = chunk.encode("utf-8")
                gz.write(data)
                raw_hash.update(data)
                raw_bytes += len(data)
    return {
        "path": str(path),
        "sha256": _sha(path),
        "bytes": path.stat().st_size,
        "uncompressed_sha256": raw_hash.hexdigest(),
        "uncompressed_bytes": raw_bytes,
    }


def _validate(manifest_path: Path, input_root: Path) -> tuple[dict[str, Any], list[Path], Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != DIRECT_SCHEMA:
        raise ValueError("direct final runtime schema mismatch")
    if manifest.get("target") != TARGET:
        raise ValueError("direct final runtime target mismatch")
    if manifest.get("factory_used") is not False:
        raise ValueError("direct final runtime must preserve factory_used=false")
    required = set((manifest.get("runtime_schema") or {}).get("required_core_fields") or [])
    if not REQUIRED.issubset(required):
        raise ValueError("direct final runtime required-core contract mismatch")
    validation = manifest.get("validation") or {}
    if int(validation.get("missing_required_core_fields", -1)) != 0:
        raise ValueError("direct final runtime reports missing required core fields")

    parts: list[Path] = []
    declared_records = 0
    for item in manifest.get("parts") or []:
        path = input_root / str(item["file"])
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != int(item["bytes"]):
            raise ValueError(f"direct final runtime size mismatch: {path.name}")
        if _sha(path) != str(item["sha256"]):
            raise ValueError(f"direct final runtime sha256 mismatch: {path.name}")
        declared_records += int(item["records"])
        parts.append(path)
    if not parts:
        raise ValueError("direct final runtime contains no parts")
    if int(validation.get("final_part_count", len(parts))) != len(parts):
        raise ValueError("direct final runtime part-count mismatch")
    expected = int(validation.get("full_json_records_validated", 0))
    if expected and expected != declared_records:
        raise ValueError("direct final runtime manifest record mismatch")

    support_meta = manifest.get("support_pack") or {}
    support = input_root / str(support_meta.get("file") or "")
    if not support.is_file():
        raise FileNotFoundError(support)
    if support.stat().st_size != int(support_meta.get("bytes", -1)):
        raise ValueError("direct final support size mismatch")
    if _sha(support) != str(support_meta.get("sha256") or ""):
        raise ValueError("direct final support sha256 mismatch")
    return manifest, parts, support


def _rows(parts: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in parts:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"runtime row must be object: {path}:{line_number}")
                missing = [name for name in REQUIRED if name not in row]
                if missing:
                    raise ValueError(f"runtime row missing core fields {missing}: {path}:{line_number}")
                yield row


def _source(row: dict[str, Any], date: str, manifest_sha: str) -> dict[str, Any]:
    return {
        "dataset": "MCP Direct Final Runtime",
        "version": date,
        "license": "see direct-runtime rights_lanes/source manifests",
        "source_id": str(row["entry_id"]),
        "source_url": "",
        "source_sha256": manifest_sha,
        "attribution": "source_datasets=" + ",".join(_unique(row.get("source_datasets") or [])),
    }


def _lexical(row: dict[str, Any], date: str, manifest_sha: str) -> dict[str, Any]:
    reading = str(row.get("reading") or "").strip()
    pos = row.get("pos")
    return {
        "record_id": str(row["entry_id"]),
        "lemma": str(row.get("lemma") or row["surface"]),
        "surfaces": _unique([row["surface"], row["lemma"], *_unique(row.get("aliases") or [])]),
        "readings": [reading] if reading else [],
        "reading_mappings": ([{"reading": reading, "restricted_to": [], "no_kanji": False}] if reading else []),
        "part_of_speech": _unique(pos if isinstance(pos, list) else [pos]),
        "lexical_category": "",
        "domains": _unique(row.get("domains") or []),
        "usage_labels": [],
        "source": _source(row, date, manifest_sha),
        "review_status": "approved",
    }


def _sense(raw: Any) -> tuple[str, list[str], dict[str, Any]]:
    if isinstance(raw, str):
        value = raw.strip()
        return value, ([value] if value else []), {}
    if not isinstance(raw, dict):
        value = str(raw).strip()
        return value, ([value] if value else []), {"source_value": raw}
    payload = dict(raw)
    glosses = _unique([payload.get("gloss"), payload.get("meaning"), payload.get("text"), payload.get("definition")])
    if isinstance(payload.get("glosses"), str):
        glosses = _unique([*glosses, payload["glosses"]])
    else:
        glosses = _unique([*glosses, *(payload.get("glosses") or [])])
    label = str(payload.get("label") or payload.get("name") or (glosses[0] if glosses else "")).strip()
    if not label:
        label = _json(payload)
    return label, (glosses or [label]), payload


def _semantic(row: dict[str, Any], lex: dict[str, Any]) -> dict[str, Any] | None:
    raw_senses = row.get("senses") or []
    if not raw_senses:
        return None
    row_pos = row.get("pos")
    pos_values = _unique(row_pos if isinstance(row_pos, list) else [row_pos])
    evidence = [f"direct-final:{v}" for v in _unique(row.get("evidence_samples") or [])]
    if not evidence:
        evidence = [f"direct-final:{row['entry_id']}"]
    candidates = []
    for number, raw in enumerate(raw_senses, 1):
        label, glosses, payload = _sense(raw)
        candidate_id = str(payload.get("sense_id") or payload.get("id") or "").strip()
        candidates.append({
            "candidate_id": candidate_id or f"{row['entry_id']}:sense:{number:04d}",
            "label": label,
            "glosses": glosses,
            "part_of_speech": _unique(payload.get("part_of_speech") or pos_values),
            "domains": _unique(payload.get("domains") or row.get("domains") or []),
            "polarity": "unspecified",
            "intensity": None,
            "parameters": payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {},
            "register": payload.get("register") if isinstance(payload.get("register"), dict) else {},
            "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
            "evidence_ids": evidence,
            "review_status": "approved",
            "direct_source_payload": payload,
        })
    semantic_surfaces = _unique([row["surface"], row["lemma"]])
    examples = row.get("examples")
    runtime_examples = examples if isinstance(examples, dict) else {
        "positive": _unique(examples or []), "negative": [], "boundary": []
    }
    return {
        "schema_version": "2.0.0",
        "record_id": lex["record_id"],
        "source_kind": "direct_final_runtime",
        "pack_namespace": "core",
        "lemma": lex["lemma"],
        "surfaces": semantic_surfaces,
        "normalized_surfaces": [_key(v) for v in semantic_surfaces],
        "readings": lex["readings"],
        "reading_mappings": lex["reading_mappings"],
        "part_of_speech": lex["part_of_speech"],
        "morphology": {},
        "domains": lex["domains"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": candidates,
        "polarity": "unspecified",
        "intensity": None,
        "semantic_targets": ["lexicon"],
        "parameters": {},
        "register": {},
        "context_conditions": {"required_any": [], "required_all": [], "forbidden_any": [], "required_social": [], "required_discourse": []},
        "task_candidates": [],
        "examples": runtime_examples,
        "risk_class": "semantic",
        "external_action_risk": False,
        "source": lex["source"],
        "approval": {
            "scopes": {"lexical": "approved", "semantic": "approved", "pragmatic": "not-applicable", "task": "not-applicable", "external_action": "not-applicable"},
            "approved_scopes": ["lexical", "semantic"],
            "review_scopes": [],
            "blockers_by_scope": {"lexical": [], "semantic": [], "pragmatic": [], "task": [], "external_action": []},
        },
        "decision_ids": [],
        "existing_runtime_links": [],
    }


def _init_open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;
        CREATE TABLE records(record_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE surface_lookup(surface TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(surface,record_id)) WITHOUT ROWID;
        CREATE TABLE reading_lookup(reading TEXT NOT NULL, record_id TEXT NOT NULL, restricted_to_json TEXT NOT NULL, no_kanji INTEGER NOT NULL, PRIMARY KEY(reading,record_id,restricted_to_json,no_kanji)) WITHOUT ROWID;
    """)
    return db


def _init_semantic(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;
        CREATE TABLE records(seq INTEGER PRIMARY KEY, record_id TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL);
        CREATE TABLE surfaces(surface TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(surface,record_id)) WITHOUT ROWID;
        CREATE TABLE readings(reading TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(reading,record_id)) WITHOUT ROWID;
    """)
    return db


def _grouped(db: sqlite3.Connection, query: str) -> Iterator[str]:
    yield "{"
    current = None
    values: list[str] = []
    first = True
    for key, record_id in db.execute(query):
        if current is None:
            current = key
        if key != current:
            if not first:
                yield ","
            yield json.dumps(current, ensure_ascii=False) + ":" + _json(values)
            first, current, values = False, key, []
        values.append(record_id)
    if current is not None:
        if not first:
            yield ","
        yield json.dumps(current, ensure_ascii=False) + ":" + _json(values)
    yield "}\n"


def _locator(db: sqlite3.Connection, shard_size: int) -> Iterator[str]:
    yield "{"
    first = True
    for seq, record_id in db.execute("SELECT seq,record_id FROM records ORDER BY seq"):
        if not first:
            yield ","
        first = False
        loc = {"shard": (seq - 1) // shard_size, "line": (seq - 1) % shard_size + 1}
        yield json.dumps(record_id, ensure_ascii=False) + ":" + _json(loc)
    yield "}\n"


def _write_semantic(db: sqlite3.Connection, root: Path, count: int, shard_size: int, date: str, manifest_sha: str) -> dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    outputs = []
    for name, query in (
        ("surface-index.json.gz", "SELECT surface,record_id FROM surfaces ORDER BY surface,record_id"),
        ("reading-index.json.gz", "SELECT reading,record_id FROM readings ORDER BY reading,record_id"),
    ):
        meta = _gzip_text(root / "indexes" / name, _grouped(db, query)); meta["path"] = f"indexes/{name}"; outputs.append(meta)
    meta = _gzip_text(root / "indexes/record-locator.json.gz", _locator(db, shard_size)); meta["path"] = "indexes/record-locator.json.gz"; outputs.append(meta)
    shards = (count + shard_size - 1) // shard_size if count else 0
    for shard in range(shards):
        start, end = shard * shard_size + 1, min(count, (shard + 1) * shard_size)
        relative = f"records/records-{shard:04d}.jsonl.gz"
        chunks = (payload + "\n" for (payload,) in db.execute("SELECT payload_json FROM records WHERE seq BETWEEN ? AND ? ORDER BY seq", (start, end)))
        meta = _gzip_text(root / relative, chunks); meta.update({"path": relative, "record_count": end - start + 1}); outputs.append(meta)
    manifest = {
        "schema_version": "2.0.0", "compiler_version": "direct-final-runtime-compat-1.0.0",
        "mode": "approved-direct-final-runtime-projection", "record_count": count,
        "record_shard_size": shard_size, "record_shards": shards, "approved_only": True,
        "preserve_ambiguity": True, "automatic_external_action": False,
        "direct_final_runtime": True, "factory_used": False, "source_date": date,
        "source_manifest_sha256": manifest_sha,
        "boundaries": {"meaning_re_resolution": False, "automatic_meaning_generation": False, "source_provided_senses_only": True, "external_action_generation": False},
        "outputs": outputs,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def compile_direct_final_runtime(*, manifest_path: Path, input_root: Path, system_root: Path, work_root: Path, semantic_shard_size: int = 10000) -> dict[str, Any]:
    if semantic_shard_size < 100:
        raise ValueError("semantic_shard_size must be at least 100")
    manifest, parts, support = _validate(manifest_path, input_root)
    date, manifest_sha = str(manifest.get("date") or ""), _sha(manifest_path)
    work_root.mkdir(parents=True, exist_ok=True)
    open_root = system_root / "compiled/open_lexicon"
    semantic_root = system_root / "compiled/canonical_dictionary_runtime"
    if open_root.exists():
        shutil.rmtree(open_root)
    open_db = _init_open(open_root / "lexicon.sqlite3")
    semantic_db = _init_semantic(work_root / "direct-final-semantic-stage.sqlite3")
    lexical_count = semantic_count = 0
    try:
        for row in _rows(parts):
            lex = _lexical(row, date, manifest_sha)
            record_id = lex["record_id"]
            open_db.execute("INSERT INTO records(record_id,payload_json) VALUES (?,?)", (record_id, _json(lex)))
            open_db.executemany("INSERT INTO surface_lookup(surface,record_id) VALUES (?,?)", [(v, record_id) for v in lex["surfaces"]])
            open_db.executemany("INSERT INTO reading_lookup(reading,record_id,restricted_to_json,no_kanji) VALUES (?,?,?,?)", [(m["reading"], record_id, _json(m.get("restricted_to") or []), int(bool(m.get("no_kanji", False)))) for m in lex["reading_mappings"]])
            lexical_count += 1
            sem = _semantic(row, lex)
            if sem is not None:
                semantic_count += 1
                semantic_db.execute("INSERT INTO records(seq,record_id,payload_json) VALUES (?,?,?)", (semantic_count, record_id, _json(sem)))
                semantic_db.executemany("INSERT INTO surfaces(surface,record_id) VALUES (?,?)", [(_key(v), record_id) for v in sem["normalized_surfaces"] if _key(v)])
                semantic_db.executemany("INSERT INTO readings(reading,record_id) VALUES (?,?)", [(_key(v), record_id) for v in sem["readings"] if _key(v)])
            if lexical_count % 50000 == 0:
                open_db.commit(); semantic_db.commit()
        open_db.commit(); semantic_db.commit()
        expected = int((manifest.get("validation") or {}).get("full_json_records_validated", 0))
        if lexical_count != expected:
            raise ValueError(f"direct final runtime row count mismatch: expected={expected} actual={lexical_count}")
        if open_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("open lexicon sqlite integrity check failed")
        unique_lemmas = len({json.loads(row[0])["lemma"] for row in open_db.execute("SELECT payload_json FROM records")}) if lexical_count <= 100000 else 0
        unique_surfaces = int(open_db.execute("SELECT COUNT(DISTINCT surface) FROM surface_lookup").fetchone()[0])
        unique_readings = int(open_db.execute("SELECT COUNT(DISTINCT reading) FROM reading_lookup").fetchone()[0])
        homographs = int(open_db.execute("SELECT COUNT(*) FROM (SELECT surface FROM surface_lookup GROUP BY surface HAVING COUNT(*) > 1)").fetchone()[0])
        open_db.close()
        db_path = open_root / "lexicon.sqlite3"
        open_manifest = {
            "schema_version": "1.1.0", "mode": "compiled_lexical_identity_only", "lookup_backend": OPEN_BACKEND,
            "record_count": lexical_count, "expected_record_count": lexical_count, "source_versions": [date],
            "source_licenses": ["mixed; preserved per direct-runtime rights_lanes"], "unique_lemmas": unique_lemmas,
            "unique_surfaces": unique_surfaces, "unique_readings": unique_readings, "homograph_surfaces": homographs,
            "record_shards": 0, "exact_lookup_only": True, "reading_alias_promotion": False,
            "semantic_auto_promotion": False, "intent_auto_promotion": False, "external_action_auto_promotion": False,
            "direct_final_runtime": True, "factory_used": False, "source_manifest_sha256": manifest_sha,
            "sqlite": {"path": "lexicon.sqlite3", "sha256": _sha(db_path), "bytes": db_path.stat().st_size},
        }
        (open_root / "manifest.json").write_text(json.dumps(open_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        semantic_manifest = _write_semantic(semantic_db, semantic_root, semantic_count, semantic_shard_size, date, manifest_sha)
        support_target = system_root / "compiled/direct_final_support" / support.name
        support_target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(support, support_target)
        result = {
            "schema_version": "djpmcp.direct-final-integration.v1", "target": TARGET, "factory_used": False,
            "source_manifest_sha256": manifest_sha, "source_runtime_records": lexical_count,
            "semantic_records": semantic_count, "support_records": int((manifest.get("support_pack") or {}).get("records", 0)),
            "open_lexicon": open_manifest, "semantic_runtime": semantic_manifest,
            "support": {"path": str(support_target), "sha256": _sha(support_target), "bytes": support_target.stat().st_size},
        }
        path = system_root / "compiled/direct_final_integration.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result
    finally:
        try:
            open_db.close()
        except Exception:
            pass
        semantic_db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--system-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--semantic-shard-size", type=int, default=10000)
    args = parser.parse_args()
    result = compile_direct_final_runtime(manifest_path=args.manifest, input_root=args.input_root, system_root=args.system_root, work_root=args.work_root, semantic_shard_size=args.semantic_shard_size)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
