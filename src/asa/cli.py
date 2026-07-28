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

- uv run python -m asa
"""

import argparse
import asyncio
import logging

from asa._tools.custom_logging import setup_logging
from asa.session import ASASession, FurhatUnreachable

log = logging.getLogger(f"{__name__}.app")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. Separate from main() so it can be exercised on its own."""
    parser = argparse.ArgumentParser(description="Run the Artificial Social Agent")
    parser.add_argument("--log", default="debug",
                        choices=["debug", "info", "warning"],
                        help="log verbosity (default: debug)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Furhat address (default: 127.0.0.1, the virtual Furhat)")
    return parser


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
    log.info("ASA Launch")

    # Run the session. This is the only place that owns an event loop — the session
    # itself is loop-agnostic so a notebook (which already has one) can await it.
    try:
        asyncio.run(ASASession(host=args.host,
                               client_log_level=getattr(logging, args.log.upper())).run())
    except FurhatUnreachable as error:
        # An unreachable Furhat is an operator problem, not a defect — one line and a
        # non-zero exit is more use than a traceback through asyncio and websockets.
        log.error("%s", error)
        raise SystemExit(1) from None
