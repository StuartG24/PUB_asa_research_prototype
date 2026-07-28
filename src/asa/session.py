#
# Interaction Session
#
# Owns the Furhat connection for the life of one session


"""One interaction session with the (virtual) Furhat.

Async by design: the realtime client is a websocket client, so every action is
awaitable. This class never calls ``asyncio.run`` itself — the caller owns the
event loop, which is what lets the same class run from both entry points:

- CLI, no loop yet — see ``asa.cli.run_session``::
    asyncio.run(run_session(host, level))

- Notebook, loop already running (``asyncio.run`` would raise there)::
    session = await ASASession().start()
    await session.say("Hello")
    await session.stop()

The class provides the connection and the actions; it does not decide *what to say*.
That script lives in the caller — ``asa.cli.interaction`` for the CLI, the middle cells
of a notebook — so the two never have to agree on a conversation.
"""

import logging

from furhat_realtime_api import AsyncFurhatClient, Events
from websockets.exceptions import WebSocketException

log = logging.getLogger(f"{__name__}.app")


class FurhatUnreachable(RuntimeError):
    """The Furhat did not accept a websocket connection.

    Raised in place of the transport's own exceptions so callers do not have to know the
    client is built on websockets. A refused connection (nothing listening) and a failed
    handshake (something else holding the port) are the same problem to a caller, but
    arrive as ``ConnectionRefusedError`` and ``InvalidMessage`` respectively.
    """


class ASASession:
    """A single interaction session with the Furhat."""

    def __init__(self, host: str = "127.0.0.1", *,
                 client_log_level: int = logging.INFO) -> None:
        # Cheap construction only — no I/O, so this is safe to do outside a loop.
        # The connection is opened in start(), which can await.
        self.host = host
        self._client_log_level = client_log_level
        self.furhat: AsyncFurhatClient | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────
    #

    async def start(self) -> "ASASession":
        """Open the websocket and register the event handlers."""
        log.info("Session starting - host %s", self.host)

        self.furhat = AsyncFurhatClient(host=self.host)
        # The client's own logger is separate from ours — it carries the websocket
        # frame traffic, which is very noisy at DEBUG.
        self.furhat.set_logging_level(self._client_log_level)

        try:
            await self.furhat.connect()
        except (OSError, WebSocketException) as error:
            # __aexit__ does not run when __aenter__ raises, so nothing else will clear the
            # dead client — drop it here rather than leave it attached to a failed session.
            endpoint = getattr(self.furhat, "ws_url", f"ws://{self.host}")
            self.furhat = None
            raise FurhatUnreachable(
                f"No Furhat at {endpoint} — is the Furhat launcher running? ({error})"
            ) from error

        self._register_handlers()

        log.debug("Session connected")
        return self

    async def stop(self) -> None:
        """Close the connection. Safe to call twice."""
        if self.furhat is None:
            return

        self.furhat.event_handlers.clear()
        await self.furhat.disconnect()
        self.furhat = None

        log.info("Session stopped")

    async def __aenter__(self) -> "ASASession":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Runs on the exception path too, so a crashed session still disconnects
        # rather than leaking the websocket.
        await self.stop()

    # ── Actions ──────────────────────────────────────────────────────────────
    #

    async def say(self, text: str) -> None:
        """Speak one utterance, interrupting anything already in progress."""
        await self._client.request_speak_text(text=text, wait=True, abort=True)

    # ── Handlers ─────────────────────────────────────────────────────────────
    #
    # Internals, kept below the public surface: nothing outside the class calls these.
    # They are registered by start() and cleared by stop().

    @property
    def _client(self) -> AsyncFurhatClient:
        """The connected client, or a clear error if the session was never started.

        A type checker narrows within a method but not across method boundaries, so it
        cannot see that say() is only ever reached after start() — every use of the
        Optional attribute is flagged. Narrowing here once avoids an assert or an ignore
        in every method, and turns a bare "NoneType has no attribute ..." into a message
        that names the actual mistake — easy to make when start and the actions live in
        separate notebook cells.
        """
        if self.furhat is None:
            raise RuntimeError("Session not started — call start() first")
        return self.furhat

    def _register_handlers(self) -> None:
        self._client.add_handler(Events.response_speak_start, self._on_speak_start)
        self._client.add_handler(Events.response_speak_end, self._on_speak_end)

    async def _on_speak_start(self, event) -> None:
        log.debug("Furhat started speaking: %s", event)

    async def _on_speak_end(self, event) -> None:
        log.debug("Furhat finished speaking: %s", event)
