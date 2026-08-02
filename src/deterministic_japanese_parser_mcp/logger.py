import json
import re
from datetime import datetime, timezone
from pathlib import Path

_EMAIL = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}")
_API_KEY = re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{12,19}(?!\d)")


def mask_sensitive_text(text: str) -> str:
    value = _EMAIL.sub("<EMAIL>", text)
    value = _BEARER.sub("Bearer <TOKEN>", value)
    value = _API_KEY.sub("<SECRET>", value)
    value = _LONG_NUMBER.sub("<LONG_NUMBER>", value)
    return value


def append_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(payload)
    if isinstance(safe.get("original_text"), str):
        safe["original_text"] = mask_sensitive_text(safe["original_text"])
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), **safe}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
