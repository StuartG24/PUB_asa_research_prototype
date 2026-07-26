#
# Tests - Greeter Class
#

"""Tests for asa.greeter.Greeter."""

from asa import Greeter


def test_default_greeting():
    """Greeter with no name greets the World."""
    assert Greeter().greet() == "Hello, World!"


def test_named_greeting():
    """Greeter uses the name it was given."""
    assert Greeter("asa").greet() == "Hello, asa!"
