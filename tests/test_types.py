#
# Tests - Type checker
#

"""Type-check the project as part of the test suite (`pyright`).

Ruff lints; it does not type-check. Without this the only thing seeing this class of error
is the editor, so it is invisible to anyone running the suite — which is how twelve of them
accumulated unnoticed in a single sitting, one of which was a `Protocol` that failed to
describe the very types it was written for.

`pyright` rather than `mypy` because it is the engine Pylance wraps, so this test agrees
with what the editor shows. A different checker would be a second opinion that disagrees in
both directions, and a gate that contradicts your editor teaches you to distrust one of
them without saying which.

Settings live in `[tool.pyright]` in pyproject.toml, which Pylance reads as well.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_pyright_reports_no_type_errors():
    """`pyright` reports nothing across `src/` and `tests/`.

    Both directories, and that is the point rather than mere thoroughness: the protocol bug
    that prompted this test lived in `src/asa/core/observers.py` yet produced no error
    there. That module violates nothing on its own — the mismatch appears only where
    something tries to satisfy the protocol, which is in the tests. Checking `src` alone
    would have caught none of it.

    `sys.executable -m pyright` for the same reason as the ruff check: it uses the
    interpreter pytest is running under, so the result is identical from the terminal and
    from the VS Code test panel, with no reliance on PATH.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "src", "tests"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"\npyright reported issues:\n{result.stdout}{result.stderr}"
