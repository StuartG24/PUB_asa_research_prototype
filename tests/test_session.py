#
# Test - ASASession
#

"""Tests for the interaction session, with the Furhat client faked out.

The real client is replaced by a recorder, so these run in milliseconds against no robot
and no network. What they cover is the logic this project wrote *around* the client — the
protocol dict built by hand in gesture(), the exception mapping, the lifecycle guards —
which is the part that can regress silently.

Tests are plain sync functions driving the coroutines through ``asyncio.run()``. The
project has no pytest-asyncio and an async plugin would buy nothing here.

Anything needing a live robot lives in test_furhat_integration.py.
"""

import asyncio
import logging

import pytest
from furhat_realtime_api import Events
from websockets.exceptions import InvalidMessage

from asa.session import ASASession, FurhatUnreachable


class FakeFurhatClient:
    """Records what the session asks of the client, and can fail connect() on demand."""

    def __init__(self, host, auth_key=None, connect_error=None):
        self.host = host
        self.ws_url = f"ws://{host}:9000/v1/events"
        self.event_handlers = {}
        self.sent_events = []
        self.spoken = []
        self.gestures = []
        self.log_level = None
        self.disconnect_calls = 0
        self._connect_error = connect_error

    def set_logging_level(self, level):
        self.log_level = level

    async def connect(self):
        if self._connect_error is not None:
            raise self._connect_error

    async def disconnect(self):
        self.disconnect_calls += 1

    def add_handler(self, event, handler):
        self.event_handlers.setdefault(event, []).append(handler)

    async def send_event(self, event):
        self.sent_events.append(event)

    async def request_speak_text(self, text, wait=False, abort=False):
        self.spoken.append({"text": text, "wait": wait, "abort": abort})

    async def request_gesture_start(self, name, intensity=1.0, duration=1.0, wait=False):
        self.gestures.append({"name": name, "intensity": intensity,
                              "duration": duration, "wait": wait})


@pytest.fixture
def clients(monkeypatch):
    """Patch the client class; the returned list collects whatever the session builds."""
    created = []

    def factory(host, auth_key=None):
        client = FakeFurhatClient(host)
        created.append(client)
        return client

    monkeypatch.setattr("asa.session.AsyncFurhatClient", factory)
    return created


# ── Actions ──────────────────────────────────────────────────────────────────


def test_gesture_without_wait_asks_for_monitoring(clients):
    """The hand-built event must set monitor=True, or the response events never arrive.

    This is the regression the whole non-waiting branch exists to prevent: the client's own
    request_gesture_start ties "monitor" to "wait", so not blocking would also mean not
    hearing response.gesture.start/end — a fault visible only by reading the logs.
    """
    async def scenario():
        session = ASASession()
        await session.start()
        await session.gesture("Smile", intensity=0.6, duration=2.0)

    asyncio.run(scenario())

    client = clients[0]
    assert client.sent_events == [{
        "type": Events.request_gesture_start,
        "name": "Smile",
        "intensity": 0.6,
        "duration": 2.0,
        "monitor": True,
    }]
    assert client.gestures == []  # deliberately bypassed the client's own method


def test_gesture_with_wait_uses_the_client_method(clients):
    """The blocking path delegates instead, so the two branches cannot be collapsed."""
    async def scenario():
        session = ASASession()
        await session.start()
        await session.gesture("BigSmile", wait=True)

    asyncio.run(scenario())

    client = clients[0]
    assert client.gestures == [{"name": "BigSmile", "intensity": 1.0,
                                "duration": 1.0, "wait": True}]
    assert client.sent_events == []


def test_say_interrupts_and_waits(clients):
    """say() blocks until the utterance ends and aborts whatever was already speaking."""
    async def scenario():
        session = ASASession()
        await session.start()
        await session.say("Hello")

    asyncio.run(scenario())

    assert clients[0].spoken == [{"text": "Hello", "wait": True, "abort": True}]


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_say_before_start_names_the_mistake():
    """The _client guard turns a NoneType AttributeError into something actionable."""
    session = ASASession()
    with pytest.raises(RuntimeError, match="Session not started"):
        asyncio.run(session.say("too early"))


def test_stop_on_unstarted_session_is_safe():
    """stop() on a session that never connected must not raise."""
    asyncio.run(ASASession().stop())


def test_stop_is_idempotent(clients):
    """Calling stop() twice disconnects once and leaves no client attached."""
    async def scenario():
        session = ASASession()
        await session.start()
        await session.stop()
        await session.stop()
        return session

    session = asyncio.run(scenario())

    assert session.furhat is None
    assert clients[0].disconnect_calls == 1


def test_context_manager_stops_on_exception(clients):
    """__aexit__ closes the connection even when the body raises."""
    async def scenario():
        async with ASASession():
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(scenario())

    assert clients[0].disconnect_calls == 1


@pytest.mark.parametrize("error", [
    ConnectionRefusedError(61, "Connect call failed"),
    InvalidMessage("did not receive a valid HTTP response"),
])
def test_connect_failures_become_furhat_unreachable(monkeypatch, error):
    """Both transport exceptions map to one domain error, and the dead client is dropped.

    ConnectionRefusedError means nothing is listening; InvalidMessage means something that
    is not a Furhat holds the port. One problem to a caller, two exceptions on the wire.
    """
    monkeypatch.setattr("asa.session.AsyncFurhatClient",
                        lambda host, auth_key=None: FakeFurhatClient(host, connect_error=error))

    session = ASASession()
    with pytest.raises(FurhatUnreachable) as raised:
        asyncio.run(session.start())

    assert session.furhat is None
    assert "ws://127.0.0.1:9000/v1/events" in str(raised.value)
    assert raised.value.__cause__ is error


# ── Wiring ───────────────────────────────────────────────────────────────────


def test_speech_and_gesture_handlers_are_both_registered(clients):
    """Gesture has the same event coverage as speech, and must keep it."""
    asyncio.run(ASASession().start())

    assert set(clients[0].event_handlers) == {
        Events.response_speak_start,
        Events.response_speak_end,
        Events.response_gesture_start,
        Events.response_gesture_end,
    }


def test_client_log_level_is_applied(clients):
    """The session hands its configured level to the client rather than leaving the default."""
    asyncio.run(ASASession(client_log_level=logging.WARNING).start())

    assert clients[0].log_level == logging.WARNING


def test_library_stderr_handler_is_removed(clients):
    """start() strips the handler the library attaches, so records are not logged twice.

    The library re-adds it on every construction ("if not self.logger.handlers"), so this
    has to happen per-session — clearing once at import time would not hold.
    """
    library_logger = logging.getLogger("AsyncFurhatClient")
    library_logger.addHandler(logging.NullHandler())
    assert library_logger.handlers

    asyncio.run(ASASession().start())

    assert library_logger.handlers == []
