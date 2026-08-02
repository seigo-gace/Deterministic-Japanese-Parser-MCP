import sys
from pathlib import Path
def validate_main()->None:
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root))
    from tools.validator import main
    raise SystemExit(main())
