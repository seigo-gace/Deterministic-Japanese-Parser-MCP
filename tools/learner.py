#!/usr/bin/env python3
"""Build a deterministic review bundle from open lexicons and unresolved logs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for item in (ROOT / "src", TOOLS_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.dictionaries import DictionaryBundle
from deterministic_japanese_parser_mcp.config import SETTINGS
from dictionary_supply.common import (
    LexiconRecord,
    SourceInfo,
    read_jsonl,
    stable_id,
)
from dictionary_supply.proposals import build_proposals, write_bundle


def existing_indexes(bundle: DictionaryBundle) -> tuple[set[str], set[str], set[str]]:
    metaphor_surfaces: set[str] = set()
    for item in bundle.metaphors.get("entries", []):
        metaphor_surfaces.add(item["expression"])
        metaphor_surfaces.update(item.get("aliases", []))
    rule_patterns = {
        item["pattern"]
        for items in bundle.rules.get("intents", {}).values()
        for item in items
    }
    synonym_surfaces = {
        value
        for canonical, values in bundle.synonyms.get("groups", {}).items()
        for value in [canonical, *(values or [])]
    }
    return metaphor_surfaces, rule_patterns, synonym_surfaces


def records_from_logs(paths: list[Path]) -> list[LexiconRecord]:
    engine = ParserEngine()
    output: list[LexiconRecord] = []
    seen: set[str] = set()
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("overall_status") not in {"PARTIAL", "FAILED"}:
                continue
            text = str(row.get("original_text", "")).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            response = engine.analyze(AnalyzeRequest(
                original_text=text,
                deadline_ms=60000,
            ))
            tokens = response.tokens
            readings = [
                token.normalized
                for token in tokens
                if token.normalized and token.normalized != token.surface
            ]
            pos = sorted({
                item
                for token in tokens
                for item in token.pos[:1]
                if item and item != "*"
            })
            output.append(LexiconRecord(
                record_id=stable_id("LOG", str(path), str(line_number), text),
                lemma=text,
                readings=readings,
                surfaces=[text],
                part_of_speech=pos,
                senses=[],
                source=SourceInfo(
                    dataset="Deterministic Japanese Parser unresolved log",
                    version="runtime-log-v1",
                    license="PRIVATE-REVIEW-ONLY",
                    source_id=f"{path}:{line_number}",
                    source_sha256=None,
                    attribution="Local application input log after secret masking",
                ),
                review_status="needs_review",
                notes=[
                    f"overall_status={row.get('overall_status')}",
                    f"ambiguities={len(row.get('ambiguities', []))}",
                    f"unsupported={len(row.get('unsupported_elements', []))}",
                ],
            ).normalized())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Combine imported open dictionary records and unresolved runtime logs "
            "into one review-only proposal bundle."
        )
    )
    parser.add_argument(
        "--lexicon",
        type=Path,
        action="append",
        default=[],
        help="JSONL produced by tools/dictionary_supply/importers/*",
    )
    parser.add_argument(
        "--log",
        type=Path,
        action="append",
        default=[],
        help="Masked parser JSONL log",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("proposals/dictionary-review.yaml"),
    )
    args = parser.parse_args()
    if not args.lexicon and not args.log:
        parser.error("at least one --lexicon or --log is required")

    records: list[LexiconRecord] = []
    for path in args.lexicon:
        records.extend(read_jsonl(path))
    records.extend(records_from_logs(args.log))

    bundle = DictionaryBundle(
        SETTINGS.system_dict_dir,
        SETTINGS.user_dict_dir,
    )
    metaphors, patterns, synonyms = existing_indexes(bundle)
    proposals = build_proposals(
        records,
        existing_metaphor_surfaces=metaphors,
        existing_rule_patterns=patterns,
        existing_synonym_surfaces=synonyms,
    )
    payload = write_bundle(
        args.out,
        batch_id=args.batch_id,
        proposals=proposals,
        input_files=[*args.lexicon, *args.log],
    )
    print(
        "LEARNER OK: "
        f"records={len(records)} proposals={len(proposals)} "
        f"counts={yaml.safe_dump(payload['counts'], allow_unicode=True).strip()} "
        f"output={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
