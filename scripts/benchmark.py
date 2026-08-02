#!/usr/bin/env python3
import statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
e=ParserEngine();samples=["UIは残せ。APIだけ変更しろ。","障害の火消しをして穴を塞げ。","テストが通ったら公開するな。"]
values=[]
for _ in range(100):
 for s in samples:
  t=time.perf_counter();e.analyze(AnalyzeRequest(original_text=s));values.append((time.perf_counter()-t)*1000)
values.sort()
def pct(p):return values[min(len(values)-1,int(len(values)*p))]
print({"n":len(values),"p50_ms":round(pct(.5),3),"p95_ms":round(pct(.95),3),"p99_ms":round(pct(.99),3),"mean_ms":round(statistics.mean(values),3)})
