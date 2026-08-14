#
# App Launch
#
# CLI entry point


"""Command-line entry point for asa.
Wired up two ways:
- as the ``asa`` console script (see ``[project.scripts]`` in pyproject.toml);
- via ``python -m asa`` (see ``__main__.py``).

So:
- uv run asa
- uv run asa --log info
- uv run asa --furhat-demo
And:
- uv run python -m asa

**Two paths, and only one of them is the agent.** ``--furhat-demo`` runs the v0.2.0
smile-and-speak check against a real or virtual Furhat. It is the only thing that exercises
the connection outside ``test_furhat_integration.py``, which skips when no robot answers.
It has a deletion date: step 11 refactors ``session.py`` into ``embodiment/furhat.py``
behind the ``Embodiment`` port, and this becomes a test of that adapter instead.
"""

import argparse
import asyncio
import logging
from pathlib import Path

from asa._tools.custom_logging import setup_logging
from asa.affect_model.belief import AffectModel
from asa.affect_model.folding import Assign, ConfidenceWeighted
from asa.core.affect import Target, utc_now
from asa.core.config import load_config
from asa.core.observers import Observers
from asa.core.representations import EKMAN6
from asa.perception.decode_keyword import (
    EKMAN6_KEYWORDS,
    LEXICON_HANDWRITTEN,
    KeywordDecoder,
)
from asa.perception.nrc_eil import load_tables
from asa.perception.text_console import TextConsole
from asa.runtime import run_agent
from asa.session import ASASession, FurhatUnreachable

log = logging.getLogger(f"{__name__}.app")


