#!/usr/bin/env python3
import json, sys, yaml, regex
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from deterministic_japanese_parser_mcp import ParserEngine, AnalyzeRequest


def load_metaphors():
    entries=[]
    for path in sorted((ROOT / "dictionaries/system/metaphors").glob("*.json")):
        entries.extend(json.loads(path.read_text(encoding="utf-8")).get("entries", []))
    return entries


def load_rules():
    intents={}
    for path in sorted((ROOT / "dictionaries/system/rules").glob("*.yaml")):
        doc=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for intent,items in doc.get("intents",{}).items(): intents.setdefault(intent,[]).extend(items or [])
    return intents


def load_gold():
    cases=[]
    for path in sorted((ROOT / "tests/gold").glob("*.json")):
        cases.extend(json.loads(path.read_text(encoding="utf-8")).get("cases", []))
    return cases


def main():
    errors=[]; meta=load_metaphors(); seen=set(); surface_owner={}
    for e in meta:
        for key in ("expression","interpretation","context","domain","version"):
            if key not in e: errors.append(f"metaphor missing {key}: {e}")
        expression=e.get("expression")
        if expression in seen: errors.append(f"duplicate metaphor: {expression}")
        seen.add(expression)
        for surface in [expression, *e.get("aliases",[])]:
            owner=surface_owner.get(surface)
            if owner and owner != expression:
                errors.append(f"metaphor surface collision: {surface}: {owner} / {expression}")
            surface_owner[surface]=expression
    manifest_path=ROOT / "dictionaries/system/metaphors/manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("metaphor_entries") != len(meta):
        errors.append(f"manifest metaphor count mismatch: {manifest.get('metaphor_entries')} != {len(meta)}")
    rules=load_rules(); ids=set()
    for intent,items in rules.items():
        for item in items:
            if item["id"] in ids: errors.append(f"duplicate rule id: {item['id']}")
            ids.add(item["id"])
            try: regex.compile(item["pattern"])
            except Exception as exc: errors.append(f"bad regex {item['id']}: {exc}")
    engine=ParserEngine(); gold=load_gold(); failures=[]
    for case in gold:
        resp=engine.analyze(AnalyzeRequest(original_text=case["text"]))
        expected_doc=case["expected"]
        got={x.type for x in resp.intents}; expected=set(expected_doc.get("intents",[]))
        missing=expected-got
        forbidden=set(expected_doc.get("forbidden_intents",[])) & got
        got_m_list=[x.expression for x in resp.metaphors]
        got_m=set(got_m_list); missing_m=set(expected_doc.get("metaphors",[]))-got_m
        duplicate_m=[]
        if expected_doc.get("unique_metaphors"):
            duplicate_m=sorted({x for x in got_m_list if got_m_list.count(x)>1})
        got_tasks=[x.intent_type for x in resp.tasks]
        missing_tasks=set(expected_doc.get("task_intents",[]))-set(got_tasks)
        forbidden_tasks=set(expected_doc.get("forbidden_task_intents",[])) & set(got_tasks)
        if missing or forbidden or missing_m or duplicate_m or missing_tasks or forbidden_tasks:
            failures.append({
                "id":case["id"],
                "missing_intents":sorted(missing),
                "forbidden_intents":sorted(forbidden),
                "missing_metaphors":sorted(missing_m),
                "duplicate_metaphors":duplicate_m,
                "missing_task_intents":sorted(missing_tasks),
                "forbidden_task_intents":sorted(forbidden_tasks),
                "got":sorted(got),
                "got_tasks":got_tasks,
            })
    if failures: errors.append(f"gold failures: {len(failures)} first={failures[:5]}")
    if errors:
        print("VALIDATION FAILED")
        for error in errors: print("-",error)
        return 1
    print(f"VALIDATION OK: metaphors={len(meta)} rules={len(ids)} gold={len(gold)}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
