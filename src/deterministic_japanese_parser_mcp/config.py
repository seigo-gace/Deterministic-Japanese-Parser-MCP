from dataclasses import dataclass
from pathlib import Path
import os
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[2]
INSTALLED_ROOT = Path(sys.prefix) / "share/deterministic-japanese-parser-mcp"
DEFAULT_DICT_ROOT = SOURCE_ROOT / "dictionaries" if (SOURCE_ROOT / "dictionaries/system").exists() else INSTALLED_ROOT / "dictionaries"

@dataclass(frozen=True)
class Settings:
    max_input_length: int = int(os.getenv("DJPMCP_MAX_INPUT_LENGTH", "20000"))
    max_context_items: int = int(os.getenv("DJPMCP_MAX_CONTEXT_ITEMS", "20"))
    max_candidates: int = int(os.getenv("DJPMCP_MAX_CANDIDATES", "8"))
    regex_timeout_ms: int = int(os.getenv("DJPMCP_REGEX_TIMEOUT_MS", "25"))
    log_path: Path = Path(os.getenv("DJPMCP_LOG_PATH", str(SOURCE_ROOT / "logs/parser.jsonl")))
    system_dict_dir: Path = Path(os.getenv("DJPMCP_SYSTEM_DICT_DIR", str(DEFAULT_DICT_ROOT / "system")))
    user_dict_dir: Path = Path(os.getenv("DJPMCP_USER_DICT_DIR", str(DEFAULT_DICT_ROOT / "user")))

SETTINGS = Settings()
