#
# Test - CLI
#

"""Tests for the asa command-line entry point.

``main()`` is driven with an explicit ``argv`` list throughout. Left to default it would
read ``sys.argv``, which under pytest is *pytest's* own command line — argparse rejects it
and exits 2, so the test would fail for a reason that has nothing to do with the CLI.
"""

import pytest

from asa.cli import build_parser, main
from asa.session import FurhatUnreachable


def test_defaults():
    """No arguments gives the virtual Furhat and debug logging."""
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.log == "debug"


def test_arguments_are_read():
    """Both options are parsed off the command line."""
    args = build_parser().parse_args(["--log", "warning", "--host", "10.0.0.5"])
    assert args.host == "10.0.0.5"
    assert args.log == "warning"


def test_rejects_unknown_log_level():
    """An unlisted --log value is refused rather than passed through to logging."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--log", "verbose"])


def test_unreachable_furhat_exits_non_zero(monkeypatch):
    """main() turns FurhatUnreachable into a clean exit 1 rather than a traceback.

    The session is stubbed rather than pointed at a dead address. A test that relied on
    nothing listening would quietly invert its meaning the day a Furhat *is* running
    locally — and would then connect and make the robot speak.
    """

    class UnreachableSession:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            raise FurhatUnreachable("no Furhat (test stub)")

        async def stop(self):
            pass

    monkeypatch.setattr("asa.cli.ASASession", UnreachableSession)

    with pytest.raises(SystemExit) as exit_info:
        main(["--log", "warning"])
    assert exit_info.value.code == 1


def test_session_is_stopped_even_if_interaction_fails(monkeypatch):
    """A failure mid-interaction still closes the session — the point of run_session's finally.

    Without it the websocket would leak and the Furhat would be left half-connected, which
    is the one thing the notebook's start/actions/stop shape cannot guarantee on its own.
    """
    events = []

    class RecordingSession:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            events.append("start")

        async def stop(self):
            events.append("stop")

    async def failing_interaction(session):
        events.append("interaction")
        raise RuntimeError("something went wrong mid-conversation")

    monkeypatch.setattr("asa.cli.ASASession", RecordingSession)
    monkeypatch.setattr("asa.cli.interaction", failing_interaction)

    with pytest.raises(RuntimeError):
        main(["--log", "warning"])

    assert events == ["start", "interaction", "stop"]


def test_start_failure_does_not_call_stop(monkeypatch):
    """If the connection never opened there is nothing to close, so stop() is not called."""
    events = []

    class FailingSession:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            events.append("start")
            raise FurhatUnreachable("no Furhat (test stub)")

        async def stop(self):
            events.append("stop")

    monkeypatch.setattr("asa.cli.ASASession", FailingSession)

    with pytest.raises(SystemExit):
        main(["--log", "warning"])

    assert events == ["start"]
