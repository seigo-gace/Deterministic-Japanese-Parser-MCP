from __future__ import annotations

import bz2
from dataclasses import asdict, dataclass, field
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import Iterable, Iterator, TextIO

SCHEMA_VERSION = "1.0.0"


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\u241f".join(normalize_text(item) for item in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_binary(path: Path):
    suffixes = [item.lower() for item in path.suffixes]
    if suffixes and suffixes[-1] == ".gz":
        return gzip.open(path, "rb")
    if suffixes and suffixes[-1] == ".bz2":
        return bz2.open(path, "rb")
    return path.open("rb")


def open_text(path: Path) -> TextIO:
    raw = open_binary(path)
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class SourceInfo:
    dataset: str
    version: str
    license: str
    source_id: str
    source_url: str | None = None
    source_sha256: str | None = None
    attribution: str | None = None

    def validate(self) -> None:
        for field_name in ("dataset", "version", "license", "source_id"):
            if not normalize_text(getattr(self, field_name)):
                raise ValueError(f"source.{field_name} must not be empty")


@dataclass
class LexiconRecord:
    record_id: str
    lemma: str
    language: str = "ja"
    readings: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)
    part_of_speech: list[str] = field(default_factory=list)
    lexical_category: str | None = None
    senses: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    antonyms: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    usage_labels: list[str] = field(default_factory=list)
    source: SourceInfo | None = None
    review_status: str = "unreviewed"
    notes: list[str] = field(default_factory=list)

    def normalized(self) -> "LexiconRecord":
        def unique(values: Iterable[str]) -> list[str]:
            output: list[str] = []
            for value in values:
                item = normalize_text(value)
                if item and item not in output:
                    output.append(item)
            return output

        self.lemma = normalize_text(self.lemma)
        self.readings = unique(self.readings)
        self.surfaces = unique([self.lemma, *self.surfaces])
        self.part_of_speech = unique(self.part_of_speech)
        self.synonyms = unique(self.synonyms)
        self.antonyms = unique(self.antonyms)
        self.related = unique(self.related)
        self.domains = unique(self.domains)
        self.usage_labels = unique(self.usage_labels)
        self.notes = unique(self.notes)
        normalized_senses: list[dict] = []
        seen_senses: set[str] = set()
        for raw in self.senses:
            gloss = normalize_text(str(raw.get("gloss", "")))
            if not gloss:
                continue
            key = json.dumps(
                {
                    "gloss": gloss,
                    "language": raw.get("language", "ja"),
                    "labels": sorted(unique(raw.get("labels", []))),
                    "domains": sorted(unique(raw.get("domains", []))),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key in seen_senses:
                continue
            seen_senses.add(key)
            normalized_senses.append({
                "sense_id": raw.get("sense_id") or stable_id(
                    "SENSE",
                    self.record_id,
                    gloss,
                ),
                "gloss": gloss,
                "language": raw.get("language", "ja"),
                "labels": unique(raw.get("labels", [])),
                "domains": unique(raw.get("domains", [])),
                "examples": unique(raw.get("examples", [])),
                "cross_references": unique(raw.get("cross_references", [])),
            })
        self.senses = normalized_senses
        normalized_forms: list[dict] = []
        seen_forms: set[tuple] = set()
        for raw in self.forms:
            representation = normalize_text(str(raw.get("representation", "")))
            if not representation:
                continue
            features = unique(raw.get("grammatical_features", []))
            key = (representation, tuple(features))
            if key in seen_forms:
                continue
            seen_forms.add(key)
            normalized_forms.append({
                "representation": representation,
                "grammatical_features": features,
                "reading": normalize_text(str(raw.get("reading", ""))) or None,
            })
        self.forms = normalized_forms
        return self

    def validate(self) -> None:
        self.normalized()
        if not self.record_id:
            raise ValueError("record_id must not be empty")
        if not self.lemma:
            raise ValueError(f"{self.record_id}: lemma must not be empty")
        if self.language != "ja":
            raise ValueError(f"{self.record_id}: only Japanese records are supported")
        if self.source is None:
            raise ValueError(f"{self.record_id}: source is required")
        self.source.validate()
        if self.review_status not in {
            "unreviewed",
            "needs_review",
            "approved",
            "rejected",
            "blocked",
        }:
            raise ValueError(
                f"{self.record_id}: invalid review_status={self.review_status}"
            )

    def to_dict(self) -> dict:
        self.validate()
        output = asdict(self)
        output["schema_version"] = SCHEMA_VERSION
        return output

    @classmethod
    def from_dict(cls, value: dict) -> "LexiconRecord":
        if value.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version={value.get('schema_version')}"
            )
        source_raw = value.get("source")
        source = SourceInfo(**source_raw) if source_raw else None
        record = cls(
            record_id=value["record_id"],
            lemma=value["lemma"],
            language=value.get("language", "ja"),
            readings=list(value.get("readings", [])),
            surfaces=list(value.get("surfaces", [])),
            part_of_speech=list(value.get("part_of_speech", [])),
            lexical_category=value.get("lexical_category"),
            senses=list(value.get("senses", [])),
            forms=list(value.get("forms", [])),
            synonyms=list(value.get("synonyms", [])),
            antonyms=list(value.get("antonyms", [])),
            related=list(value.get("related", [])),
            domains=list(value.get("domains", [])),
            usage_labels=list(value.get("usage_labels", [])),
            source=source,
            review_status=value.get("review_status", "unreviewed"),
            notes=list(value.get("notes", [])),
        )
        record.validate()
        return record


def write_jsonl(path: Path, records: Iterable[LexiconRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    record.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            count += 1
    return count


def read_jsonl(path: Path) -> Iterator[LexiconRecord]:
    with open_text(path) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                yield LexiconRecord.from_dict(value)
            except Exception as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc


def merge_records(records: Iterable[LexiconRecord]) -> list[LexiconRecord]:
    by_key: dict[tuple[str, tuple[str, ...]], LexiconRecord] = {}
    for item in records:
        item.validate()
        key = (item.lemma, tuple(sorted(item.readings)))
        current = by_key.get(key)
        if current is None:
            by_key[key] = item
            continue
        current.surfaces.extend(item.surfaces)
        current.part_of_speech.extend(item.part_of_speech)
        current.senses.extend(item.senses)
        current.forms.extend(item.forms)
        current.synonyms.extend(item.synonyms)
        current.antonyms.extend(item.antonyms)
        current.related.extend(item.related)
        current.domains.extend(item.domains)
        current.usage_labels.extend(item.usage_labels)
        current.notes.append(
            f"merged source record: {item.source.dataset}:{item.source.source_id}"
        )
        current.normalized()
    return sorted(by_key.values(), key=lambda item: (item.lemma, item.readings))
