#
# Test - configuration
#

"""Tests for the two-layer configuration load.

The packaged defaults are read through ``importlib.resources``, so these tests also prove
the TOML is genuinely reachable from the installed package rather than only from the
repository root — which is the whole reason it lives inside ``src/asa/core/``.
"""

import pytest

from asa.core.config import load_config


def test_defaults_load():
    """The shipped defaults resolve with no override file."""
    config = load_config()
    assert config.furhat_host == "127.0.0.1"
    assert config.source is None
    assert config.design_version                 # populated from [project]; value pinned below


def test_the_design_version_is_pinned_deliberately():
    """A tripwire against unintended change — **not** a check that the version is correct.

    It cannot be one. ``design_version`` names the design document this build implements, and
    that document lives in a different repository, so nothing here can verify it. What this
    catches is a half-finished or accidental edit to ``defaults.toml``: the value reaches
    every run manifest, and a wrong one silently mislabels research data whose provenance is
    the only reason the field exists.

    **What it deliberately cannot catch, and this is worth knowing before relying on it:** a
    bump that never happened. Change the design document to v0.7 and touch neither this line
    nor ``defaults.toml``, and the suite stays green while every manifest claims v0.6. The
    mitigation is procedural — bump the document and the package in one sitting — not
    technical.

    One assertion, not three. It was three until 2026-08-04, which put four copies of one
    string in the repository and tested only that they agreed with each other. The other two
    now assert the properties their names claim, which is what they were always for.
    """
    assert load_config().design_version == "v0.6.1"


def test_override_replaces_only_the_keys_given(tmp_path):
    """A partial override file leaves every key it does not mention alone."""
    override = tmp_path / "pilot.toml"
    override.write_text('[furhat]\nhost = "10.0.0.5"\n', encoding="utf-8")

    config = load_config(override)
    assert config.furhat_host == "10.0.0.5"
    assert config.source == str(override)
    # compared against the default rather than a literal: the claim is that the override
    # left this alone, and a literal would assert that *and* what the default happens to be
    assert config.design_version == load_config().design_version


def test_unknown_key_is_rejected(tmp_path):
    """A mistyped key fails loudly instead of silently leaving the default in place.

    This is the failure that matters for research data: the run quietly uses the default
    while the notes record the intended value, and nothing in the results says so.
    """
    override = tmp_path / "typo.toml"
    override.write_text('[furhat]\nhostname = "10.0.0.5"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unknown key"):
        load_config(override)


def test_unknown_section_is_rejected(tmp_path):
    """Same again one level up — a section the defaults do not define."""
    override = tmp_path / "typo.toml"
    override.write_text('[furhatt]\nhost = "10.0.0.5"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unknown section"):
        load_config(override)


def test_missing_file_names_the_path(tmp_path):
    """The error says which file was not found, not just that something was missing."""
    missing = tmp_path / "not-here.toml"

    with pytest.raises(FileNotFoundError, match="not-here.toml"):
        load_config(missing)


def test_as_dict_is_plain_data():
    """The manifest serialises the config with no bespoke code.

    Every field appears, as plain data. ``design_version`` is compared against the config it
    came from rather than a literal — the claim here is that ``as_dict`` loses nothing, not
    what any particular value is.
    """
    config = load_config()

    assert config.as_dict() == {
        "design_version": config.design_version,
        "furhat_host": "127.0.0.1",
        "source": None,
    }
