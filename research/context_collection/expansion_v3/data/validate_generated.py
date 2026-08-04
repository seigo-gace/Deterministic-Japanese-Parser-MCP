#!/usr/bin/env python3
"""Dependency-free structural validator for generated Context Data v3 YAML files."""
from __future__ import annotations
import argparse, json, re, unicodedata
from collections import Counter
from pathlib import Path
EXPECTED = {"slang":1000,"onomatopoeia":700,"modality":500,"honorific":500,"discourse":400,"metaphor":500,"dialect":400,"media_community":500,"reference":300,"epistemic":200}
REQUIRED = ["entry_id:","surface:","feature_type:","meaning_candidates:","source:","source_version:","license:","review_status: \"needs-evidence\"","external_action_risk:","positive_examples:","negative_examples:","boundary_examples:"]
def norm(s): return unicodedata.normalize("NFKC",s).strip().casefold()
def main():
 p=argparse.ArgumentParser(); p.add_argument("root",type=Path); a=p.parse_args()
 files=sorted(a.root.glob("*/*.yaml")); errors=[]; counts=Counter(); surfaces=[]
 if len(files)!=5000: errors.append(f"yaml file count={len(files)}")
 for f in files:
  counts[f.parent.name]+=1; text=f.read_text(encoding="utf-8")
  for key in REQUIRED:
   if key not in text: errors.append(f"{f}: missing {key}")
  m=re.search(r'^surface: (.+)$',text,re.M)
  if not m: errors.append(f"{f}: missing surface"); continue
  try: surfaces.append(norm(json.loads(m.group(1))))
  except Exception: errors.append(f"{f}: invalid surface JSON string")
  if re.search(r'(?:mock|placeholder|候補[0-9０-９]{2,})',text,re.I): errors.append(f"{f}: placeholder pattern")
 if dict(counts)!=EXPECTED: errors.append(f"category counts={dict(counts)}")
 if len(set(surfaces))!=5000: errors.append(f"unique surfaces={len(set(surfaces))}")
 result={"ok":not errors,"yaml_files":len(files),"unique_surfaces":len(set(surfaces)),"category_counts":dict(counts),"errors":errors[:100]}
 print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0 if not errors else 1)
if __name__=="__main__": main()
