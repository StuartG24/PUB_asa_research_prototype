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
    assert config.design_version == "v0.3"
    assert config.furhat_host == "127.0.0.1"
    assert config.source is None


def test_override_replaces_only_the_keys_given(tmp_path):
    """A partial override file leaves every key it does not mention alone."""
    override = tmp_path / "pilot.toml"
    override.write_text('[furhat]\nhost = "10.0.0.5"\n', encoding="utf-8")

    config = load_config(override)
    assert config.furhat_host == "10.0.0.5"
    assert config.design_version == "v0.3"       # untouched by the override
    assert config.source == str(override)


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
    """The manifest serialises the config with no bespoke code."""
    assert load_config().as_dict() == {
        "design_version": "v0.3",
        "furhat_host": "127.0.0.1",
        "source": None,
    }
