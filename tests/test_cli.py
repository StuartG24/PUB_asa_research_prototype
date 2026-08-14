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

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from asa.cli import build_parser, main
from asa.core.affect import AffectObservation, Utterance, utc_now
from asa.core.observers import Observers
from asa.perception.decode_keyword import KeywordDecoder
from asa.perception.text_console import TextConsole
from asa.session import ASASession, FurhatUnreachable


async def _unreachable_run_agent(**kwargs: object) -> None:
    """Stands in for ``run_agent`` where the run must fail before ever reaching it.

    Not a no-op: if a guard under test stops guarding, the CLI would fall through to a real
    agent whose text console reads stdin, and the test would hang rather than fail.
    """
    raise AssertionError("the run should have exited before composing the agent")


def _fake_session(events: list[str], *,
                  start_error: Exception | None = None,
                  gesture_error: Exception | None = None) -> type:
    """A stand-in ``ASASession`` that records what the demo did to it.

    Stubbed rather than pointed at a dead address. A test that relied on nothing listening
    would quietly invert its meaning the day a Furhat *is* running locally — and would then
    connect and make the robot speak.

    ``gesture`` mirrors ``ASASession.gesture`` parameter for parameter rather than absorbing
    the extras into ``**kwargs``. A ``**kwargs`` double is wrong in *both* directions at once:
    it has no positional slots, so it refuses a call the real class accepts — which is what
    broke here, when the demo's gesture chain began passing ``intensity`` and ``duration``
    positionally — and it accepts any keyword at all, so a misspelling the robot would reject
    sails through and the test still passes. Mirroring buys agreement on every call shape; the
    parameter values are unused.
    """
    class FakeSession:
        def __init__(self, host: str, **kwargs: object) -> None:
            events.append(f"host={host}")

        async def start(self) -> None:
            events.append("start")
            if start_error is not None:
                raise start_error

        async def gesture(self, name: str,
                          intensity: float = 1.0, duration: float = 1.0, *,
                          wait: bool = False) -> None:
            events.append("gesture")
            if gesture_error is not None:
                raise gesture_error

        async def say(self, text: str) -> None:
            events.append("say")

        async def stop(self) -> None:
            events.append("stop")

    return FakeSession


def test_the_fake_session_mirrors_the_real_gesture_signature():
    """The double is hand-written, so only this stops it drifting from the class it doubles.

    ``inspect.signature`` equality rather than a call, because the property under test is
    the *shape* of the parameter list — which call shapes are accepted — and a call would
    only ever exercise the one shape it happened to use. This is the check that failed
    silently before: nothing tied the two together, so the demo could change how it calls
    ``gesture`` and only a ``TypeError`` at run time said so.
    """
    assert inspect.signature(_fake_session([]).gesture) == inspect.signature(ASASession.gesture)


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


#
# ── Choosing the decoder's table ────────────────────────────────────────────────────────
#

def _artefact(tmp_path: Path, *, entries: dict | None = None, id_: str = "test-lexicon") -> Path:
    """A prepared lexicon file with one distinctive word per axis.

    The words are nonsense on purpose. Asserting that "sonorous" decodes proves the *artefact*
    was read, where a real emotion word would also be in the built-in tables and so would pass
    whichever table the CLI actually chose.
    """
    prepared = {
        "id": id_,
        "lexicon": "not-a-real-lexicon",
        "prepared_by": "tests/test_cli.py",
        "entries": entries if entries is not None else {
            "anger": {"sonorous": 0.9},
            "anticipation": {"vermillion": 0.7},
            "disgust": {"plangent": 0.9},
            "fear": {"crepuscular": 0.9},
            "joy": {"halcyon": 0.9},
            "sadness": {"lambent": 0.9},
            "surprise": {"eldritch": 0.8},
            "trust": {"adamantine": 0.8},
        },
    }
    path = tmp_path / "lexicon.json"
    path.write_text(json.dumps(prepared), encoding="utf-8")
    return path


def _decode_through(decoder: KeywordDecoder, text: str) -> AffectObservation:
    """What the composed decoder actually produces — the observable, not a private field."""
    utterance = Utterance(text=text, source="input:test", at=utc_now())
    return asyncio.run(decoder.decode(utterance))


def _captured_decoder(monkeypatch, argv: list[str]) -> KeywordDecoder:
    """Run the agent path and hand back the decoder it was composed with."""
    captured: dict[str, object] = {}

    async def recording_run_agent(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("asa.cli.run_agent", recording_run_agent)
    main(argv)

    decoder = captured["decoder"]
    assert isinstance(decoder, KeywordDecoder)
    return decoder


def test_without_a_lexicon_the_built_in_tables_are_used(monkeypatch):
    """Step 7 must not have changed what `uv run asa` does, and this is where that is pinned.

    The lexicon is an opt-in instrument rather than a replacement: the rule-versus-lexicon
    comparison needs the hand-written decoder available unchanged, and a default that quietly
    became the lexicon would retire one arm of it.
    """
    got = _decode_through(_captured_decoder(monkeypatch, ["--log", "warning"]),
                          "I am delighted")

    assert got.source == "decoder:rule:handwritten"
    assert got.affect.values["happiness"] == 0.9


def test_a_lexicon_artefact_replaces_the_table_and_names_itself(monkeypatch, tmp_path):
    """Both halves of the swap, and the second is what makes the first legible in the data.

    The table changes *and* the recorded source changes with it — read from the artefact
    rather than assumed, so a run cannot claim a lexicon it did not load.
    """
    got = _decode_through(
        _captured_decoder(monkeypatch, ["--log", "warning", "--lexicon", str(_artefact(tmp_path))]),
        "everything felt halcyon",
    )

    assert got.source == "decoder:rule:test-lexicon"
    assert got.affect.values["happiness"] == 0.9        # a word only the artefact holds


def test_a_missing_lexicon_exits_with_a_message(monkeypatch, tmp_path, capsys):
    """An operator problem gets one line and a non-zero exit, as an unreachable Furhat does.

    Somebody who mistyped a path needs the path back, not a traceback through ``json``.

    **``capsys``, not ``caplog``**, and the reason is worth knowing before reaching for the
    obvious fixture: ``setup_logging`` calls ``basicConfig(force=True)``, which clears every
    handler already installed — pytest's capturing handler included — and attaches one of its
    own to stdout. So ``caplog`` sees nothing while the message is plainly there. Asserting on
    stdout also tests the thing an operator actually reads.
    """
    monkeypatch.setattr("asa.cli.run_agent", _unreachable_run_agent)

    with pytest.raises(SystemExit) as exit_info:
        main(["--log", "warning", "--lexicon", str(tmp_path / "absent.json")])

    assert exit_info.value.code == 1
    assert "absent.json" in capsys.readouterr().out


def test_an_artefact_the_loader_refuses_exits_the_same_way(monkeypatch, tmp_path, capsys):
    """A file that loads as JSON but is not this lexicon — the wrong-download case.

    It reaches a different guard from the missing-file test, and must reach the same outcome:
    the two are one situation for whoever is running the agent, whatever the loader thought.
    """
    monkeypatch.setattr("asa.cli.run_agent", _unreachable_run_agent)
    four_only = {"anger": {"sonorous": 0.9}, "fear": {"crepuscular": 0.9},
                 "joy": {"halcyon": 0.9}, "sadness": {"lambent": 0.9}}

    with pytest.raises(SystemExit) as exit_info:
        main(["--log", "warning", "--lexicon", str(_artefact(tmp_path, entries=four_only))])

    assert exit_info.value.code == 1
    assert "anticipation, disgust, surprise, trust" in capsys.readouterr().out


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
