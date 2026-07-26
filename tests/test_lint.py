#
# Tests - Linter
#

"""Lint the project as part of the test suite (`ruff check`).

Runs the linter over the whole repo and fails if ruff reports anything. Uses
`ruff check` only — formatting is handled by autopep8, not `ruff format`.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_ruff_check_passes():
    """`ruff check .` reports no lint violations across the project."""
    # `sys.executable -m ruff` uses the interpreter pytest is running under, so it
    # works the same from the terminal and the VS Code test panel (no PATH reliance).
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"\nruff reported issues:\n{result.stdout}{result.stderr}"
