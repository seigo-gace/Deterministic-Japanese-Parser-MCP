from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .models import LexicalCandidate, Token

FINAL_RUNTIME_INDEX_ENV = "DJPMCP_FINAL_RUNTIME_INDEX"
INDEX_SCHEMA_VERSION = "djpmcp.final-runtime-index.v1"
EXPECTED_TARGET = "Deterministic-Japanese-Parser-MCP"
_REQUIRED_SAFETY = {
    "factory_used": False,
}
_RICH_FIELDS = (
    "senses",
    "aliases",
    "examples",
    "translations",
    "relations",
    "metrics",
    "source_roles",
    "rights_lanes",
    "evidence_count",
    "evidence_occurrences",
    "evidence_samples",
    "entry_types",
)


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if item is not None and str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _rich_payload(row: dict[str, Any]) -> str | None:
    rich = {
        field: row[field]
        for field in _RICH_FIELDS
        if field in row and row[field] not in (None, "", [], {})
    }
    if not rich:
        return None
    return json.dumps(rich, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_jsonl_gzip(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"runtime row must be an object: {path}:{line_number}")
            yield line_number, value


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("target") != EXPECTED_TARGET:
        raise ValueError("final runtime manifest target mismatch")
    for field, expected in _REQUIRED_SAFETY.items():
        if manifest.get(field) is not expected:
            raise ValueError(f"final runtime manifest safety mismatch: {field}")
    schema = manifest.get("runtime_schema") or {}
    required = set(schema.get("required_core_fields") or [])
    expected_required = {
        "surface",
        "lemma",
        "reading",
        "pos",
        "dictionary",
        "cost",
        "entry_id",
    }
    if not expected_required.issubset(required):
        raise ValueError("final runtime manifest required_core_fields mismatch")
    parts = manifest.get("parts") or []
    if not parts:
        raise ValueError("final runtime manifest has no parts")
    validation = manifest.get("validation") or {}
    if validation.get("final_part_count") not in (None, len(parts)):
        raise ValueError("final runtime manifest part count mismatch")
    if validation.get("missing_required_core_fields") not in (None, 0):
        raise ValueError("final runtime source reports missing required fields")
    return manifest


def _connect_for_build(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-131072")
    return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            surface TEXT NOT NULL,
            lemma TEXT NOT NULL,
            reading TEXT NOT NULL,
            pos_json TEXT NOT NULL,
            dictionary_name TEXT,
            cost INTEGER,
            domains_json TEXT NOT NULL,
            source_datasets_json TEXT NOT NULL,
            rich_payload_json TEXT,
            source_part TEXT NOT NULL,
            source_line INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE support (
            support_id INTEGER PRIMARY KEY,
            record_type TEXT,
            payload_json TEXT NOT NULL
        );
        """
    )


def _insert_metadata(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            (
                str(key),
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            for key, value in values.items()
        ],
    )


def build_final_runtime_index(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    manifest = _load_manifest(manifest_path)
    source_root = manifest_path.parent
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    if temporary.exists():
        temporary.unlink()

    connection = _connect_for_build(temporary)
    inserted = 0
    support_inserted = 0
    try:
        _create_schema(connection)
        required_fields = set(manifest["runtime_schema"]["required_core_fields"])
        for part in manifest["parts"]:
            name = str(part["file"])
            path = source_root / name
            if not path.is_file():
                raise FileNotFoundError(path)
            if verify_hashes and _sha256(path) != part.get("sha256"):
                raise ValueError(f"final runtime SHA-256 mismatch: {name}")
            part_count = 0
            batch: list[tuple[Any, ...]] = []
            for line_number, row in _iter_jsonl_gzip(path):
                missing = required_fields.difference(row)
                if missing:
                    raise ValueError(
                        f"final runtime required fields missing: {name}:{line_number}:"
                        + ",".join(sorted(missing))
                    )
                entry_id = str(row["entry_id"])
                surface = str(row["surface"])
                lemma = str(row["lemma"])
                reading = str(row["reading"])
                if not entry_id or not surface:
                    raise ValueError(f"final runtime identity is empty: {name}:{line_number}")
                batch.append(
                    (
                        entry_id,
                        surface,
                        lemma,
                        reading,
                        json.dumps(_json_list(row.get("pos")), ensure_ascii=False, separators=(",", ":")),
                        None if row.get("dictionary") is None else str(row.get("dictionary")),
                        row.get("cost") if isinstance(row.get("cost"), int) else None,
                        json.dumps(_json_list(row.get("domains")), ensure_ascii=False, separators=(",", ":")),
                        json.dumps(_json_list(row.get("source_datasets")), ensure_ascii=False, separators=(",", ":")),
                        _rich_payload(row),
                        name,
                        line_number,
                    )
                )
                if len(batch) >= 5000:
                    connection.executemany(
                        """
                        INSERT INTO entries(
                            entry_id, surface, lemma, reading, pos_json,
                            dictionary_name, cost, domains_json,
                            source_datasets_json, rich_payload_json, source_part, source_line
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    part_count += len(batch)
                    inserted += len(batch)
                    batch.clear()
            if batch:
                connection.executemany(
                    """
                    INSERT INTO entries(
                        entry_id, surface, lemma, reading, pos_json,
                        dictionary_name, cost, domains_json,
                        source_datasets_json, rich_payload_json, source_part, source_line
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                part_count += len(batch)
                inserted += len(batch)
            if part_count != int(part.get("records", -1)):
                raise ValueError(
                    f"final runtime record count mismatch: {name}:"
                    f" expected={part.get('records')} actual={part_count}"
                )

        support = manifest.get("support_pack") or {}
        support_name = support.get("file")
        if support_name:
            support_path = source_root / str(support_name)
            if not support_path.is_file():
                raise FileNotFoundError(support_path)
            if verify_hashes and _sha256(support_path) != support.get("sha256"):
                raise ValueError("final runtime support SHA-256 mismatch")
            support_batch: list[tuple[str | None, str]] = []
            for _line_number, row in _iter_jsonl_gzip(support_path):
                support_batch.append(
                    (
                        None if row.get("record_type") is None else str(row.get("record_type")),
                        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    )
                )
                if len(support_batch) >= 5000:
                    connection.executemany(
                        "INSERT INTO support(record_type, payload_json) VALUES (?, ?)",
                        support_batch,
                    )
                    support_inserted += len(support_batch)
                    support_batch.clear()
            if support_batch:
                connection.executemany(
                    "INSERT INTO support(record_type, payload_json) VALUES (?, ?)",
                    support_batch,
                )
                support_inserted += len(support_batch)
            if support_inserted != int(support.get("records", 0)):
                raise ValueError(
                    "final runtime support count mismatch: "
                    f"expected={support.get('records')} actual={support_inserted}"
                )

        expected_total = sum(int(part["records"]) for part in manifest["parts"])
        if inserted != expected_total:
            raise ValueError(
                f"final runtime total count mismatch: expected={expected_total} actual={inserted}"
                )
        connection.executescript(
            """
            CREATE INDEX entries_surface_idx ON entries(surface);
            CREATE INDEX entries_lemma_idx ON entries(lemma);
            CREATE INDEX entries_reading_idx ON entries(reading);
            """
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        _insert_metadata(
            connection,
            {
                "schema_version": INDEX_SCHEMA_VERSION,
                "target": manifest["target"],
                "source_manifest_sha256": manifest_hash,
                "source_manifest_date": manifest.get("date"),
                "record_count": inserted,
                "support_record_count": support_inserted,
                "part_count": len(manifest["parts"]),
                "factory_used": False,
                "exact_lookup_only": True,
                "semantic_auto_promotion": False,
                "intent_auto_promotion": False,
                "external_action_auto_promotion": False,
            },
        )
        connection.commit()
        check = connection.execute("PRAGMA integrity_check").fetchone()
        if check is None or check[0] != "ok":
            raise ValueError("final runtime SQLite integrity_check failed")
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
    else:
        connection.close()
        os.replace(temporary, output_path)

    return {
        "index": str(output_path),
        "record_count": inserted,
        "support_record_count": support_inserted,
        "part_count": len(manifest["parts"]),
        "status": "PASS",
    }


class FinalRuntimeLexicon:
    """Read-only exact lookup over the completed Drive runtime data index.

    This adapter only exposes lexical candidates already present in the source.
    It never promotes a candidate to a semantic sense, intent, task or action.
    """

    _UNAVAILABLE: "FinalRuntimeLexicon | None" = None

    def __init__(self, index_path: str | Path):
        self.index_path = Path(index_path)
        self.available = False
        self.metadata: dict[str, Any] = {}
        self._connection: sqlite3.Connection | None = None
        if not self.index_path.is_file():
            return
        connection = sqlite3.connect(
            f"file:{self.index_path.resolve().as_posix()}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        metadata_rows = connection.execute("SELECT key, value FROM metadata").fetchall()
        metadata = {row["key"]: json.loads(row["value"]) for row in metadata_rows}
        required = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "target": EXPECTED_TARGET,
            "factory_used": False,
            "exact_lookup_only": True,
            "semantic_auto_promotion": False,
            "intent_auto_promotion": False,
            "external_action_auto_promotion": False,
        }
        for field, expected in required.items():
            if metadata.get(field) != expected:
                connection.close()
                raise ValueError(f"final runtime index safety mismatch: {field}")
        self._connection = connection
        self.metadata = metadata
        self.available = True

    @classmethod
    def unavailable(cls) -> "FinalRuntimeLexicon":
        if cls._UNAVAILABLE is None:
            instance = cls.__new__(cls)
            instance.index_path = Path(".")
            instance.available = False
            instance.metadata = {}
            instance._connection = None
            cls._UNAVAILABLE = instance
        return cls._UNAVAILABLE

    @classmethod
    def from_env(cls) -> "FinalRuntimeLexicon":
        value = os.getenv(FINAL_RUNTIME_INDEX)
        return cls(value) if value else cls.unavailable()

    @property
    def record_count(self) -> int:
        return int(self.metadata.get("record_count", 0))

    @property
    def support_record_count(self) -> int:
        return int(self.metadata.get("support_record_count", 0))

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            self.available = False

    def _rows(
        self,
        field: str,
        value: str,
        *,
        max_candidates: int,
    ) -> tuple[list[sqlite3.Row], int]:
        if not self.available or not value or self._connection is None:
            return [], 0
        if field not in {"surface", "lemma", "reading"}:
            raise ValueError(f"unsupported final runtime lookup field: {field}")
        limit = max(1, max_candidates)
        rows = self._connection.execute(
            f"""
            SELECT entry_id, surface, lemma, reading, pos_json,
                   dictionary_name, cost, domains_json, source_datasets_json,
                   rich_payload_json, COUNT(*) OVER() AS total_count
            FROM entries
            WHERE {field} = ?
            ORDER BY entry_id
            LIMIT ?
            """,
            (value, limit),
        ).fetchall()
        total = int(rows[0]["total_count"]) if rows else 0
        return rows, total

    def record_payload(self, record_id: str) -> dict[str, Any] | None:
        """Return source-backed fields for one final-runtime record.

        Rich fields remain data, not automatically promoted semantic decisions.
        """
        if not self.available or self._connection is None or not record_id:
            return None
        row = self._connection.execute(
            """
            SELECT entry_id, surface, lemma, reading, pos_json, dictionary_name,
                   cost, domains_json, source_datasets_json, rich_payload_json
            FROM entries WHERE entry_id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        payload: dict[str, Any] = {
            "entry_id": row["entry_id"],
            "surface": row["surface"],
            "lemma": row["lemma"],
            "reading": row["reading"],
            "pos": json.loads(row["pos_json"]),
            "dictionary": row["dictionary_name"],
            "cost": row["cost"],
            "domains": json.loads(row["domains_json"]),
            "source_datasets": json.loads(row["source_datasets_json"]),
        }
        if row["rich_payload_json"]:
            payload.update(json.loads(row["rich_payload_json"]))
        return payload

    @staticmethod
    def _candidate(row: sqlite3.Row, *, matched_text: str, match_type: str) -> LexicalCandidate:
        sources = json.loads(row["source_datasets_json"])
        return LexicalCandidate(
            record_id=row["entry_id"],
            lemma=row["lemma"],
            matched_text=matched_text,
            match_type=match_type,
            readings=[row["reading"]] if row["reading"] else [],
            restricted_to=[],
            no_kanji=False,
            part_of_speech=json.loads(row["pos_json"]),
            domains=json.loads(row["domains_json"]),
            usage_labels=[],
            source_dataset=(sources[0] if sources else row["dictionary_name"]),
            source_version=None,
            source_license=None,
        )

    def exact_lookup(
        self,
        text: str,
        *,
        match_type: str = "surface",
        max_candidates: int = 8,
    ) -> tuple[list[LexicalCandidate], int]:
        rows, total = self._rows("surface", text, max_candidates=max_candidates)
        return [
            self._candidate(row, matched_text=text, match_type=match_type)
            for row in rows
        ], total

    def lemma_lookup(
        self,
        lemma: str,
        *,
        max_candidates: int = 8,
    ) -> tuple[list[LexicalCandidate], int]:
        rows, total = self._rows("lemma", lemma, max_candidates=max_candidates)
        return [
            self._candidate(row, matched_text=lemma, match_type="normalized")
            for row in rows
        ], total

    def reading_lookup(
        self,
        reading: str,
        *,
        max_candidates: int = 8,
    ) -> tuple[list[LexicalCandidate], int]:
        rows, total = self._rows("reading", reading, max_candidates=max_candidates)
        return [
            self._candidate(row, matched_text=reading, match_type="reading")
            for row in rows
        ], total

    def lookup_token(self, token: Token, *, max_candidates: int = 8) -> Token:
        candidates, total = self.exact_lookup(
            token.surface,
            match_type="surface",
            max_candidates=max_candidates,
        )
        if not candidates and token.normalized != token.surface:
            candidates, total = self.exact_lookup(
                token.normalized,
                match_type="normalized",
                max_candidates=max_candidates,
            )
        if not candidates and token.reading:
            candidates, total = self.reading_lookup(
                token.reading,
                max_candidates=max_candidates,
            )
        status = "NO_MATCH"
        if total == 1:
            status = "MATCHED"
        elif total > 1:
            status = "AMBIGUOUS"
        return token.model_copy(
            update={
                "lexical_candidates": candidates,
                "lexical_candidate_total": total,
                "lexical_status": status,
            }
        )

    def annotate_tokens(self, tokens: list[Token], *, max_candidates: int = 8) -> list[Token]:
        if not self.available:
            return tokens
        return [self.lookup_token(token, max_candidates=max_candidates) for token in tokens]

    def support_type_counts(self) -> dict[str, int]:
        if not self.available or self._connection is None:
            return {}
        return {
            str(row[0] or "unknown"): int(row[1])
            for row in self._connection.execute(
                "SELECT record_type, COUNT(*) FROM support GROUP BY record_type ORDER BY record_type"
            )
        }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/read the DJPMCP final runtime SQLite index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a verified SQLite index from the final Drive data")
    build.add_argument("--manifest", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--skip-hash-verification", action="store_true")
    args = parser.parse_args(arvy)
    if args.command == "build":
        result = build_final_runtime_index(
            args.manifest,
            args.output,
            verify_hashes=not args.skip_hash_verification,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
