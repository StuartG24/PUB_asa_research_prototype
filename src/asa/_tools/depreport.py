#
# Dependency Report Utility
#

"""List the dependencies declared in pyproject.toml with their installed version and release date.

Three layers of information, deliberately kept apart because they come from three places:

- the *constraint* (e.g. ``>=0.1.3``) is read from pyproject.toml — what you asked for;
- the *version* is read from the installed metadata in .venv — what you actually got;
- the *date* is fetched from PyPI — when that exact version was published.

Useful for a reproducibility appendix, or just for spotting a dependency that has not
moved in three years. Pure standard library, so it adds nothing to the lock file.

A private development utility (see ``asa._tools``), not part of the public API. It rides
along in the wheel, which costs nothing at import time and keeps it reachable from a
notebook with no sys.path juggling::

    from asa._tools.depreport import report

    report()
"""

import json
import re
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

# PyPI's JSON API for one specific release. The generic /pypi/<name>/json returns the
# *latest* release, which is not what we want — we want the one actually installed.
PYPI_RELEASE_URL = "https://pypi.org/pypi/{name}/{version}/json"

# PEP 508 requirement strings look like "ruff>=0.15.20", "foo[extra]>=1 ; python_version<'3.13'".
# The name is the leading run of letters, digits, dot, dash and underscore.
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class Dependency:
    """One declared dependency, resolved as far as we can take it."""

    name: str
    group: str  # "project" for [project].dependencies, otherwise the dependency-group name
    constraint: str  # the requirement string exactly as written in pyproject.toml
    version: str | None = None  # installed version, None if not installed
    released: str | None = None  # ISO date (YYYY-MM-DD) that version hit PyPI, None if unknown


def find_pyproject(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: this file) to the first directory holding a pyproject.toml."""
    here = (start or Path(__file__)).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No pyproject.toml found at or above {here}")


def requirement_name(requirement: str) -> str | None:
    """Pull the bare distribution name out of a PEP 508 requirement string, or None if unparseable."""
    match = _NAME_RE.match(requirement)
    return match.group(1) if match else None


def declared_dependencies(pyproject: Path | None = None) -> list[Dependency]:
    """Read every dependency declared in pyproject.toml, without touching the network.

    Covers ``[project].dependencies`` and every PEP 735 ``[dependency-groups]`` table.
    ``{ include-group = ... }`` entries are skipped: they point at another group, which is
    itself listed, so following them would only produce duplicates.
    """
    path = pyproject or find_pyproject()
    config = tomllib.loads(path.read_text(encoding="utf-8"))

    sources: list[tuple[str, list]] = [("project", config.get("project", {}).get("dependencies", []))]
    sources += [(group, entries) for group, entries in config.get("dependency-groups", {}).items()]

    found: list[Dependency] = []
    for group, entries in sources:
        for entry in entries:
            if not isinstance(entry, str):  # an include-group table, not a requirement
                continue
            name = requirement_name(entry)
            if name:
                found.append(Dependency(name=name, group=group, constraint=entry.strip()))
    return found


def fetch_release_date(name: str, version: str, timeout: float = 5.0) -> str | None:
    """Return the ISO date ``version`` of ``name`` was published to PyPI, or None if it cannot be found.

    A release can have several files (wheels, sdist) uploaded moments apart, so the earliest
    upload is taken as the release date. Any network or lookup failure returns None rather
    than raising — an unreachable PyPI should not break the report.
    """
    url = PYPI_RELEASE_URL.format(name=name, version=version)
    try:
        # URL is built from a constant https template, so there is no scheme to smuggle.
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    uploads = [f["upload_time_iso_8601"] for f in payload.get("urls", []) if f.get("upload_time_iso_8601")]
    return min(uploads)[:10] if uploads else None


def resolve(dependencies: list[Dependency], offline: bool = False) -> list[Dependency]:
    """Fill in the installed version, and (unless ``offline``) the PyPI release date, for each dependency."""
    resolved: list[Dependency] = []
    for dep in dependencies:
        try:
            version = installed_version(dep.name)
        except PackageNotFoundError:
            version = None
        released = fetch_release_date(dep.name, version) if version and not offline else None
        resolved.append(Dependency(dep.name, dep.group, dep.constraint, version, released))
    return resolved


def report(pyproject: Path | None = None, offline: bool = False) -> list[Dependency]:
    """Print the dependency table and return the rows, so callers can reuse the data."""
    rows = resolve(declared_dependencies(pyproject), offline=offline)

    headers = ("PACKAGE", "INSTALLED", "RELEASED", "GROUP", "DECLARED")
    cells = [(r.name, r.version or "-", r.released or "-", r.group, r.constraint) for r in rows]
    widths = [max(len(h), *(len(row[i]) for row in cells)) for i, h in enumerate(headers)]

    def line(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(values, widths, strict=True)).rstrip()

    print(line(headers))
    print(line(tuple("-" * width for width in widths)))
    for row in cells:
        print(line(row))
    return rows
