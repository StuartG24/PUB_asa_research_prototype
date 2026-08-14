#
# Repository paths for notebooks
#
# A development utility — nothing in the library may import it


"""Where the repository is, asked from a notebook that does not know where it was started.

Every data-loading notebook needs ``data_in/``

**It stays in ``_tools`` and the library must not reach for it.** ``nrc_eil.load_tables``
deliberately refuses a default path, on the grounds that where a file lives is a composition
root's decision rather than a module's. A ``repo_root()`` importable from ``asa.perception``
would hand every module a way to undo that quietly. A notebook *is* a composition root and may
use this; ``core``, ``perception`` and ``affect_model`` may not.
"""

from pathlib import Path


def repo_root(marker: str = "uv.lock") -> Path:
    """Nearest ancestor of this module containing *marker*.

    **Anchored on ``__file__`` rather than ``Path.cwd()``.** Jupyter starts a kernel in the
    notebook's own directory, so a walk up from the working directory does work — until a cell
    calls ``os.chdir``, or the kernel is launched from somewhere else, at which point it finds
    the wrong root or none, and does so silently because both outcomes look like a path. The
    module's own location moves only when the source tree does.

    ``uv.lock`` rather than ``pyproject.toml`` because a workspace has exactly one lock file and
    may have several ``pyproject.toml``, so the walk cannot stop early at a subproject. It is
    tracked, so a fresh clone has it before anything has been installed.

    **Raises rather than falling back to a guess.** An ``asa`` installed non-editable sits in
    ``site-packages`` with no lock file above it, and a plausible-looking wrong root would be
    discovered later, as a confusing read of the wrong data. A stack trace names the problem
    where it happens.
    """
    start = Path(__file__).resolve()
    for candidate in (start, *start.parents):
        if (candidate / marker).is_file():
            return candidate
    raise FileNotFoundError(f"No {marker} found above {start}")
