import json
from pathlib import Path
from datetime import datetime, timezone

def append_log(path:Path,payload:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    row={"timestamp":datetime.now(timezone.utc).isoformat(),**payload}
    with path.open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False)+"\n")
