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
And:
- uv run python -m asa

"""

import argparse
import asyncio
import logging
from pathlib import Path

from asa._tools.custom_logging import setup_logging
from asa.core.config import load_config
from asa.session import ASASession, FurhatUnreachable

log = logging.getLogger(f"{__name__}.app")


def main(argv: list[str] | None = None) -> None:
    """Build the Articial Social Agent
    - Virtual Furhat
    - An interaction session

    ``argv`` defaults to None, which makes argparse read the real ``sys.argv`` — the
    behaviour both entry points need. Passing an explicit list lets a test (or any other
    caller) drive main() without argparse picking up the *host* process's arguments.
    """
    # Get CLI parameters
    args = build_parser().parse_args(argv)

    # Setup custom logging
    setup_logging(level=args.log.upper())

    # Resolve configuration, then let any explicit argument win over it. Three layers
    # in all — packaged defaults, override file, command line — and this is the only
    # place the last one is applied, so load_config() stays usable from a notebook.
    config = load_config(args.config)
    host = args.host or config.furhat_host

    log.info("ASA Launch - Design %s, Furhat Host %s", config.design_version, host)

    # Run the session. This is the only place that owns an event loop — run_session and
    # ASASession are both loop-agnostic, so a notebook (which already has one) can await
    # the same pieces directly.
    try:
        asyncio.run(run_session(host=host,
                                client_log_level=getattr(logging, args.log.upper())))
    except FurhatUnreachable as error:
        # An unreachable Furhat is an operator problem, not a defect — one line and a
        # non-zero exit is more use than a traceback through asyncio and websockets.
        log.error("%s", error)
        raise SystemExit(1) from None


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
    return parser


async def run_session(host: str, client_log_level: int) -> None:
    """Start a session, run the interaction, then stop it — the three phases, spelled out."""
    session = ASASession(host=host, client_log_level=client_log_level)

    # start() sits outside the try deliberately: if the connection never opened there is
    # nothing to clean up, and start() has already dropped the dead client itself.
    await session.start()

    try:
        await interaction(session)
    finally:
        # finally, not merely a trailing call — an exception part-way through the
        # interaction must still close the websocket, or the Furhat is left half-connected.
        await session.stop()


async def interaction(session: ASASession) -> None:
    """What the agent actually does — a placeholder until the real agent logic lands.

    This is the equivalent of a notebook's middle cells: everything between start and stop.
    It takes an already-started session rather than creating one, so it never has to care
    how the connection was made, and the same body can be pasted into a notebook cell.
    """
    # gesture() does not wait, so the smile plays *while* the line is spoken rather than
    # before it — one turn rather than two.
    await session.gesture("Smile", intensity=0.6, duration=2.0)
    await session.say("Hello, this is a second test")
