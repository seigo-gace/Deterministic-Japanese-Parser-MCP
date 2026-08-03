from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import lexicon_validator


def test_runtime_lexicon_provenance_is_valid():
    assert lexicon_validator.main() == 0