def main(argv: list[str] | None = None) -> None:
    """Resolve configuration, choose what this run is made of, then run it.

    ``argv`` defaults to None, which makes argparse read the real ``sys.argv`` — the
    behaviour both entry points need. Passing an explicit list lets a test (or any other
    caller) drive main() without argparse picking up the *host* process's arguments.

    **This is the composition root, and it is the only place that names a concrete
    adapter.** Everything below it is handed its collaborators and never chooses one, which
    is what makes the swap-the-robot and swap-the-decoder claims real rather than stated.
    """
    args = build_parser().parse_args(argv)
    setup_logging(level=args.log.upper())

    # Three layers — packaged defaults, override file, command line — and this is the only
    # place the last one is applied, so load_config() stays usable from a notebook.
    config = load_config(args.config)
    host = args.host or config.furhat_host

    log.info("ASA Launch - Design %s, Furhat Host %s", config.design_version, host)

    # The legacy path, self-contained so step 11 can delete this block whole.
    if args.furhat_demo:
        try:
            asyncio.run(furhat_demo(host=host,
                                    client_log_level=getattr(logging, args.log.upper())))
        except FurhatUnreachable as error:
            # An unreachable Furhat is an operator problem, not a defect — one line and a
            # non-zero exit is more use than a traceback through asyncio and websockets.
            log.error("%s", error)
            raise SystemExit(1) from None
        return

    # The agent. EKMAN6 is fixed here until `[affect] representation` lands in configuration
    # (design §11): a config key naming a representation also needs somewhere to pair it
    # with its lexicon, and that has no home yet.
    observers = Observers()
    source = TextConsole()

    # Which table the one algorithm runs over. The built-in tables are the default, so a run
    # without `--lexicon` decodes exactly as it did before step 7 — the lexicon is an opt-in
    # instrument rather than a replacement, and the comparison needs both available unchanged.
    #
    # A flag rather than a hardcoded constant, departing from EKMAN6 above deliberately: that
    # is a research parameter and stable in committed code, whereas a path to an untracked,
    # dated artefact is wrong on another machine and wrong tomorrow. It is also an explicit
    # path and never a discovered one — preparations accumulate by design, so resolving "the
    # newest matching file" would make which instrument a run used depend on what happens to
    # be in the directory.
    if args.lexicon is None:
        table, lexicon = EKMAN6_KEYWORDS, LEXICON_HANDWRITTEN
    else:
        try:
            prepared = load_tables(args.lexicon, [EKMAN6])
        except (OSError, ValueError) as error:
            # A missing file, or an artefact failing the loader's guards, is an operator
            # problem rather than a defect — the same judgement as FurhatUnreachable above.
            # Someone who mistyped a path or prepared the wrong download needs the message,
            # not a stack through json and the mapping checks.
            log.error("%s", error)
            raise SystemExit(1) from None
        table, lexicon = prepared.tables[EKMAN6.id], prepared.source

    # Which instrument decoded a session is as load-bearing for reading a transcript as the
    # design version already logged above, and it is not recoverable from the console output.
    log.info("Decoder lexicon: %s", lexicon)

    decoder = KeywordDecoder(representation=EKMAN6, table=table, lexicon=lexicon)

    # The affect model's parameters are fixed here until `[affect]` lands in configuration
    # (design §11, which currently has no home for three of them). Every value below is a
    # parameter of the behaviour being evaluated and belongs in the run manifest, so this
    # hardcoding is the same provisional arrangement as EKMAN6 above and goes the same way.
    # SELF assigns because §11 sets `self_fold_weight = 1.0` for iteration 1 — a blended
    # self-state would muddy the recognition stimulus. EXPRESSED assigns because it is a fact.
    model = AffectModel(representation=EKMAN6,
                        policies={Target.OTHER: ConfidenceWeighted(unstated_confidence=0.5, max_weight=1.0,
                                                                   refresh_above=0.5),
                                  Target.SELF: Assign(),
                                  Target.EXPRESSED: Assign(),
                                  },
                        half_lives={Target.OTHER: 45.0, Target.SELF: 45.0},
                        started_at=utc_now(),
                        )

    # The only place that owns an event loop, so run_agent stays loop-agnostic and a
    # notebook — which already has one — can await it directly.
    asyncio.run(run_agent(source=source,
                          decoder=decoder,
                          state_writer=model.observe,
                          observers=observers))


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. Separate from main() so it can be exercised on its own."""
    parser = argparse.ArgumentParser(description="Run the Artificial Social Agent")
    parser.add_argument("--log", default="debug",
                        choices=["debug", "info", "warning"],
                        help="log verbosity (default: debug)")
    # No default: None means "not given", so the configured value shows through.
    # Putting the default here would make the argument always present and silently beat every config file.
    parser.add_argument("--host", default=None,
                        help="Furhat address (default: from configuration)")
    parser.add_argument("--config", type=Path, default=None, metavar="FILE",
                        help="TOML file overriding selected configuration keys")
    # An explicit path, never a directory scan: prepared lexicons accumulate, so discovering
    # "the newest one" would let a re-run of the same command decode differently next week.
    parser.add_argument("--lexicon", type=Path, default=None, metavar="FILE",
                        help="prepared lexicon artefact (default: the built-in tables)")
    parser.add_argument("--furhat-demo", action="store_true",
                        help="run the smile-and-speak connection check instead of the agent")
    return parser


# A simple chain of gestures to test
GESTURE_CHAIN = (("BrowRaise", 0.8, 1.0),
                 ("Smile", 0.6, 2.0),
                 ("Nod", 1.0, 5.0),
                 )


async def furhat_demo(host: str, client_log_level: int) -> None:
    """Prove the Furhat connection works: connect, smile, speak, disconnect.

    ``stop()`` is in a ``finally`` rather than a trailing call — a failure part-way through
    must still close the websocket, or the Furhat is left half-connected. ``start()`` sits
    outside the ``try`` deliberately: if the connection never opened there is nothing to
    clean up, and ``start()`` has already dropped the dead client itself.

    ``gesture()`` does not wait, so the smile plays *while* the line is spoken rather than
    before it — one turn rather than two.
    """
    session = ASASession(host=host, client_log_level=client_log_level)
    await session.start()

    try:
        for name, intensity, duration in GESTURE_CHAIN:
            await session.gesture(name, intensity, duration, wait=True)
            await asyncio.sleep(0.5)

        await session.gesture("Smile", intensity=5.0, duration=5.0)
        await session.say("Hello, I hope you are feeling well today. What are your plans?")
    finally:
        await session.stop()
