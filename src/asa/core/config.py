#
# Configuration
#
# Shipped defaults, optionally overridden by a file


"""Runtime configuration for the agent.

Two layers, resolved in this order — later wins:

1. ``defaults.toml``, shipped alongside this module;
2. an override file passed to ``load_config()`` (``asa --config <file>``).

Command-line arguments are a third layer, applied by the caller rather than here: see
``asa.cli.main``. Keeping that layer out of ``load_config()`` means a notebook can build a
``Config`` without inventing an argv.

The override file need only carry the keys it changes. Unknown keys are an **error**
rather than a warning — a mistyped key in a research config silently reverts a pilot to
the default while the notes say otherwise, which is the sort of thing that invalidates a
run without anybody noticing.
"""

import tomllib
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """One resolved configuration.

    Frozen, so a stage cannot quietly change what a later stage or the run manifest
    reports. ``asdict()`` serialises it for the manifest with no bespoke code.
    """

    design_version: str
    furhat_host: str
    source: str | None = None       # the override file used, or None for defaults only

    def as_dict(self) -> dict[str, object]:
        """The configuration as plain data, for recording into a run manifest."""
        return asdict(self)


def load_config(path: Path | None = None) -> Config:
    """Resolve the configuration, optionally layering an override file on the defaults."""
    merged = _read_defaults()

    if path is not None:
        override = _read_toml(path)
        _reject_unknown(override, merged, path)
        for section, values in override.items():
            merged[section].update(values)

    return Config(
        design_version=merged["project"]["design_version"],
        furhat_host=merged["furhat"]["host"],
        source=str(path) if path is not None else None,
    )


def _read_defaults() -> dict[str, dict]:
    """Read the packaged defaults.

    Located through ``importlib.resources`` rather than ``__file__`` or a relative path,
    so it resolves from any working directory and from a real (non-editable) install as
    well as the editable one — the same property that makes ``import asa`` work anywhere.
    """
    text = files("asa.core").joinpath("defaults.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def _read_toml(path: Path) -> dict[str, dict]:
    """Read one TOML file, with a message that names the file when it is missing."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"No configuration file at {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path} is not valid TOML: {error}") from None


def _reject_unknown(override: dict[str, dict], defaults: dict[str, dict],
                    path: Path) -> None:
    """Raise on any section or key the defaults do not define."""
    for section, values in override.items():
        if section not in defaults:
            raise ValueError(f"{path}: unknown section [{section}]")
        unknown = set(values) - set(defaults[section])
        if unknown:
            keys = ", ".join(sorted(unknown))
            raise ValueError(f"{path}: unknown key(s) in [{section}] — {keys}")
