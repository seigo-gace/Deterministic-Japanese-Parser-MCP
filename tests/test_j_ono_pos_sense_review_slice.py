from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    ROOT / "research/semantic_decisions/j_ono_pos_sense_review_slice_20261013.json"
)


def _read_evidence() -> dict:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_negative_sense_reviews_are_provenance_bound_and_never_approvals() -> None:
    payload = _read_evidence()
    source = payload["source"]
    assert source["repo"] == "seigo-gace/Deterministic-Japanese-Parser-MCP"
    assert source["pr"] == 56
    assert source["head"] == "d4e652718242c8c23129c65437e8230621817041"
    assert source["run_id"] == 38277024445
    assert source["artifact_id"] == 11759482589
    assert source["pr26_review_queue_sha256"] == (
        "29afe10d8d7f2696ff5bcbee9aefedcd2e438e4ff76c138386bc8504d606db17"
    )

    pairs = payload["reviewed_pairs"]
    assert len(pairs) == 19
    ids = [(row["jono_record_id"], row["jmdict_record_id"]) for row in pairs]
    assert len(set(ids)) == len(ids)
    for row in pairs:
        assert row["jono_record_id"].startswith("FROZEN-j-ono-definitions-")
        assert row["jmdict_record_id"].startswith("JMD-")
        assert row["source_meaning"].strip()
        assert row["jmdict_gloss"].strip()
        assert row["review_result"] == "SENSE_NON_EQUIVALENT"
        assert row["lexical_pos_approval"] is False
        assert row["rationale"].strip()

    assert payload["review_scope"] == "sense-equivalence-negative-examples"
    assert payload["remaining_pairs_status"] == "NOT_REVIEWED"
    assert payload["automatic_approval"] is False
    assert payload["runtime_promotion"] is False
