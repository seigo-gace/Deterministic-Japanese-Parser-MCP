from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class PurposePayload:
    kind: str
    consumer: str
    key: str
    value: str
    semantic_authority: bool = False

_PROVENANCE = {
    "xml_path", "xml_tag", "base", "eng_sentence_id",
    "transcription", "skk_key", "indices", "更新日",
}

_EDUCATION = {
    "KNOW", "LISTEN", "READ", "SPEAK", "WRITE",
    "KNOW_age", "LISTEN_age", "READ_age", "SPEAK_age", "WRITE_age",
    "KNOW_grade", "LISTEN_grade", "READ_grade",
    "SPEAK_grade", "WRITE_grade",
}

def _split(raw: str) -> tuple[str, str]:
    positions = [i for i in (raw.find(":"), raw.find("=")) if i >= 0]
    if not positions:
        return "", raw
    i = min(positions)
    return raw[:i], raw[i + 1:]

def classify_payload(field: str, raw: str) -> PurposePayload:
    key, value = _split(str(raw))

    if not key:
        return PurposePayload("unknown", "none", "", value)

    if key in _PROVENANCE:
        return PurposePayload("provenance", "evidence_graph", key, value)

    if key in {"frequency", "pmw", "familiarity"}:
        return PurposePayload("ranking", "sense_ranker", key, value)

    if key == "source_occurrences":
        return PurposePayload("evidence_weight", "evidence_graph", key, value)

    if key in _EDUCATION:
        return PurposePayload("education_profile", "lexical_metadata", key, value)

    if key.startswith("writer_"):
        return PurposePayload("sentiment_profile", "semantic_data_runtime", key, value)

    if key == "acceptability":
        return PurposePayload("syntax_evidence", "grammar_kernel", key, value)

    if key == "dependency" and field == "relations":
        return PurposePayload("syntax_relation", "grammar_kernel", key, value)

    if key == "classification" and field == "relations":
        return PurposePayload("semantic_class", "sense_resolver", key, value)

    if key == "contrast" and field == "relations":
        return PurposePayload("lexical_relation", "sense_resolver", key, value)

    if key == "pronunciation" and field == "relations":
        return PurposePayload("reading_evidence", "reading_runtime", key, value)

    if key == "concept" and field == "relations":
        return PurposePayload("concept_link", "evidence_graph", key, value)

    if key in {"BUSHU", "KUNYOMI", "ONYOMI"}:
        return PurposePayload("lexical_metadata", "lexical_metadata", key, value)

    return PurposePayload("unknown", "none", key, value)
