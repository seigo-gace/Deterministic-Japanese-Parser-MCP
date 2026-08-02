#!/usr/bin/env python3
import json,sys,yaml,regex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
def load_metaphors():
 entries=[]
 for path in sorted((ROOT/"dictionaries/system/metaphors").glob("*.json")): entries.extend(json.loads(path.read_text(encoding="utf-8")).get("entries",[]))
 return entries
def load_rules():
 intents={}
 for path in sorted((ROOT/"dictionaries/system/rules").glob("*.yaml")):
  doc=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
  for intent,items in doc.get("intents",{}).items():intents.setdefault(intent,[]).extend(items or [])
 return intents
def load_gold():
 cases=[]
 for path in sorted((ROOT/"tests/gold").glob("*.json")):cases.extend(json.loads(path.read_text(encoding="utf-8")).get("cases",[]))
 return cases
def main():
 errors=[];meta=load_metaphors();seen=set()
 for e in meta:
  for key in ("expression","interpretation","context","domain","version"):
   if key not in e:errors.append(f"metaphor missing {key}: {e}")
  if e.get("expression") in seen:errors.append(f"duplicate metaphor: {e['expression']}")
  seen.add(e.get("expression"))
 rules=load_rules();ids=set()
 for intent,items in rules.items():
  for item in items:
   if item["id"] in ids:errors.append(f"duplicate rule id: {item['id']}")
   ids.add(item["id"])
   try:regex.compile(item["pattern"])
   except Exception as exc:errors.append(f"bad regex {item['id']}: {exc}")
 engine=ParserEngine();gold=load_gold();failures=[]
 for case in gold:
  resp=engine.analyze(AnalyzeRequest(original_text=case["text"]));got={x.type for x in resp.intents};expected=set(case["expected"].get("intents",[]));missing=expected-got;got_m={x.expression for x in resp.metaphors};missing_m=set(case["expected"].get("metaphors",[]))-got_m
  if missing or missing_m:failures.append({"id":case["id"],"missing_intents":sorted(missing),"missing_metaphors":sorted(missing_m),"got":sorted(got)})
 if failures:errors.append(f"gold failures: {len(failures)} first={failures[:5]}")
 if errors:
  print("VALIDATION FAILED")
  for error in errors:print("-",error)
  return 1
 print(f"VALIDATION OK: metaphors={len(meta)} rules={len(ids)} gold={len(gold)}");return 0
if __name__=="__main__":raise SystemExit(main())
