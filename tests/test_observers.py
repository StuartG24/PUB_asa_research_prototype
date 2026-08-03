#
# Test - observer registry
#

"""Tests for the publish-only observer registry.

The registry is a list and a loop, so what is worth testing is not that it calls things —
it is the contract that makes it safe to put in the control path of a live session:
a failing observer must not reach the caller, must not stop its siblings, and must not
disappear silently. The last of those is the one that matters for research data, since a
dropped record is otherwise indistinguishable from a record that never happened.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from asa.core.observers import Event, Observers


@dataclass(frozen=True)
class Ping:
    """A record satisfying ``Event`` structurally, without importing or inheriting it."""

    at: datetime = datetime(2026, 8, 1, 14, 30, tzinfo=UTC)
    schema: str = "ping/1"


def test_a_registered_observer_receives_the_event():
    """The ordinary path: register a callable, publish, it is called with the event."""
    seen: list[Event] = []
    observers = Observers()
    observers.register(seen.append)

    event = Ping()
    observers.publish(event)

    assert seen == [event]


def test_a_late_observer_gets_no_replay_of_earlier_events():
    """Publishing into an empty registry is harmless, and nothing is kept for later.

    Components publish from the moment they are written, so for most of the build the
    registry is empty — that path has to be safe. It also has to be *forgetful*: there is
    no buffering and no replay, so an observer registered after the fact sees only what
    comes next. That is why ``register`` belongs to composition time, and it is what a
    recorder wired up late would silently lose.

    Written as an assertion about replay rather than as a bare call, because "it did not
    raise" cannot distinguish doing nothing from doing something wrong quietly — and
    buffering for late subscribers is a plausible-sounding change that would break what
    the recorder can claim about its own coverage.
    """
    seen: list[Event] = []
    observers = Observers()

    observers.publish(Ping(schema="early/1"))       # nobody listening — must not raise
    observers.register(seen.append)
    observers.publish(Ping(schema="late/1"))

    assert [event.schema for event in seen] == ["late/1"]


def test_a_failing_observer_neither_escapes_nor_stops_its_siblings():
    """The contract: publish-only means an observer cannot affect control flow.

    Both halves matter and they fail independently. Without the ``try``, the exception
    reaches whichever component published — so a broken recorder would take down the
    render loop. With the ``try`` outside the loop rather than inside it, the first
    failure would silently cancel every observer after it.
    """
    seen: list[Event] = []
    observers = Observers()

    def explode(event: Event) -> None:
        raise RuntimeError("disk full")

    observers.register(explode)
    observers.register(seen.append)     # registered after the failure

    observers.publish(Ping())           # must not raise

    assert len(seen) == 1


def test_a_failure_is_logged(caplog: pytest.LogCaptureFixture):
    """"Logged and dropped" has two halves, and the logging half is the one that matters.

    A silently dropped event is a hole in the research data that looks exactly like an
    event that never occurred. This is the only signal that it happened, so its absence
    would be discovered after the participant has gone.
    """
    observers = Observers()

    def explode(event: Event) -> None:
        raise RuntimeError("disk full")

    observers.register(explode)

    with caplog.at_level(logging.ERROR, logger="asa.core.observers.app"):
        observers.publish(Ping())

    assert "event dropped" in caplog.text
    assert "disk full" in caplog.text   # log.exception attaches the traceback


def test_the_failure_handler_does_not_read_the_event():
    """The handler must not become the thing that breaks the caller.

    Building the message from ``event.schema`` would evaluate that attribute *inside* the
    ``except`` block, so an event lacking one would raise from the handler — turning a
    contained observer failure into an uncontained registry failure, which is the one
    thing this class exists to prevent. Passing the event to the logger instead leaves
    formatting to the handler and reads nothing here.

    Nothing type-checks its way to this: ``Event`` is a ``Protocol`` and constrains only
    what Pylance accepts, so an object without a ``schema`` reaches ``publish`` at runtime
    perfectly happily.
    """
    class NoSchema:
        """Publishable by accident — the case the old handler crashed on."""

    observers = Observers()

    def explode(event: object) -> None:
        raise RuntimeError("disk full")

    observers.register(explode)

    observers.publish(NoSchema())       # type: ignore[arg-type]  # must not raise
