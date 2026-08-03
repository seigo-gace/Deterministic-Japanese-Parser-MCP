#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from deterministic_japanese_parser_mcp import AnalyzeRequest
from deterministic_japanese_parser_mcp.server import prewarm


def semantic_hash(response) -> str:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    engine = prewarm()
    settings = engine.settings
    request = AnalyzeRequest(
        original_text="UIは残せ。APIだけ変更しろ。",
        execution_mode="external_action",
        deadline_ms=60000,
    )
    hashes = {semantic_hash(engine.analyze(request)) for _ in range(20)}
    rule_count = len(engine.rules.compiled)
    metaphor_count = len(engine.metaphors.entries)
    template_count = len(engine.bundle.templates.get("templates", []))
    synonym_count = len(engine.bundle.synonyms.get("groups", {}))

    report = {
        "status": "READY",
        "python": sys.version,
        "tokenizer_backend": engine.tokenizer.backend,
        "system_dictionary_dir": str(settings.system_dict_dir),
        "user_dictionary_dir": str(settings.user_dict_dir),
        "system_dictionary_exists": settings.system_dict_dir.is_dir(),
        "user_dictionary_exists": settings.user_dict_dir.is_dir(),
        "rule_count": rule_count,
        "metaphor_count": metaphor_count,
        "template_count": template_count,
        "synonym_group_count": synonym_count,
        "deterministic_hash_count": len(hashes),
        "semantic_hash": next(iter(hashes)) if hashes else None,
    }

    failures: list[str] = []
    if engine.tokenizer.backend != "sudachi-core":
        failures.append(f"production tokenizer unavailable: {engine.tokenizer.backend}")
    for path_name, path in (
        ("system dictionary", settings.system_dict_dir),
        ("user dictionary", settings.user_dict_dir),
    ):
        if not Path(path).is_dir():
            failures.append(f"{path_name} missing: {path}")
    if rule_count < 150:
        failures.append(f"rule count below contract: {rule_count}")
    if metaphor_count < 152:
        failures.append(f"metaphor count below contract: {metaphor_count}")
    if template_count < 29:
        failures.append(f"template count below contract: {template_count}")
    if synonym_count < 20:
        failures.append(f"synonym group count below contract: {synonym_count}")
    if len(hashes) != 1:
        failures.append(f"non-deterministic responses detected: {len(hashes)} hashes")

    if failures:
        report["status"] = "FAILED"
        report["failures"] = failures
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
