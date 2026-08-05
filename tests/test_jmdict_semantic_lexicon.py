from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_jmdict_semantic_lexicon import build_semantic_lexicon  # noqa: E402
from unified_semantic_data.pipeline import build_review_assets  # noqa: E402


def test_jmdict_semantics_become_review_candidates(tmp_path: Path) -> None:
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<JMdict>
  <entry>
    <ent_seq>1000010</ent_seq>
    <k_ele><keb>明るい</keb></k_ele>
    <r_ele><reb>あかるい</reb></r_ele>
    <sense>
      <pos>adjective (keiyoushi)</pos>
      <field>physics</field>
      <misc>commonly used</misc>
      <gloss>bright</gloss>
      <gloss>well-lit</gloss>
    </sense>
    <sense>
      <pos>adjective (keiyoushi)</pos>
      <gloss>cheerful</gloss>
      <xref>朗らか</xref>
    </sense>
  </entry>
</JMdict>
'''.encode("utf-8")
    source_path = tmp_path / "JMdict_e.gz"
    with gzip.open(source_path, "wb") as handle:
        handle.write(xml)
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()

    lexicon_root = tmp_path / "lexicon"
    lexicon_root.mkdir()
    record = {
        "record_id": "JMD-FIXTURE-001",
        "lemma": "明るい",
        "surfaces": ["明るい"],
        "readings": ["あかるい"],
        "part_of_speech": ["adjective (keiyoushi)"],
        "source": {
            "dataset": "JMdict",
            "version": "fixture-lexical",
            "license": "CC-BY-SA-4.0",
            "source_id": "1000010",
            "source_url": "https://example.invalid/JMdict_e.gz",
            "source_sha256": "a" * 64,
            "attribution": "EDRDG",
        },
        "review_status": "approved",
    }
    (lexicon_root / "part.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    enriched_root = tmp_path / "enriched"
    result = build_semantic_lexicon(
        input_path=source_path,
        lexicon_root=lexicon_root,
        output_root=enriched_root,
        report_path=tmp_path / "report.json",
        source_version="fixture-semantic",
        expected_sha256=source_sha,
        expected_records=1,
        shard_size=100,
    )
    assert result["record_count"] == 1
    assert result["meaning_candidate_count"] == 2

    with gzip.open(
        enriched_root / "jmdict-semantic-0000.jsonl.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        enriched = json.loads(handle.readline())
    assert enriched["review_status"] == "needs-evidence"
    assert [item["label"] for item in enriched["meaning_candidates"]] == [
        "bright",
        "cheerful",
    ]
    assert all(
        item["review_status"] == "needs-evidence"
        for item in enriched["meaning_candidates"]
    )

    review_root = tmp_path / "review"
    manifest = build_review_assets(
        open_lexicon_root=enriched_root,
        context_root=tmp_path / "context",
        pack_roots=[],
        output_root=review_root,
        system_root=tmp_path / "system",
    )
    assert manifest["total_records"] == 1
    assert manifest["runtime_eligible_records"] == 0
    reviewed = json.loads(
        (review_root / "review-records.jsonl").read_text(encoding="utf-8")
    )
    assert len(reviewed["meaning_candidates"]) == 2
    assert reviewed["review_status"] == "needs-evidence"
