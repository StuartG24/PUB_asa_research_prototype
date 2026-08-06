#
# Test - runtime
#

"""Tests for the wiring: what runs, and the order it stops in.

This is the first test file that exercises components together rather than one at a time,
and that is deliberate — every claim here is about a *seam*, and a seam is invisible to the
tests either side of it. The parts have their own tests and are not re-tested through here.

The fakes are local rather than the real adapters. A runtime test that used ``TextConsole``
would fail when the console changed, for a reason having nothing to do with the runtime.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from asa.core.affect import (
    AffectEvidence,
    AffectObservation,
    AffectState,
    AffectVector,
    Target,
    Utterance,
)
from asa.core.loops import StateWriter
from asa.core.observers import Event, Observers
from asa.core.representations import BASIC4
from asa.runtime import run_agent

TIMEOUT = 2.0
"""Long enough that no machine fails it, short enough that a hang is a failure not a wait.

Every test here wraps the agent in ``wait_for``, because the failure this file is most
concerned with *is* a hang: a teardown that forgets to cancel the consumer does not raise,
it waits forever, and an unbounded test would take the whole suite with it.
"""


def _rest() -> AffectVector:
    """A vector at rest in the study's representation — content nothing here asserts on."""
    return AffectVector(representation=BASIC4.id, values=dict.fromkeys(BASIC4.axes, BASIC4.rest))


class _ScriptedSource:
    """Yields the given utterances, pausing between them, then ends the stream.

    The pause is not padding. A real source waits for a person to speak, so it yields control
    to the event loop between utterances — and without that the whole script would be
    submitted before the consumer ran once, which is not how a session behaves.
    """

    def __init__(self, *texts: str) -> None:
        self._texts = texts

    async def events(self) -> AsyncIterator[Utterance]:
        for text in self._texts:
            await asyncio.sleep(0.01)
            yield Utterance(text=text, source="input:test")


class _FixedDecoder:
    """Returns one rest-vector observation per utterance, linked back to it."""

    async def decode(self, utterance: Utterance) -> AffectObservation:
        return AffectObservation(target=Target.OTHER, affect=_rest(), source="decoder:test",
                                 of_input=utterance.id, at=utterance.at)


def _recording_writer(folded: list[AffectEvidence]) -> StateWriter:
    """A stand-in affect model: records what it was given, returns a state for it."""
    def write(evidence: AffectEvidence) -> AffectState:
        folded.append(evidence)
        return AffectState(other=evidence.affect, self_=_rest(), at=evidence.at)

    return write


def _run(source: _ScriptedSource, state_writer: StateWriter, observers: Observers) -> None:
    """Run one agent to completion, or fail rather than hang."""
    async def scenario() -> None:
        await asyncio.wait_for(
            run_agent(source=source, decoder=_FixedDecoder(),
                      state_writer=state_writer, observers=observers),
            timeout=TIMEOUT)

    asyncio.run(scenario())


def test_every_utterance_is_folded_before_the_agent_returns():
    """The drain, and the reason it comes before the cancel.

    Returning with work outstanding would be the failure hardest to notice: the
    participant's last turn missing, and a recording that looks exactly like a clean
    shutdown, because a drained queue is what a clean shutdown produces. **Getting the
    order wrong does not produce that, though — it hangs**, verified by swapping the two
    lines. ``drain`` waits for one acknowledgement per item taken off the queue, and a
    cancelled consumer takes no more, so the wait never ends. The loud failure is the lucky
    outcome rather than the designed one, and the ``wait_for`` is what turns it into a named
    failure instead of a suite that never finishes.
    """
    folded: list[AffectEvidence] = []

    _run(_ScriptedSource("one", "two", "three"), _recording_writer(folded), Observers())

    assert len(folded) == 3


def test_the_agent_returns_when_the_input_ends():
    """Termination is a property, not a formality — without the cancel, this hangs forever.

    ``EvidenceLoop.run`` is a ``while True``, and a task group waits for every child before
    it will exit. So an agent whose teardown forgets ``consumer.cancel()`` runs correctly and
    never stops, which at the end of a participant session means a terminal that will not
    come back. The ``wait_for`` is what turns that into a failure instead of a hung suite.
    """
    _run(_ScriptedSource("one"), _recording_writer([]), Observers())


def test_each_input_produces_an_utterance_an_evidence_and_a_state_in_that_order():
    """The whole publish chain, which no single component's tests can see.

    Perception publishes the utterance, the evidence loop publishes the evidence and then the
    state it folded. Three publishers' worth of behaviour, and the order is the record's
    causal order — evidence before the state it produced, and the utterance before both.
    """
    published: list[Event] = []
    observers = Observers()
    observers.register(published.append)

    _run(_ScriptedSource("one", "two"), _recording_writer([]), observers)

    assert [event.schema for event in published] == [
        "utterance/1", "evidence/1", "state/1",
        "utterance/1", "evidence/1", "state/1",
    ]


def test_a_failing_affect_model_ends_the_session_rather_than_hanging():
    """The fatal path, and the hang it is designed to avoid.

    Two things are asserted at once. The error reaches the caller, wrapped in the
    ``ExceptionGroup`` a task group always raises. And it *arrives* — the body may already be
    waiting inside ``drain()`` when the consumer dies, and draining a queue whose consumer is
    dead waits forever, because nothing will ever acknowledge the backlog. The group
    cancelling the body at that ``await`` is what rescues it, so this test is the evidence
    that §3.4's "never drain after a fatal fold" is structural here rather than remembered.
    """
    def explode(evidence: AffectEvidence) -> AffectState:
        raise RuntimeError("the fold failed")

    with pytest.raises(BaseExceptionGroup) as caught:
        _run(_ScriptedSource("one", "two"), explode, Observers())

    assert [type(error) for error in caught.value.exceptions] == [RuntimeError]
