from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import unicodedata

from .models import MeaningGraph, OriginalSpan, Proposition, SenseCandidate, Token


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", value).casefold()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


class SemanticCandidateRuntime:
    """Expose source-validated meanings without selecting or applying them."""

    def __init__(self, root: Path, *, shard_cache_size: int = 4):
        del shard_cache_size  # retained for backwards-compatible construction
        self.root = Path(root)
        self.available = False
        self.manifest: dict[str, Any] = {}
        self._connection: sqlite3.Connection | None = None
        self.last_metrics: dict[str, int | float] = {
            "semantic_candidate_pack_available": 0,
            "semantic_candidate_pack_record_count": 0,
            "semantic_candidate_pack_match_count": 0,
            "semantic_candidate_pack_sense_count": 0,
        }

        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {
            "candidate_only": True,
            "approved_semantic_effects": False,
            "automatic_sense_selection": False,
            "automatic_parameter_application": False,
            "automatic_external_action": False,
            "preserve_ambiguity": True,
        }
        for name, expected in required.items():
            if manifest.get(name) is not expected:
                raise ValueError(
                    f"semantic candidate pack safety flag mismatch: {name}"
                )
        if manifest.get("storage") != "sqlite3-read-only-index":
            raise ValueError("semantic candidate pack storage is not indexed SQLite")
        database = manifest.get("database") or {}
        database_path = self.root / str(database.get("path", ""))
        if not database_path.is_file():
            raise FileNotFoundError(database_path)
        if _sha256_file(database_path) != database.get("sha256"):
            raise ValueError("semantic candidate SQLite digest mismatch")

        uri = f"file:{database_path.resolve().as_posix()}?mode=ro&immutable=1"
        connection = sqlite3.connect(
            uri,
            uri=True,
            check_same_thread=False,
            isolation_level=None,
        )
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA temp_store=MEMORY")
        actual_records = int(
            connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        )
        if actual_records != int(manifest.get("record_count", 0)):
            connection.close()
            raise ValueError("semantic candidate SQLite record count mismatch")
        self._connection = connection
        self.manifest = manifest
        self.available = True
        self.last_metrics = {
            "semantic_candidate_pack_available": 1,
            "semantic_candidate_pack_record_count": actual_records,
            "semantic_candidate_pack_match_count": 0,
            "semantic_candidate_pack_sense_count": 0,
        }

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("record_count", 0))

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        self._lookup.cache_clear()
        if connection is not None:
            connection.close()

    def __del__(self):  # pragma: no cover - best effort at interpreter shutdown
        try:
            self.close()
        except Exception:
            pass

    @lru_cache(maxsize=4096)
    def _lookup(
        self,
        table: str,
        key: str,
        max_records: int,
    ) -> tuple[dict[str, Any], ...]:
        if table not in {"surfaces", "readings"}:
            raise ValueError(f"unsupported candidate index: {table}")
        connection = self._connection
        if connection is None:
            return ()
        column = "surface" if table == "surfaces" else "reading"
        rows = connection.execute(
            f"""
            SELECT
                r.record_id,
                r.source_kind,
                r.lemma,
                r.part_of_speech_json,
                r.domains_json,
                r.candidates_json
            FROM {table} AS i
            JOIN records AS r ON r.record_id = i.record_id
            WHERE i.{column} = ?
            ORDER BY r.record_id
            LIMIT ?
            """,
            (key, max(1, max_records)),
        ).fetchall()
        return tuple(
            {
                "record_id": row[0],
                "source_kind": row[1],
                "lemma": row[2],
                "part_of_speech": json.loads(row[3]),
                "domains": json.loads(row[4]),
                "meaning_candidates": json.loads(row[5]),
                "runtime_mode": "candidate-only",
                "automatic_sense_selection_allowed": False,
                "automatic_parameter_application_allowed": False,
                "automatic_external_action_allowed": False,
            }
            for row in rows
        )

    def lookup_token(
        self,
        token: Token,
        *,
        max_records: int = 16,
    ) -> list[dict[str, Any]]:
        if not self.available:
            return []
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in (token.surface, token.normalized):
            key = _normalize(value)
            if not key:
                continue
            for record in self._lookup("surfaces", key, max_records):
                if record["record_id"] not in seen:
                    seen.add(record["record_id"])
                    records.append(record)
                    if len(records) >= max_records:
                        return records
        if not records and token.reading:
            key = _normalize(token.reading)
            for record in self._lookup("readings", key, max_records):
                if record["record_id"] not in seen:
                    seen.add(record["record_id"])
                    records.append(record)
                    if len(records) >= max_records:
                        break
        return records

    @staticmethod
    def _score(
        record: dict[str, Any],
        candidate: dict[str, Any],
        *,
        token: Token,
        context_text: str,
    ) -> tuple[int, list[str]]:
        score = 50
        evidence = [
            "source_validated_candidate_only",
            f"candidate_record:{record['record_id']}",
        ]
        token_pos = " ".join(token.pos).casefold()
        record_pos = " ".join(record.get("part_of_speech", [])).casefold()
        if token_pos and record_pos:
            token_families = {
                value
                for value in re.split(r"[^\w一-龥ぁ-んァ-ヶ]+", token_pos)
                if len(value) >= 2
            }
            if any(value in record_pos for value in token_families):
                score += 10
                evidence.append("candidate_pos_match")
        domains = [
            *record.get("domains", []),
            *candidate.get("domains", []),
        ]
        matched_domain = next(
            (
                str(domain)
                for domain in domains
                if str(domain)
                and str(domain).casefold() in context_text.casefold()
            ),
            None,
        )
        if matched_domain:
            score += 5
            evidence.append(f"candidate_domain:{matched_domain}")
        if candidate.get("evidence_ids"):
            score += 1
            evidence.append("candidate_source_evidence")
        return score, evidence

    @staticmethod
    def _related_indices(
        propositions: list[Proposition], token: Token
    ) -> list[int]:
        return [
            index
            for index, proposition in enumerate(propositions)
            if _overlap(token.span, proposition.source_span)
            or any(
                argument.span and _overlap(token.span, argument.span)
                for argument in proposition.arguments
            )
        ]

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
                "semantic_candidate_pack_used": False,
                "semantic_candidate_pack_record_count": 0,
                "semantic_candidate_pack_automatic_selection": False,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            return updated.model_copy(update={"semantic_hash": _stable_hash(updated)})

        context_text = "\n".join(
            [original_text, *conversation_context, *known_entities]
        )
        propositions = list(graph.propositions)
        matched_records: set[str] = set()
        exposed_senses = 0

        for token in tokens:
            records = self.lookup_token(token)
            if not records:
                continue
            related = self._related_indices(propositions, token)
            if not related:
                continue
            generated: list[SenseCandidate] = []
            for record in records:
                matched_records.add(record["record_id"])
                for candidate in record.get("meaning_candidates", []):
                    score, evidence = self._score(
                        record,
                        candidate,
                        token=token,
                        context_text=context_text,
                    )
                    generated.append(
                        SenseCandidate(
                            sense_id=candidate["candidate_id"],
                            label=(
                                candidate.get("label")
                                or next(
                                    iter(candidate.get("glosses") or []),
                                    candidate["candidate_id"],
                                )
                            ),
                            score=score,
                            evidence=evidence,
                        )
                    )
            generated.sort(key=lambda item: (-item.score, item.sense_id))
            for index in related:
                proposition = propositions[index]
                by_id = {
                    item.sense_id: item
                    for item in proposition.sense_candidates
                }
                for item in generated:
                    current = by_id.get(item.sense_id)
                    if current is None or item.score > current.score:
                        by_id[item.sense_id] = item
                candidates = sorted(
                    by_id.values(),
                    key=lambda item: (-item.score, item.sense_id),
                )[:32]
                exposed_senses += len(candidates)
                propositions[index] = proposition.model_copy(update={
                    "sense_candidates": candidates,
                    "inference_sources": list(dict.fromkeys([
                        *proposition.inference_sources,
                        "source-validated-semantic-candidate-pack",
                    ])),
                })

        quality = {
            **graph.quality_annotations,
            "semantic_candidate_pack_used": True,
            "semantic_candidate_pack_record_count": self.record_count,
            "semantic_candidate_pack_match_count": len(matched_records),
            "semantic_candidate_pack_sense_count": exposed_senses,
            "semantic_candidate_pack_automatic_selection": False,
            "semantic_candidate_pack_parameter_application": False,
            "semantic_candidate_pack_external_action": False,
        }
        updated = graph.model_copy(update={
            "propositions": propositions,
            "quality_annotations": quality,
        })
        updated = updated.model_copy(update={"semantic_hash": _stable_hash(updated)})
        self.last_metrics = {
            "semantic_candidate_pack_available": 1,
            "semantic_candidate_pack_record_count": self.record_count,
            "semantic_candidate_pack_match_count": len(matched_records),
            "semantic_candidate_pack_sense_count": exposed_senses,
        }
        return updated
