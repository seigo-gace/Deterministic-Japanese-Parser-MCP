from dataclasses import dataclass
from pathlib import Path
import os
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[2]
INSTALLED_ROOT = Path(sys.prefix) / "share/deterministic-japanese-parser-mcp"
DEFAULT_DICT_ROOT = (
    SOURCE_ROOT / "dictionaries"
    if (SOURCE_ROOT / "dictionaries/system").exists()
    else INSTALLED_ROOT / "dictionaries"
)


@dataclass(frozen=True)
class Settings:
    max_input_length: int = int(os.getenv("DJPMCP_MAX_INPUT_LENGTH", "20000"))
    max_context_items: int = int(os.getenv("DJPMCP_MAX_CONTEXT_ITEMS", "20"))
    max_candidates: int = int(os.getenv("DJPMCP_MAX_CANDIDATES", "8"))
    regex_timeout_ms: int = int(os.getenv("DJPMCP_REGEX_TIMEOUT_MS", "25"))
    target_latency_ms: int = int(os.getenv("DJPMCP_TARGET_LATENCY_MS", "10"))
    hard_deadline_ms: int = int(os.getenv("DJPMCP_HARD_DEADLINE_MS", "50"))
    max_graph_nodes: int = int(os.getenv("DJPMCP_MAX_GRAPH_NODES", "512"))
    max_scope_edges: int = int(os.getenv("DJPMCP_MAX_SCOPE_EDGES", "1024"))
    log_path: Path = Path(
        os.getenv("DJPMCP_LOG_PATH", str(SOURCE_ROOT / "logs/parser.jsonl"))
    )
    system_dict_dir: Path = Path(
        os.getenv("DJPMCP_SYSTEM_DICT_DIR", str(DEFAULT_DICT_ROOT / "system"))
    )
    user_dict_dir: Path = Path(
        os.getenv("DJPMCP_USER_DICT_DIR", str(DEFAULT_DICT_ROOT / "user"))
    )

    def __post_init__(self) -> None:
        if self.target_latency_ms < 1:
            raise ValueError("target_latency_ms must be at least 1")
        if self.hard_deadline_ms < self.target_latency_ms:
            raise ValueError("hard_deadline_ms must be >= target_latency_ms")
        if self.max_graph_nodes < 32:
            raise ValueError("max_graph_nodes must be at least 32")
        if self.max_scope_edges < 32:
            raise ValueError("max_scope_edges must be at least 32")


SETTINGS = Settings()
