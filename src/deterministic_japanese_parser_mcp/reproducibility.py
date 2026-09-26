from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from .engine import ParserEngine
from .models import AnalyzeRequest
from .normalizer import normalize_with_map
from .version import VERSION

_INSTALLED = False
SEMANTIC_HASH_V2_ALGORITHM = "sha256-semantic-runtime-v2"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dictionary_snapshot(engine: ParserEngine) -> dict[str, Any]:
    synonyms = {
        key: value
        for key, value in engine.bundle.synonyms.items()
        if key != "_cache_key"
    }
    open_lexicon_manifest = (
        engine.bundle.open_lexicon.manifest
        if engine.bundle.open_lexicon.available
        else {}
    )
    return {
        "rules": engine.bundle.rules,
        "metaphors": engine.bundle.metaphors,
        "templates": engine.bundle.templates,
        "lexicon": engine.bundle.lexicon,
        "synonyms": synonyms,
        "open_lexicon_manifest": open_lexicon_manifest,
    }


def _semantic_runtime_snapshot(engine: ParserEngine) -> dict[str, Any]:
    return {
        "available": bool(engine.semantic_data.available),
        "manifest": engine.semantic_data.manifest,
    }


def _language_feature_asset(engine: ParserEngine) -> str:
    runtime = getattr(engine, "language_features", None)
    if runtime is None:
        return "unavailable"
    return str(getattr(runtime, "asset_sha256", "unavailable") or "unavailable")


def _runtime_snapshot(engine: ParserEngine) -> dict[str, str]:
    return {
        "engine_versions_sha256": _canonical_sha256(VERSION),
        "dictionary_snapshot_sha256": _canonical_sha256(_dictionary_snapshot(engine)),
        "semantic_runtime_sha256": _canonical_sha256(_semantic_runtime_snapshot(engine)),
        "language_feature_asset_sha256": _language_feature_asset(engine),
    }


def semantic_hash_v2(
    *,
    normalized_text: str,
    semantic_hash_v1: str,
    runtime_snapshot: dict[str, str],
) -> str:
    """Bind semantic graph identity to the deterministic runtime snapshot.

    `semantic_hash` remains the MeaningGraph identity for backward compatibility.
    This v2 digest answers a different question: whether the same normalized
    input and graph identity were produced under the same deterministic runtime
    assets and version set.
    """
    return _canonical_sha256({
        "algorithm": SEMANTIC_HASH_V2_ALGORITHM,
        "normalized_text": normalized_text,
        "semantic_hash_v1": semantic_hash_v1,
        **runtime_snapshot,
    })


def install_reproducibility_fingerprint() -> None:
    """Add v2 reproducibility evidence without changing semantic_hash v1."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_init: Callable = ParserEngine.__init__
    original_analyze: Callable = ParserEngine.analyze

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.reproducibility_snapshot = _runtime_snapshot(self)

    def analyze(self, request: AnalyzeRequest, *args, **kwargs):
        response = original_analyze(self, request, *args, **kwargs)
        normalized_text, _ = normalize_with_map(request.original_text)
        versions = dict(response.versions)
        versions.update(self.reproducibility_snapshot)
        versions["semantic_hash_v1"] = response.meaning_graph.semantic_hash
        versions["semantic_hash_v2_algorithm"] = SEMANTIC_HASH_V2_ALGORITHM
        versions["semantic_hash_v2"] = semantic_hash_v2(
            normalized_text=normalized_text,
            semantic_hash_v1=response.meaning_graph.semantic_hash,
            runtime_snapshot=self.reproducibility_snapshot,
        )
        # Always expose the language feature asset, even when the input matched
        # no feature and the language-feature wrapper returned early.
        versions["language_feature_asset"] = self.reproducibility_snapshot[
            "language_feature_asset_sha256"
        ]
        return response.model_copy(update={"versions": versions})

    ParserEngine.__init__ = __init__
    ParserEngine.analyze = analyze
    _INSTALLED = True
