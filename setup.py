from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent


class build_py(_build_py):
    """Reject stale immutable language assets before wheel packaging."""

    def run(self):
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/compile_language_features.py"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )
        super().run()


setup(cmdclass={"build_py": build_py})
