#
# Observers
#
# Publish-only capture, never in the control path


"""The observer registry — how events reach the recorder without reaching the agent.

Every component publishes: 
- perception each ``Utterance``
- the evidence loop each fold with the state it produced
- the response loop each render
- the evaluation prompt each participant report. 
No queue is wrapped, because the events worth recording originate in
four components and no one of them sees the others — the affect model never learns that a
face was rendered, and the response loop never sees the utterance that started it.

This is the one place the design borrows from publish/subscribe, and it borrows only the
half that is free. There are **no topics, no routing, no subscriptions and no
back-pressure**: an observer receives every event and decides for itself what it cares
about. That is what keeps this from being the message bus the design considered and
rejected.

**Publish-only means an observer cannot affect control flow.** One that raises is logged
and dropped, and the next one still runs. There is consequently no error policy to
configure and no ordering question to answer, because nothing downstream is waiting on the
outcome.

The registry knows nothing about affect. ``Event`` is a ``Protocol``, so the record types
satisfy it structurally — this module imports none of them, and none of them import this.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

log = logging.getLogger(f"{__name__}.app")


class Event(Protocol):
    """The shape every publishable record already has: when it happened, and what it is.

    Not a new requirement. ``at`` and ``schema`` sit on every record in ``core`` by the
    convention settled with the affect types; naming that shape here lets ``publish`` be
    typed without this module knowing any of those types, and gives a recorder something
    to route on that is neither an ``isinstance`` check nor an import.

    Structural, so nothing declares that it satisfies this — a record matches by having
    the fields. Deliberately **not** ``@runtime_checkable``: that would imply the registry
    validates what it is handed, when it only ever checks that attributes exist rather
    than their types, which is false confidence for no benefit.

    **Declared as read-only properties, not as bare attributes.** 
    A bare ``at: datetime`` in a protocol means *readable and writable*, 
    which every record here fails, because they are all frozen. 
    Properties ask only to be read — which is all this needs, and what a frozen record can offer. 
    A mutable attribute satisfies a read-only requirement too, so nothing is excluded by asking for less.
    """

    @property
    def at(self) -> datetime: ...

    @property
    def schema(self) -> str: ...


Observer = Callable[[Event], None]
"""A function taking one event and returning nothing.

The ``None`` is the publish-only contract expressed as a type: an observer has no return
value that anybody reads, so there is no channel through which it could influence the
agent. Contrast ``AffectDecoder.decode``, which returns an observation precisely because
the cycle depends on what comes back.
"""


class Observers:
    """A list of callables notified of every event, exceptions logged and dropped.

    **One instance is shared by every publishing component**, rather than one registry
    each. An observer then registers once and the composition root wires a single object;
    the alternative means registering the recorder four times, and once more per component
    added. Since there is no routing, an observer sees everything and filters for itself,
    which is the recorder's job and is keyed on ``Event.schema``.
    """

    def __init__(self) -> None:
        self._observers: list[Observer] = []

    def register(self, observer: Observer) -> None:
        """Add an observer, at composition time rather than while the agent is running."""
        self._observers.append(observer)

    def publish(self, event: Event) -> None:
        """Notify every observer, surviving any that fail.

        **Synchronous deliberately.** A JSONL append is tens of microseconds against a
        render tick of ~100 ms, and capture requires that streams buffer nothing — which
        rules out the background writer an ``async`` signature would otherwise buy. An
        observer that genuinely needs to be slow, such as a dashboard pushing over a
        network, gets its own task; that is a change to the observer, not to this.

        ``Exception`` rather than ``BaseException``, so a broken observer cannot swallow
        ``KeyboardInterrupt`` and stop Ctrl-C working mid-session.

        The event is passed to the logger rather than any attribute of it. ``logging``
        defers formatting to the handler and contains any error it raises there, whereas
        reading ``event.schema`` here would be evaluated inside the ``except`` block — so
        an object without one would raise from the handler and break the very guarantee
        this method exists to make.
        """
        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                log.exception("Observer %r failed — event dropped: %r", observer, event)
