#!/usr/bin/env python3
"""Measure how source-authored J-Ono evidence reduces review ambiguity.

This is an evidence measurement tool only. It never merges records, assigns POS,
judges meanings, approves records, or promotes runtime data.

Semantic-effectiveness metrics intentionally exclude example metadata from the
primary semantic score because source/file metadata can be unique without proving
meaning separation. Example metadata is reported separately as provenance-only
review evidence.
"""
from __future__ import annotations

import argparse
from itertools import combinations
import json
from pathlib import Path
import unicodedata
from typing import Any

EXPECTED_READING_UNRESOLVED_CLUSTERS = 124


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _stable_tuple(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({_norm(value) for value in values if _norm(value)}))


def _semantic_type_signature(evidence: dict[str, Any]) -> tuple[str, ...]:
    values = [
        _norm(evidence.get("semantic_type_code")),
        _norm(evidence.get("semantic_type_label")),
    ]
    return tuple(value for value in values if value)


def _refer_signature(evidence: dict[str, Any]) -> tuple[str, ...]:
    """Return only actual refer-path provenance, never local record identity.

    Resolved evidence also contains each record's own local source identity. Counting
    that would make every record look semantically distinguishable merely because its
    source_record_id is unique.
    """
    parts: list[str] = []
    refer = _norm(evidence.get("refer"))
    if refer:
        parts.append(f"refer={refer}")
    resolved = evidence.get("resolved_meaning_evidence")
    if isinstance(resolved, list):
        for item in resolved:
            if not isinstance(item, dict) or not bool(item.get("via_refer")):
                continue
            source_record_id = _norm(item.get("source_record_id"))
            source_definition_index = int(item.get("source_definition_index") or 0)
            if source_record_id or source_definition_index:
                parts.append(
                    f"resolved_refer={source_record_id}:{source_definition_index}"
                )
    return tuple(sorted(set(parts)))


def _example_metadata_signature(evidence: dict[str, Any]) -> tuple[str, ...]:
    examples = evidence.get("example_metadata")
    if not isinstance(examples, list):
        return ()
    parts: list[str] = []
    for item in examples:
        if not isinstance(item, dict):
            continue
        values = (
            _norm(item.get("source")),
            _norm(item.get("file")),
            _norm(item.get("display")),
            _norm(item.get("contributor")),
        )
        if any(values):
            parts.append("|".join(values))
    return tuple(sorted(set(parts)))


