import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _metaphor_documents() -> list[tuple[Path, dict]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((ROOT / "dictionaries/system/metaphors").glob("*.json"))
        if path.name != "manifest.json"
    ]


def _rule_documents() -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((ROOT / "dictionaries/system/rules").glob("*.yaml"))
    ]


def test_expanded_dictionary_volume_is_exact():
    metaphor_docs = _metaphor_documents()
    metaphors = sum(len(doc.get("entries", [])) for _, doc in metaphor_docs)
    rules = sum(
        len(items)
        for doc in _rule_documents()
        for items in doc.get("intents", {}).values()
    )
    gold = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["cases"])
        for path in sorted((ROOT / "tests/gold").glob("*.json"))
    )
    synonym_doc = yaml.safe_load(
        (ROOT / "dictionaries/system/synonyms.yaml").read_text(encoding="utf-8")
    )
    template_doc = yaml.safe_load(
        (ROOT / "dictionaries/system/task_templates.yaml").read_text(encoding="utf-8")
    )
    templates = template_doc["templates"]
    workflows = [item for item in templates if item.get("intent") == "workflow"]

    assert metaphors == 200
    assert rules == 213
    assert gold == 271
    assert len(synonym_doc["groups"]) == 40
    assert len(templates) == 39
    assert len(workflows) == 18


def test_metaphor_manifest_matches_every_category_file():
    manifest = json.loads(
        (ROOT / "dictionaries/system/metaphors/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    actual = {
        path.name: len(doc.get("entries", []))
        for path, doc in _metaphor_documents()
    }
    assert manifest["dictionary_version"] == "1.1.0"
    assert manifest["metaphor_entries"] == sum(actual.values())
    assert manifest["category_files"] == actual


def test_all_twenty_one_intents_received_common_usage_expansion():
    expansion = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/rules/common_usage_expansion.yaml"
        ).read_text(encoding="utf-8")
    )
    intents = expansion["intents"]
    assert len(intents) == 21
    assert all(len(items) == 3 for items in intents.values())
    assert sum(len(items) for items in intents.values()) == 63


def test_new_workflow_ids_are_present_and_ordered():
    doc = yaml.safe_load(
        (ROOT / "dictionaries/system/task_templates.yaml").read_text(
            encoding="utf-8"
        )
    )
    workflows = {
        item["id"]: item
        for item in doc["templates"]
        if item.get("intent") == "workflow"
    }
    expected = {
        "WF-REQUIREMENT_ANALYSIS",
        "WF-BUG_REPRODUCTION",
        "WF-ROOT_CAUSE_ANALYSIS",
        "WF-DOCUMENT_REVISION",
        "WF-DATA-MIGRATION",
        "WF-DEPENDENCY-UPGRADE",
        "WF-ACCOUNT-AUTH-CHANGE",
        "WF-UI-ACCESSIBILITY-REVIEW",
        "WF-KNOWLEDGE-BASE-UPDATE",
        "WF-ROLLBACK-RECOVERY",
    }
    assert expected <= set(workflows)
    for workflow_id in expected:
        orders = [step["order"] for step in workflows[workflow_id]["steps"]]
        assert orders == list(range(1, len(orders) + 1))
