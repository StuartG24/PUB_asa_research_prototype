#
# Test - Furhat integration
#

"""End-to-end test against a real (virtual) Furhat.

Skipped automatically unless a Furhat websocket answers on the Furhat port, so a plain
``uv run pytest`` stays green with the SDK closed. A skip rather than a failure is the
point: the suite must not go red because the launcher happens not to be open.

This is the only test that can catch *protocol drift*. A fake will accept ``monitor: True``
forever even if the robot stops honouring it; only the robot can say otherwise.

It makes the Furhat speak and gesture. Start the launcher to enable it.
"""

import asyncio
import base64
import secrets
import socket

import pytest
from furhat_realtime_api import Events

from asa.session import ASASession

FURHAT_HOST = "127.0.0.1"
FURHAT_PORT = 9000
FURHAT_PATH = "/v1/events"


def _furhat_listening(timeout: float = 0.5) -> bool:
    """True if a **websocket** answers on the Furhat port — not merely that something does.

    **The earlier version asked the wrong question and it bit.** It opened a TCP connection
    and returned ``True`` if anything accepted, which is not "is Furhat there" but "is the
    port busy". A Jupyter kernel launched from this repository's own ``.venv`` takes port
    9000 and answers TCP happily — so opening a notebook made the guard report a robot,
    the test run, and the suite go **red on a routine action**, with an error about the
    launcher that pointed nowhere near the cause.

    So the guard completes an HTTP Upgrade handshake and insists on ``101 Switching
    Protocols``. A kernel accepts the connection and then says nothing, which times out; a
    plain HTTP server answers 200 or 404; either way this returns ``False`` and the test
    skips, which is what it should always have done.

    **Deliberately raw rather than reusing ``ASASession``.** Probing with the code under test
    would mean a broken session made this test *skip* instead of fail — turning the one test
    that can catch protocol drift into one that silently excuses it. The handshake here
    shares no code with what it guards.

    ``socket.timeout`` is a subclass of ``OSError``, so the no-answer case needs no separate
    branch.
    """
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    request = (
        f"GET {FURHAT_PATH} HTTP/1.1\r\n"
        f"Host: {FURHAT_HOST}:{FURHAT_PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    try:
        with socket.create_connection((FURHAT_HOST, FURHAT_PORT), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request.encode("ascii"))
            status = sock.recv(64)
    except OSError:
        return False

    return status.startswith(b"HTTP/1.1 101")


pytestmark = pytest.mark.skipif(
    not _furhat_listening(),
    reason=f"no Furhat on {FURHAT_HOST}:{FURHAT_PORT} — start the Furhat launcher",
)


def test_session_round_trip():
    """Connect, gesture, speak and disconnect against the live robot.

    The gesture assertion is the one that matters: response.gesture.end only arrives if the
    robot honoured the monitor flag our non-waiting branch sets by hand. If the protocol
    changes, this fails here rather than silently going quiet in production logs.
    """
    seen = []

    async def record(event):
        seen.append(event.get("type"))

    async def scenario():
        async with ASASession(host=FURHAT_HOST) as session:
            client = session.furhat
            assert client is not None  # started, so the connection exists

            client.add_handler(Events.response_gesture_end, record)
            client.add_handler(Events.response_speak_end, record)

            await session.gesture("Smile", intensity=0.6, duration=1.0)
            await session.say("Integration test")

            # say() returns on response.speak.end; give the shorter gesture's trailing
            # event a moment to land rather than racing it.
            await asyncio.sleep(0.5)

        return session

    session = asyncio.run(scenario())

    assert Events.response_speak_end in seen, "the robot never reported finishing speech"
    assert Events.response_gesture_end in seen, "monitor flag not honoured — no gesture end"
    assert session.furhat is None, "the context manager should have closed the session"
