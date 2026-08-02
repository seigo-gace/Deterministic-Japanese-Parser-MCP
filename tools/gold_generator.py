#!/usr/bin/env python3
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("--log",required=True);p.add_argument("--out",default="proposals/gold_candidates.json");a=p.parse_args()
 cases=[]
 for line in Path(a.log).read_text(encoding="utf-8").splitlines():
  try:r=json.loads(line)
  except json.JSONDecodeError:continue
  t=r.get("original_text","").strip()
  if t: cases.append({"id":f"CAND-{len(cases)+1:04d}","text":t,"expected":{"intents":[],"metaphors":[]},"requires_review":True})
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({"version":"1.0.0","cases":cases},ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"wrote {len(cases)} candidates to {out}")
if __name__=="__main__":main()
