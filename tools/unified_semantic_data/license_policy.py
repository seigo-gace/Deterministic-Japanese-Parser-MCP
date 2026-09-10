"""Conservative data-license classification for the MCP canonical dictionary.

The classifier is intentionally narrow. It does not provide legal advice and it does not
rewrite upstream licenses. Its purpose is to prevent obviously non-commercial,
no-derivatives, reference-only, unknown, or pending source data from being silently
compiled into the default public-distributable canonical dictionary. Exact upstream
license text remains evidence.
"""
from __future__ import annotations

import re
from typing import Any


DISTRIBUTION_TIERS = {
    "permissive",
    "sharealike",
    "noncommercial",
    "reference-only",
    "blocked-unknown",
}


def _fold(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\s+", " ", text)
    return text


def classify_data_license(value: Any) -> dict[str, Any]:
    """Classify one declared data-license string without rewriting it."""
    raw = str(value or "").strip()
    folded = _fold(raw)
    if not folded or any(
        marker in folded
        for marker in (
            "unknown",
            "unlicensed",
            "pending",
            "tbd",
            "確認中",
            "license required",
            "license-required",
        )
    ):
        return {
            "license": raw,
            "tier": "blocked-unknown",
            "public_dictionary_allowed": False,
            "reason": "license-declaration-required",
        }

    # Descriptions such as "project reference" or "reference only" are not
    # redistribution licences. Preserve them internally, but do not ship them.
    if any(
        marker in folded
        for marker in (
            "reference-only",
            "reference only",
            "project reference",
            "internal reference",
            "参照専用",
            "参考資料",
        )
    ):
        return {
            "license": raw,
            "tier": "reference-only",
            "public_dictionary_allowed": False,
            "reason": "reference-only-source",
        }

    # NoDerivatives material must not be transformed into the public dictionary.
    if any(
        marker in folded
        for marker in (
            "by-nd",
            "by nd",
            "no derivatives",
            "noderivatives",
            "改変禁止",
        )
    ):
        return {
            "license": raw,
            "tier": "reference-only",
            "public_dictionary_allowed": False,
            "reason": "no-derivatives-source",
        }

    # NonCommercial evidence can remain in the internal master dictionary, but
    # it is excluded from the default public-distributable view.
    if any(
        marker in folded
        for marker in (
            "by-nc",
            "by nc",
            "noncommercial",
            "non-commercial",
            "非営利",
        )
    ):
        return {
            "license": raw,
            "tier": "noncommercial",
            "public_dictionary_allowed": False,
            "reason": "noncommercial-source",
        }

    # ShareAlike material remains eligible only as a separately tracked data
    # licence tier. The classifier never relabels it as MIT/permissive.
    if any(
        marker in folded
        for marker in (
            "by-sa",
            "by sa",
            "sharealike",
            "share alike",
            "継承",
        )
    ):
        return {
            "license": raw,
            "tier": "sharealike",
            "public_dictionary_allowed": True,
            "reason": "sharealike-data-license-preserved",
        }

    return {
        "license": raw,
        "tier": "permissive",
        "public_dictionary_allowed": True,
        "reason": "declared-license-preserved",
    }


def source_distribution_allowed(source: dict[str, Any]) -> bool:
    return classify_data_license((source or {}).get("license"))[
        "public_dictionary_allowed"
    ] is True
