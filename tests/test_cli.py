#
# Test - CLI
#

"""Smoke test for the asa command-line entry point."""

from asa.cli import main


def test_cli_prints_greeting(capsys):
    """main() prints the default greeting to stdout."""
    main()
    assert capsys.readouterr().out.strip() == "Hello, World!"
