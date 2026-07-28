#
# Test - Furhat integration
#

"""End-to-end test against a real (virtual) Furhat.

Skipped automatically unless something is serving on the Furhat websocket port, so a plain
``uv run pytest`` stays green with the SDK closed. A skip rather than a failure is the
point: the suite must not go red because the launcher happens not to be open.

This is the only test that can catch *protocol drift*. A fake will accept ``monitor: True``
forever even if the robot stops honouring it; only the robot can say otherwise.

It makes the Furhat speak and gesture. Start the launcher to enable it.
"""

import asyncio
import socket

import pytest
from furhat_realtime_api import Events

from asa.session import ASASession

FURHAT_HOST = "127.0.0.1"
FURHAT_PORT = 9000


def _furhat_listening(timeout: float = 0.2) -> bool:
    """True if anything accepts a TCP connection on the Furhat port."""
    try:
        with socket.create_connection((FURHAT_HOST, FURHAT_PORT), timeout=timeout):
            return True
    except OSError:
        return False


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
