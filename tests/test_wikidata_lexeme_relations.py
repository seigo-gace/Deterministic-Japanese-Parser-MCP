from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.importers.wikidata_lexemes import import_dump


def test_wikidata_sense_ids_are_not_promoted_as_surface_synonyms():
    record = import_dump(
        ROOT / "tests/fixtures/dictionary_supply/wikidata-lexemes.json",
        source_version="fixture-1",
    )[0]
    assert record.synonyms == []
    assert record.antonyms == []
    assert record.senses[0]["cross_references"] == [
        "synonym_sense:L101-S1",
        "antonym_sense:L102-S1",
    ]
    assert record.related == ["derived_from_lexeme:L099"]
