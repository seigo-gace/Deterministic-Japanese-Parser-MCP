from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pos_evidence_uses_same_rebuilt_identity_as_queue() -> None:
    """The two adjacent stages must use the same rebuilt adapter ID space."""
    workflow = (ROOT / ".github/workflows/j-ono-data-quality-audit.yml").read_text(encoding="utf-8")
    pos_stage = workflow.split("      - name: Compare J-Ono POS evidence", 1)[-1]
    # Scope the producer by its canonical output, not the unrelated earlier audit.
    producer = workflow.split('with Path("work/j-ono-pos-evidence.jsonl").open', 1)[0]
    producer = producer.rsplit('for line in Path(', 1)[-1]
    assert producer.startswith('"work/j-ono-rebuilt-source-adapter.jsonl")')
    consumer = workflow.split("      - name: Build review-only J-Ono POS evidence queue", 1)[1]
    consumer = consumer.split("      - name: Restore immutable PR 26 semantic Review Queue", 1)[0]
    assert "--records work/j-ono-rebuilt-source-adapter.jsonl" in consumer
    assert "--pos-evidence work/j-ono-pos-evidence.jsonl" in consumer


def test_jmdict_sense_count_is_pinned_to_verified_review_input() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-data-quality-audit.yml").read_text(encoding="utf-8")
    stage = workflow.split("      - name: Build review-only J-Ono JMdict Sense/POS alignment evidence", 1)[1]
    stage = stage.split("      - name: Verify no automatic semantic judgement or promotion", 1)[0]
    assert 'report["review_record_count"] != 94' in stage
    assert 'report["distinct_jmdict_record_count"] != 64' in stage
    assert 'report["jmdict_sense_candidate_count"] != 151' in stage
    assert "J_ONO_POS_ALIGNMENT_PREMATURE_JUDGEMENT" in stage
    assert "J_ONO_POS_ALIGNMENT_PR26_DIGEST_MISMATCH" in stage
