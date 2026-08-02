#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
SAMPLES=["今のUIは殺すな。APIだけ変更しろ。","障害の火消しをして、落ち着いてから穴を全部塞げ。最後にGitHubへ入れろ。","これを前の案と比較しろ。"]
e=ParserEngine()
for text in SAMPLES: print(e.analyze(AnalyzeRequest(original_text=text,conversation_context=["旧API案"],known_entities=["新API案"])).model_dump_json(indent=2))