def _member_signatures(member: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    evidence = member.get("source_evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    equivalents = set(_stable_tuple(evidence.get("equivalents")))
    semantic_type = set(_semantic_type_signature(evidence))
    resolved = evidence.get("resolved_meaning_evidence")
    if isinstance(resolved, list):
        for item in resolved:
            if not isinstance(item, dict) or not bool(item.get("via_refer")):
                continue
            equivalents.update(_stable_tuple(item.get("equivalents")))
            semantic_type.update(_semantic_type_signature(item))

    return {
        "equivalents": tuple(sorted(equivalents)),
        "semantic_type": tuple(sorted(semantic_type)),
        "refer_provenance": _refer_signature(evidence),
        "example_metadata": _example_metadata_signature(evidence),
    }


def _pair_metrics(
    signatures: list[dict[str, tuple[str, ...]]],
    dimensions: tuple[str, ...],
) -> dict[str, int]:
    total_pairs = 0
    comparable_pairs = 0
    distinguished_pairs = 0
    availability_difference_pairs = 0
    for left, right in combinations(signatures, 2):
        total_pairs += 1
        shared_comparable_dimension = False
        differentiated = False
        availability_difference = False
        for dimension in dimensions:
            a = left[dimension]
            b = right[dimension]
            if bool(a) != bool(b):
                availability_difference = True
            if a and b:
                shared_comparable_dimension = True
                if a != b:
                    differentiated = True
        if shared_comparable_dimension:
            comparable_pairs += 1
        if differentiated:
            distinguished_pairs += 1
        if availability_difference:
            availability_difference_pairs += 1
    return {
        "total_pairs": total_pairs,
        "comparable_pairs": comparable_pairs,
        "distinguished_pairs": distinguished_pairs,
        "remaining_ambiguous_pairs": total_pairs - distinguished_pairs,
        "availability_difference_pairs": availability_difference_pairs,
    }


def measure_source_evidence_effectiveness(
    clusters_path: Path,
    *,
    expected_reading_unresolved: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    clusters = [
        json.loads(line)
        for line in Path(clusters_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unresolved = [
        cluster
        for cluster in clusters
        if int(cluster.get("reading_partition_count") or 0) == 1
    ]
    if expected_reading_unresolved is not None and len(unresolved) != expected_reading_unresolved:
        raise ValueError(
            "J_ONO_READING_UNRESOLVED_CLUSTER_COUNT_MISMATCH:"
            f"expected={expected_reading_unresolved}:actual={len(unresolved)}"
        )

    semantic_dimensions = ("equivalents", "semantic_type", "refer_provenance")
    all_dimensions = (*semantic_dimensions, "example_metadata")
    dimension_totals = {
        dimension: {
            "comparable_pairs": 0,
            "distinguished_pairs": 0,
            "availability_difference_pairs": 0,
            "clusters_with_distinguished_pairs": 0,
        }
        for dimension in all_dimensions
    }
    semantic_totals = {
        "total_pairs": 0,
        "comparable_pairs": 0,
        "distinguished_pairs": 0,
        "availability_difference_pairs": 0,
    }
    all_source_totals = dict(semantic_totals)
    details: list[dict[str, Any]] = []

    for cluster in unresolved:
        members = cluster.get("members")
        if not isinstance(members, list) or len(members) < 2:
            raise ValueError(f"J_ONO_SOURCE_EVIDENCE_CLUSTER_INVALID:{cluster.get('cluster_id')}")
        signatures = [_member_signatures(member) for member in members]

        dimension_metrics: dict[str, dict[str, int]] = {}
        for dimension in all_dimensions:
            metrics = _pair_metrics(signatures, (dimension,))
            dimension_metrics[dimension] = metrics
            dimension_totals[dimension]["comparable_pairs"] += metrics["comparable_pairs"]
            dimension_totals[dimension]["distinguished_pairs"] += metrics["distinguished_pairs"]
            dimension_totals[dimension]["availability_difference_pairs"] += metrics[
                "availability_difference_pairs"
            ]
            if metrics["distinguished_pairs"] > 0:
                dimension_totals[dimension]["clusters_with_distinguished_pairs"] += 1

        semantic = _pair_metrics(signatures, semantic_dimensions)
        all_source = _pair_metrics(signatures, all_dimensions)
        for key in semantic_totals:
            semantic_totals[key] += semantic[key]
            all_source_totals[key] += all_source[key]

        pair_review_evidence = []
        for left_index, right_index in combinations(range(len(members)), 2):
            left = signatures[left_index]
            right = signatures[right_index]
            distinguishing = [
                dimension for dimension in semantic_dimensions
                if left[dimension] and right[dimension]
                and left[dimension] != right[dimension]
            ]
            pair_review_evidence.append({
                "left_record_id": str(members[left_index].get("record_id") or ""),
                "right_record_id": str(members[right_index].get("record_id") or ""),
                "distinguishing_semantic_dimensions": distinguishing,
                "semantic_evidence_comparable": any(
                    left[dimension] and right[dimension]
                    for dimension in semantic_dimensions
                ),
                "source_signatures": {
                    "left": {key: list(value) for key, value in left.items()},
                    "right": {key: list(value) for key, value in right.items()},
                },
                "semantic_equivalence_judgement": "NOT_ADJUDICATED",
                "automatic_approval": False,
            })

        details.append(
            {
                "cluster_id": _norm(cluster.get("cluster_id")),
                "record_count": len(members),
                "record_ids": [str(member.get("record_id") or "") for member in members],
                "pair_review_evidence": pair_review_evidence,
                "baseline_ambiguous_pairs": semantic["total_pairs"],
                "semantic_evidence": semantic,
                "all_source_evidence": all_source,
                "provenance_only_extra_distinguished_pairs": max(
                    0, all_source["distinguished_pairs"] - semantic["distinguished_pairs"]
                ),
                "dimension_metrics": dimension_metrics,
                "automatic_merge": False,
                "automatic_meaning_judgement": False,
                "automatic_pos_fill": False,
                "runtime_promotion": False,
            }
        )

    total_pairs = semantic_totals["total_pairs"]
    report = {
        "status": "J_ONO_SOURCE_EVIDENCE_DISAMBIGUATION_EFFECTIVENESS_MEASURED",
        "cluster_count": len(clusters),
        "reading_unresolved_cluster_count": len(unresolved),
        "semantic_signal_dimensions": list(semantic_dimensions),
        "provenance_only_dimension": "example_metadata",
        "semantic_evidence": {
            **semantic_totals,
            "pair_reduction_ratio": round(
                semantic_totals["distinguished_pairs"] / total_pairs, 6
            ) if total_pairs else 0.0,
            "clusters_with_some_pair_reduction": sum(
                detail["semantic_evidence"]["distinguished_pairs"] > 0
                for detail in details
            ),
            "clusters_with_full_pair_reduction": sum(
                detail["semantic_evidence"]["distinguished_pairs"]
                == detail["baseline_ambiguous_pairs"]
                for detail in details
            ),
        },
        "all_source_evidence": {
            **all_source_totals,
            "pair_reduction_ratio": round(
                all_source_totals["distinguished_pairs"] / total_pairs, 6
            ) if total_pairs else 0.0,
            "clusters_with_some_pair_reduction": sum(
                detail["all_source_evidence"]["distinguished_pairs"] > 0
                for detail in details
            ),
            "clusters_with_full_pair_reduction": sum(
                detail["all_source_evidence"]["distinguished_pairs"]
                == detail["baseline_ambiguous_pairs"]
                for detail in details
            ),
        },
        "provenance_only_extra_distinguished_pairs": max(
            0,
            all_source_totals["distinguished_pairs"]
            - semantic_totals["distinguished_pairs"],
        ),
        "dimension_totals": dimension_totals,
        "interpretation_boundary": {
            "different_source_evidence_is_review_signal_not_semantic_truth": True,
            "refer_target_semantic_evidence_used": True,
            "example_metadata_excluded_from_primary_semantic_score": True,
            "missing_vs_present_evidence_not_counted_as_semantic_disambiguation": True,
            "automatic_merge": False,
            "automatic_meaning_judgement": False,
            "automatic_pos_fill": False,
            "automatic_approval": False,
            "runtime_promotion": False,
        },
    }
    return report, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clusters", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument(
        "--expected-reading-unresolved",
        type=int,
        default=EXPECTED_READING_UNRESOLVED_CLUSTERS,
    )
    args = parser.parse_args()

    report, details = measure_source_evidence_effectiveness(
        args.clusters,
        expected_reading_unresolved=args.expected_reading_unresolved,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with args.details.open("w", encoding="utf-8", newline="\n") as handle:
        for detail in details:
            handle.write(
                json.dumps(detail, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
