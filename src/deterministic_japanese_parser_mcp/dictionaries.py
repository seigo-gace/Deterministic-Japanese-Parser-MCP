from pathlib import Path
import json

import yaml


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml_set(path: Path) -> dict:
    if path.is_file():
        return _load_yaml(path)
    docs = [_load_yaml(item) for item in sorted(path.glob("*.yaml"))]
    output = {"version": "0", "timeout_ms": 25, "intents": {}}
    for doc in docs:
        output["version"] = doc.get("version", output["version"])
        output["timeout_ms"] = doc.get("timeout_ms", output["timeout_ms"])
        for intent, items in doc.get("intents", {}).items():
            output["intents"].setdefault(intent, []).extend(items or [])
    return output


def _load_json_set(path: Path) -> dict:
    if path.is_file():
        return _load_json(path)

    control_path = path / "overrides.json"
    controls = _load_json(control_path) if control_path.exists() else {}
    by_expression: dict[str, dict] = {}
    version = "0"

    for item_path in sorted(path.glob("*.json")):
        if item_path.name in {"manifest.json", "overrides.json"}:
            continue
        doc = _load_json(item_path)
        version = doc.get("version", version)
        for item in doc.get("entries", []):
            by_expression[item["expression"]] = item

    for expression, patterns in controls.get("pattern_overrides", {}).items():
        if expression not in by_expression:
            raise ValueError(
                f"metaphor pattern override target is missing: {expression}"
            )
        item = dict(by_expression[expression])
        merged_patterns = list(item.get("patterns", []))
        for pattern in patterns:
            if pattern not in merged_patterns:
                merged_patterns.append(pattern)
        item["patterns"] = merged_patterns
        by_expression[expression] = item

    for expression in controls.get("disabled_expressions", []):
        by_expression.pop(expression, None)

    for item in controls.get("replacement_entries", []):
        by_expression[item["expression"]] = item

    return {
        "version": controls.get("version", version),
        "entries": list(by_expression.values()),
        "controls": controls,
    }


def _load_yaml_fragments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [_load_yaml(item) for item in sorted(path.glob("*.yaml"))]


def _load_template_set(primary: Path, fragments: Path) -> dict:
    docs: list[dict] = []
    if primary.is_file():
        docs.append(_load_yaml(primary))
    docs.extend(_load_yaml_fragments(fragments))
    output = {"version": "0", "templates": []}
    for doc in docs:
        output["version"] = doc.get("version", output["version"])
        output["templates"].extend(doc.get("templates", []) or [])
    return output


def _load_synonym_set(primary: Path, fragments: Path) -> dict:
    docs: list[dict] = []
    if primary.is_file():
        docs.append(_load_yaml(primary))
    docs.extend(_load_yaml_fragments(fragments))
    output: dict = {"version": "0", "groups": {}}
    for doc in docs:
        output["version"] = doc.get("version", output["version"])
        for canonical, values in doc.get("groups", {}).items():
            bucket = output["groups"].setdefault(canonical, [])
            for value in [canonical, *(values or [])]:
                if value and value not in bucket:
                    bucket.append(value)
    return output


def merge_rule_docs(system: dict, user: dict) -> dict:
    merged = {
        "version": system.get("version", "0"),
        "timeout_ms": system.get("timeout_ms", 25),
        "intents": {},
    }
    for source in (system, user):
        for intent, items in source.get("intents", {}).items():
            merged["intents"].setdefault(intent, []).extend(items or [])
    return merged


def merge_metaphors(system: dict, user: dict) -> dict:
    by_expression: dict[str, dict] = {}
    for source in (system, user):
        for item in source.get("entries", []):
            by_expression[item["expression"]] = item
    return {
        "version": system.get("version", "0"),
        "entries": list(by_expression.values()),
    }


def merge_templates(system: dict, user: dict) -> dict:
    by_id: dict[str, dict] = {}
    for source in (system, user):
        for item in source.get("templates", []):
            by_id[item["id"]] = item
    return {
        "version": system.get("version", "0"),
        "templates": list(by_id.values()),
    }


def merge_synonyms(system: dict, user: dict) -> dict:
    groups: dict[str, list[str]] = {}
    for source in (system, user):
        for canonical, values in source.get("groups", {}).items():
            bucket = groups.setdefault(canonical, [])
            for value in [canonical, *(values or [])]:
                if value and value not in bucket:
                    bucket.append(value)
    return {"version": system.get("version", "0"), "groups": groups}


class DictionaryBundle:
    def __init__(self, system_dir: Path, user_dir: Path):
        system_rules = _load_yaml_set(system_dir / "rules")
        system_metaphors = _load_json_set(system_dir / "metaphors")
        system_templates = _load_template_set(
            system_dir / "task_templates.yaml",
            system_dir / "task_templates.d",
        )
        system_synonyms = _load_synonym_set(
            system_dir / "synonyms.yaml",
            system_dir / "synonyms.d",
        )
        self.rules = merge_rule_docs(
            system_rules,
            _load_yaml(user_dir / "rules.yaml"),
        )
        self.metaphors = merge_metaphors(
            system_metaphors,
            _load_json(user_dir / "metaphor.json"),
        )
        self.templates = merge_templates(
            system_templates,
            _load_yaml(user_dir / "task_templates.yaml"),
        )
        self.synonyms = merge_synonyms(
            system_synonyms,
            _load_yaml(user_dir / "synonyms.yaml"),
        )
