from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import LexiconRecord, SourceInfo


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPILER = _load_script(
    "compile_open_lexicon_runtime",
    ROOT / "tools/compile_open_lexicon_runtime.py",
)
VALIDATOR = _load_script(
    "validate_compiled_open_lexicon",
    ROOT / "tools/validate_compiled_open_lexicon.py",
)


def _record(
    record_id: str,
    lemma: str,
    surfaces: list[str],
    readings: list[str],
    *,
    pos: str = "noun",
    domain: str = "general",
) -> LexiconRecord:
    return LexiconRecord(
        record_id=record_id,
        lemma=lemma,
        readings=readings,
        reading_mappings=[
            {
                "reading": reading,
                "restricted_to": surfaces,
                "no_kanji": False,
            }
            for reading in readings
        ],
        surfaces=surfaces,
        part_of_speech=[pos],
        domains=[domain],
        source=SourceInfo(
            dataset="JMdict",
            version="fixture",
            license="CC-BY-SA-4.0",
            source_id=record_id,
            source_url="https://www.edrdg.org/jmdict/j_jmdict.html",
            source_sha256="a" * 64,
            attribution="JMdict fixture",
        ),
        review_status="approved",
    )


def test_compile_and_validate_runtime_indexes(tmp_path: Path):
    source_root = tmp_path / "lexicon.d/cc-by-sa"
    source_root.mkdir(parents=True)
    records = [
        _record("R1", "橋", ["橋"], ["はし"]),
        _record("R2", "箸", ["箸"], ["はし"], domain="food"),
        _record("R3", "生", ["生"], ["なま"]),
        _record("R4", "生もの", ["生もの", "生"], ["なまもの"]),
    ]
    source_path = source_root / "fixture-0001.jsonl.gz"
    with gzip.open(source_path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
                + "\n"
            )

    output_root = tmp_path / "compiled/open_lexicon"
    manifest = COMPILER.compile_runtime(
        input_root=tmp_path / "lexicon.d",
        output_root=output_root,
        expected_records=4,
        record_shard_size=100,
    )
    report = VALIDATOR.validate(output_root, expected_records=4)

    assert manifest["record_count"] == 4
    assert manifest["semantic_auto_promotion"] is False
    assert manifest["external_action_auto_promotion"] is False
    assert report["status"] == "PASS", report

    with gzip.open(
        output_root / "indexes/canonical-groups.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        canonical = json.load(handle)
    with gzip.open(
        output_root / "indexes/reading-index.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        readings = json.load(handle)
    with gzip.open(
        output_root / "indexes/homograph-index.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        homographs = json.load(handle)

    assert "はし" in readings
    assert all("はし" not in members for members in canonical.values())
    assert homographs["生"] == ["R3", "R4"]
