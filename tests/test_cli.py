#
# Test - CLI
#

"""Tests for the asa command-line entry point.

``main()`` is driven with an explicit ``argv`` list throughout. Left to default it would
read ``sys.argv``, which under pytest is *pytest's* own command line — argparse rejects it
and exits 2, so the test would fail for a reason that has nothing to do with the CLI.

**There are two paths and the agent is the default**, so every test about the robot passes
``--furhat-demo``. Without it they would run the agent, whose text console reads stdin —
which under pytest raises, from somewhere that explains nothing.
"""

import pytest

from asa.cli import build_parser, main
from asa.core.observers import Observers
from asa.perception.decode_keyword import KeywordDecoder
from asa.perception.text_console import TextConsole
from asa.session import FurhatUnreachable


def _fake_session(events: list[str], *,
                  start_error: Exception | None = None,
                  gesture_error: Exception | None = None) -> type:
    """A stand-in ``ASASession`` that records what the demo did to it.

    Stubbed rather than pointed at a dead address. A test that relied on nothing listening
    would quietly invert its meaning the day a Furhat *is* running locally — and would then
    connect and make the robot speak.
    """
    class FakeSession:
        def __init__(self, host: str, **kwargs: object) -> None:
            events.append(f"host={host}")

        async def start(self) -> None:
            events.append("start")
            if start_error is not None:
                raise start_error

        async def gesture(self, name: str, **kwargs: object) -> None:
            events.append("gesture")
            if gesture_error is not None:
                raise gesture_error

        async def say(self, text: str) -> None:
            events.append("say")

        async def stop(self) -> None:
            events.append("stop")

    return FakeSession


def test_defaults():
    """No arguments leaves --host unset so the configured value shows through.

    ``None`` rather than an address is the point: a default here would make the argument
    always present, and it would then beat every configuration file silently.
    ``--furhat-demo`` defaulting to False is what makes the agent the default path.
    """
    args = build_parser().parse_args([])
    assert args.host is None
    assert args.config is None
    assert args.log == "debug"
    assert args.furhat_demo is False


def test_arguments_are_read():
    """The options are parsed off the command line."""
    args = build_parser().parse_args(["--log", "warning", "--host", "10.0.0.5"])
    assert args.host == "10.0.0.5"
    assert args.log == "warning"


def test_rejects_unknown_log_level():
    """An unlisted --log value is refused rather than passed through to logging."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--log", "verbose"])


def test_the_default_path_composes_the_agent_and_never_touches_the_robot(monkeypatch):
    """The composition root's actual job, and the branch that chooses the agent.

    ``run_agent`` is replaced so nothing runs; what is under test is what it was *handed*.
    The forbidden session is the other half of the claim — the agent path must not open a
    websocket, and asserting that a robot was not contacted needs something that objects.
    """
    captured: dict[str, object] = {}

    async def recording_run_agent(**kwargs: object) -> None:
        captured.update(kwargs)

    class ForbiddenSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("the agent path must not construct a Furhat session")

    monkeypatch.setattr("asa.cli.run_agent", recording_run_agent)
    monkeypatch.setattr("asa.cli.ASASession", ForbiddenSession)

    main(["--log", "warning"])

    assert isinstance(captured["source"], TextConsole)
    assert isinstance(captured["decoder"], KeywordDecoder)
    assert isinstance(captured["observers"], Observers)


def test_host_falls_back_to_configuration(monkeypatch):
    """With no --host, the session is built with the host from configuration."""
    events: list[str] = []
    monkeypatch.setattr("asa.cli.ASASession", _fake_session(events))

    main(["--log", "warning", "--furhat-demo"])

    assert events[0] == "host=127.0.0.1"


def test_host_argument_beats_configuration(monkeypatch):
    """An explicit --host wins over the configured value — the third layer."""
    events: list[str] = []
    monkeypatch.setattr("asa.cli.ASASession", _fake_session(events))

    main(["--log", "warning", "--host", "10.0.0.5", "--furhat-demo"])

    assert events[0] == "host=10.0.0.5"


def test_unreachable_furhat_exits_non_zero(monkeypatch):
    """main() turns FurhatUnreachable into a clean exit 1 rather than a traceback."""
    events: list[str] = []
    monkeypatch.setattr("asa.cli.ASASession",
                        _fake_session(events, start_error=FurhatUnreachable("no Furhat (test stub)")))

    with pytest.raises(SystemExit) as exit_info:
        main(["--log", "warning", "--furhat-demo"])

    assert exit_info.value.code == 1


def test_the_demo_session_is_closed_even_if_it_fails_midway(monkeypatch):
    """A failure part-way through still closes the session — the point of the ``finally``.

    Without it the websocket leaks and the Furhat is left half-connected, which is the one
    thing the notebook's start/actions/stop shape cannot guarantee on its own. The trace also
    shows ``say`` was never reached, so ``stop`` ran because of the ``finally`` rather than
    because the demo simply carried on.
    """
    events: list[str] = []
    monkeypatch.setattr("asa.cli.ASASession",
                        _fake_session(events, gesture_error=RuntimeError("something went wrong")))

    with pytest.raises(RuntimeError):
        main(["--log", "warning", "--furhat-demo"])

    assert events == ["host=127.0.0.1", "start", "gesture", "stop"]


def test_start_failure_does_not_call_stop(monkeypatch):
    """If the connection never opened there is nothing to close, so stop() is not called."""
    events: list[str] = []
    monkeypatch.setattr("asa.cli.ASASession",
                        _fake_session(events, start_error=FurhatUnreachable("no Furhat (test stub)")))

    with pytest.raises(SystemExit):
        main(["--log", "warning", "--furhat-demo"])

    assert events == ["host=127.0.0.1", "start"]
