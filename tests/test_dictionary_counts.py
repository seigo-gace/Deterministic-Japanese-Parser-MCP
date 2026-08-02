import json, yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_initial_data_volume():
    metaphors=sum(
        len((json.loads(path.read_text(encoding="utf-8")) or {}).get("entries", []))
        for path in (ROOT/"dictionaries/system/metaphors").glob("*.json")
    )
    rules=0
    for p in (ROOT/"dictionaries/system/rules").glob("*.yaml"):
        rules += sum(len(x) for x in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("intents",{}).values())
    gold=sum(len(json.loads(p.read_text(encoding="utf-8"))["cases"]) for p in (ROOT/"tests/gold").glob("*.json"))
    assert metaphors >= 100
    assert rules >= 120
    assert gold >= 120
