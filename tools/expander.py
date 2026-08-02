#!/usr/bin/env python3
import argparse,yaml,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--out",default="proposals/synonym_expansion.yaml");a=p.parse_args()
 synonyms=yaml.safe_load((ROOT/"dictionaries/system/synonyms.yaml").read_text(encoding="utf-8"))["groups"]
 entries=[]
 for path in sorted((ROOT/"dictionaries/system/metaphors").glob("*.json")): entries.extend(json.loads(path.read_text(encoding="utf-8")).get("entries",[]))
 proposals=[]
 for entry in entries:
  aliases=set(entry.get("aliases",[]))
  for canonical,words in synonyms.items():
   if canonical in entry["interpretation"]: aliases.update(words)
  if aliases: proposals.append({"expression":entry["expression"],"current_aliases":entry.get("aliases",[]),"proposed_aliases":sorted(aliases),"requires_review":True})
 out=ROOT/a.out;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(yaml.safe_dump({"version":"1.0.0","proposals":proposals},allow_unicode=True,sort_keys=False),encoding="utf-8")
 print(f"wrote {len(proposals)} review items to {out}")
if __name__=="__main__":main()
