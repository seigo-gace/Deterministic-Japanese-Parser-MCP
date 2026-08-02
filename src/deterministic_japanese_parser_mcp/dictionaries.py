from pathlib import Path
import json, yaml


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml_set(path: Path) -> dict:
    if path.is_file():
        return _load_yaml(path)
    docs = [_load_yaml(p) for p in sorted(path.glob("*.yaml"))]
    out = {"version": "0", "timeout_ms": 25, "intents": {}}
    for doc in docs:
        out["version"] = doc.get("version", out["version"])
        out["timeout_ms"] = doc.get("timeout_ms", out["timeout_ms"])
        for intent, items in doc.get("intents", {}).items():
            out["intents"].setdefault(intent, []).extend(items or [])
    return out


def _load_json_set(path: Path) -> dict:
    if path.is_file():
        return _load_json(path)
    docs = [_load_json(p) for p in sorted(path.glob("*.json"))]
    out = {"version": "0", "entries": []}
    for doc in docs:
        out["version"] = doc.get("version", out["version"])
        out["entries"].extend(doc.get("entries", []))
    return out


def merge_rule_docs(system: dict, user: dict) -> dict:
    merged = {"version": system.get("version", "0"), "timeout_ms": system.get("timeout_ms", 25), "intents": {}}
    for src in (system, user):
        for intent, items in src.get("intents", {}).items():
            merged["intents"].setdefault(intent, []).extend(items or [])
    return merged


def merge_metaphors(system: dict, user: dict) -> dict:
    by_exp = {}
    for src in (system, user):
        for item in src.get("entries", []):
            by_exp[item["expression"]] = item
    return {"version": system.get("version", "0"), "entries": list(by_exp.values())}


def merge_templates(system: dict, user: dict) -> dict:
    by_id = {}
    for src in (system, user):
        for item in src.get("templates", []):
            by_id[item["id"]] = item
    return {"version": system.get("version", "0"), "templates": list(by_id.values())}


class DictionaryBundle:
    def __init__(self, system_dir: Path, user_dir: Path):
        system_rules = _load_yaml_set(system_dir / "rules")
        system_metaphors = _load_json_set(system_dir / "metaphors")
        self.rules = merge_rule_docs(system_rules, _load_yaml(user_dir / "rules.yaml"))
        self.metaphors = merge_metaphors(system_metaphors, _load_json(user_dir / "metaphor.json"))
        self.templates = merge_templates(_load_yaml(system_dir / "task_templates.yaml"), _load_yaml(user_dir / "task_templates.yaml"))
        self.synonyms = _load_yaml(system_dir / "synonyms.yaml")
