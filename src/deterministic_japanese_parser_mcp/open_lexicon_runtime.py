from __future__ import annotations

from collections import OrderedDict
import gzip
import json
from pathlib import Path
import re
from typing import Any

from .models import LexicalCandidate, Token

_KANJI = re.compile(r"[一-龥々〆ヵヶ]")


def _katakana_to_hiragana(value: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char
        for char in value
    )


_DEFAULT_RUNTIME: "OpenLexiconRuntime | None" = None


def register_default_open_lexicon(runtime: "OpenLexiconRuntime") -> None:
    global _DEFAULT_RUNTIME
    _DEFAULT_RUNTIME = runtime


def get_default_open_lexicon() -> "OpenLexiconRuntime":
    return _DEFAULT_RUNTIME or OpenLexiconRuntime.unavailable()


def _load_gzip_json(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


class OpenLexiconRuntime:
    """Exact-only lookup over the compiled 120k open lexicon.

    The runtime never infers senses, intents, tasks, pragmatic meanings, or
    executable actions. It exposes lexical candidates and preserves ambiguity.
    All record shards are preloaded before readiness so request-time lookup does
    not perform disk I/O or gzip expansion.
    """

    _UNAVAILABLE: "OpenLexiconRuntime | None" = None

    def __init__(self, root: Path, *, shard_cache_size: int = 4):
        self.root = Path(root)
        self.available = False
        self.records_preloaded = False
        self.manifest: dict[str, Any] = {}
        self.surface_index: dict[str, list[str]] = {}
        self.reading_index: dict[str, list[dict[str, Any]]] = {}
        self.record_locator: dict[str, dict[str, int]] = {}
        self.shard_cache_size = max(1, shard_cache_size)
        self._shard_cache: OrderedDict[int, dict[str, dict[str, Any]]] = OrderedDict()

        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_flags = {
            "exact_lookup_only": True,
            "reading_alias_promotion": False,
            "semantic_auto_promotion": False,
            "intent_auto_promotion": False,
            "external_action_auto_promotion": False,
        }
        for name, expected in required_flags.items():
            if manifest.get(name) is not expected:
                raise ValueError(
                    f"compiled open lexicon safety flag mismatch: {name}"
                )

        index_root = self.root / "indexes"
        required_paths = {
            "surface": index_root / "surface-index.json.gz",
            "reading": index_root / "reading-index.json.gz",
            "locator": index_root / "record-locator.json.gz",
        }
        missing = [str(path) for path in required_paths.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "compiled open lexicon indexes are incomplete: " + ", ".join(missing)
            )

        self.manifest = manifest
        self.surface_index = _load_gzip_json(required_paths["surface"])
        self.reading_index = _load_gzip_json(required_paths["reading"])
        self.record_locator = _load_gzip_json(required_paths["locator"])
        if len(self.record_locator) != manifest.get("record_count"):
            raise ValueError("compiled open lexicon record locator count mismatch")
        self.available = True

    @classmethod
    def unavailable(cls) -> "OpenLexiconRuntime":
        if cls._UNAVAILABLE is None:
            instance = cls.__new__(cls)
            instance.root = Path(".")
            instance.available = False
            instance.records_preloaded = False
            instance.manifest = {}
            instance.surface_index = {}
            instance.reading_index = {}
            instance.record_locator = {}
            instance.shard_cache_size = 1
            instance._shard_cache = OrderedDict()
            cls._UNAVAILABLE = instance
        return cls._UNAVAILABLE

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("record_count", 0))

    @property
    def version(self) -> str:
        versions = self.manifest.get("source_versions", [])
        return "+".join(versions) if versions else "0"

    def preload_records(self) -> None:
        """Expand every compact record shard before the server becomes ready."""
        if not self.available or self.records_preloaded:
            return
        shard_count = int(self.manifest.get("record_shards", 0))
        if shard_count < 1:
            raise ValueError("compiled open lexicon record_shards is missing")
        self.shard_cache_size = max(self.shard_cache_size, shard_count)
        loaded_records = 0
        for number in range(shard_count):
            loaded_records += len(self._load_shard(number))
        if loaded_records != self.record_count:
            raise ValueError(
                "compiled open lexicon preload count mismatch: "
                f"expected={self.record_count} actual={loaded_records}"
            )
        self.records_preloaded = True

    def _load_shard(self, number: int) -> dict[str, dict[str, Any]]:
        cached = self._shard_cache.get(number)
        if cached is not None:
            self._shard_cache.move_to_end(number)
            return cached

        path = self.root / "records" / f"records-{number:04d}.jsonl.gz"
        if not path.exists():
            raise FileNotFoundError(path)
        records: dict[str, dict[str, Any]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                item = json.loads(line)
                record_id = item.get("record_id")
                if not record_id:
                    raise ValueError(f"compiled record_id missing: {path}:{line_number}")
                records[record_id] = item
        self._shard_cache[number] = records
        self._shard_cache.move_to_end(number)
        while len(self._shard_cache) > self.shard_cache_size:
            self._shard_cache.popitem(last=False)
        return records

    def _record(self, record_id: str) -> dict[str, Any]:
        location = self.record_locator.get(record_id)
        if location is None:
            raise KeyError(f"compiled record locator missing: {record_id}")
        record = self._load_shard(int(location["shard"])).get(record_id)
        if record is None:
            raise KeyError(f"compiled record missing from shard: {record_id}")
        return record

    @staticmethod
    def _candidate(
        record: dict[str, Any],
        *,
        matched_text: str,
        match_type: str,
        restricted_to: list[str] | None = None,
        no_kanji: bool = False,
    ) -> LexicalCandidate:
        source = record.get("source") or {}
        return LexicalCandidate(
            record_id=record["record_id"],
            lemma=record["lemma"],
            matched_text=matched_text,
            match_type=match_type,
            readings=list(record.get("readings", [])),
            restricted_to=list(restricted_to or []),
            no_kanji=no_kanji,
            part_of_speech=list(record.get("part_of_speech", [])),
            domains=list(record.get("domains", [])),
            usage_labels=list(record.get("usage_labels", [])),
            source_dataset=source.get("dataset"),
            source_version=source.get("version"),
            source_license=source.get("license"),
        )

    def exact_lookup(
        self,
        text: str,
        *,
        match_type: str = "surface",
        max_candidates: int = 8,
    ) -> tuple[list[LexicalCandidate], int]:
        if not self.available or not text:
            return [], 0
        record_ids = self.surface_index.get(text, [])
        total = len(record_ids)
        selected = record_ids[: max(1, max_candidates)]
        return [
            self._candidate(
                self._record(record_id),
                matched_text=text,
                match_type=match_type,
            )
            for record_id in selected
        ], total

    def reading_lookup(
        self,
        reading: str,
        *,
        surface: str | None = None,
        normalized: str | None = None,
        max_candidates: int = 8,
    ) -> tuple[list[LexicalCandidate], int]:
        if not self.available or not reading:
            return [], 0
        allowed_surfaces = {value for value in (surface, normalized) if value}
        mappings: list[dict[str, Any]] = []
        lookup_reading = (
            reading
            if reading in self.reading_index
            else _katakana_to_hiragana(reading)
        )
        for mapping in self.reading_index.get(lookup_reading, []):
            restricted_to = set(mapping.get("restricted_to", []))
            if restricted_to and not restricted_to.intersection(allowed_surfaces):
                continue
            if mapping.get("no_kanji") and surface and _KANJI.search(surface):
                continue
            mappings.append(mapping)
        total = len(mappings)
        candidates = []
        for mapping in mappings[: max(1, max_candidates)]:
            candidates.append(
                self._candidate(
                    self._record(mapping["record_id"]),
                    matched_text=lookup_reading,
                    match_type="reading",
                    restricted_to=list(mapping.get("restricted_to", [])),
                    no_kanji=bool(mapping.get("no_kanji", False)),
                )
            )
        return candidates, total

    def lookup_token(
        self,
        token: Token,
        *,
        max_candidates: int = 8,
    ) -> Token:
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
                surface=token.surface,
                normalized=token.normalized,
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

    def annotate_tokens(
        self,
        tokens: list[Token],
        *,
        max_candidates: int = 8,
    ) -> list[Token]:
        if not self.available:
            return tokens
        return [
            self.lookup_token(token, max_candidates=max_candidates)
            for token in tokens
        ]
