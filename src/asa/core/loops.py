#
# Run loops
#
# The long-lived tasks that move the agent, and how they stop


"""The agent's run loops — the tasks that keep going with nothing asking them to.

Two loops: EvidenceLoop and ResponseLoop (TBC)

The **evidence loop** with long-lived tasks: 
- deliberation on own slow clock
- intention planner on own slow clock

Producers currently are:
- Perception
- Deliberation
- Intention planner

**The evidence queue and the evidence loop are two different things**.
- The queue is an ``asyncio.Queue``: a buffer that producers write to, which takes no decision and knows nothing. 
- The loop is the consumer task that drains it, hands each item to the affect model, 
publishes what happened, and stops cleanly.

``EvidenceLoop`` **owns** its queue rather than being handed one, so producers hold a
``submit`` method and never see the transport. Swapping the queue for a message bus is then
a change in one place instead of one per producer, which is what the design assumes when it
sets out the conditions under which a bus would earn itself.

**Only the loop publishes evidence, whichever producer made it.** 
Producers all submit and none of them holds the observer registry 
Perception publishes the ``Utterance`` and nothing else, because nothing else in the
architecture stores one. This is what keeps one fold to one row in ``evidence.jsonl``: a
producer that also published its own evidence would have its records appear twice, and
nothing anywhere would fail. The error would surface as an analysis that quietly
double-counts.

The **response loop** (TBC)
"""

import asyncio
import logging
from collections.abc import Callable

from asa.core.affect import AffectEvidence, AffectState
from asa.core.observers import Observers

log = logging.getLogger(f"{__name__}.app")

#
# ── AffectEvidenc, EvidenceLoop ─────────────────────────────────────────────────────────
#

StateWriter = Callable[[AffectEvidence], AffectState]
"""The affect model, seen from the loop: evidence in, the resulting belief out.

A callable rather than an import, and that is forced rather than chosen. ``core/`` holds
what every other subpackage may depend on and which depends on none of them, so
``core/loops.py`` cannot import ``affect_model/``. The composition root passes
``model.observe``; a test passes a function.

Named for the guarantee it stands for — the model is the **sole author of ``AffectState``**
— rather than for how it does the job.

Note the shape: one call returns the state it produced, rather than the loop writing and
then asking separately what the state now is. Two calls would let the loop ask about an
instant the model had not just computed, and the design asks it to publish *each fold with
the state it produced* — which is one thing, not two.
"""


class EvidenceLoop:
    """The one queue carrying evidence in, and the task that consumes it.

    Three producers write to it — perception, deliberation and the intention planner — and
    one consumer reads. That is the whole of the transport; there is no second queue, since
    a model that emits nothing has nothing to put on one. Everything that leaves the model
    leaves by being read.
    """

    def __init__(self, state_writer: StateWriter, observers: Observers) -> None:
        self._state_writer = state_writer
        self._observers = observers
        self._queue: asyncio.Queue[AffectEvidence] = asyncio.Queue()

    def submit(self, evidence: AffectEvidence) -> None:
        """Put evidence on the queue, from any producer.

        **Synchronous, because the queue is unbounded** and ``put_nowait`` therefore never
        blocks. Producers need not be async to submit, and none of them can be made to wait
        on the affect model — a slow fold cannot back up into perception.

        The honest cost of unbounded is that there is no back-pressure: a producer that ran
        away would grow the queue until memory ran out, with nothing complaining. With one
        human speaking and two slow clocks that is not a live risk in iteration 1, and a
        bound would trade it for a worse failure — dropped evidence, or a blocked producer.
        """
        self._queue.put_nowait(evidence)

    async def run(self) -> None:
        """Consume evidence forever: publish it, fold it, publish the state that resulted.

        **Evidence is published before the fold, deliberately.** If the model then fails,
        the evidence that killed it is already in the record. It also gives the failure a
        signature readable at analysis with no extra field: an evidence row with no state
        row after it is a fold that did not complete.

        **A failing ``StateWriter`` is fatal, and this is the one place that differs from
        the observer registry.** Observers are contained because they sit outside the
        control path — a broken recorder must not stop the agent. The state writer *is* the
        control path: if it raises, the agent has stopped forming beliefs and will go on
        rendering whatever it last felt, which to a participant is a robot that has quietly
        stopped responding, and in the record is indistinguishable from one that sat still.

        Retrying, or counting failures before giving up, would be answering a question the
        architecture has already answered elsewhere. The model is a deterministic fold over
        evidence with no network and no language model in it — the slow, non-deterministic,
        may-time-out component is deliberation, which produces evidence *before* the queue
        and fails there without reaching this. So a raise here is a bug, not a transient,
        and the useful response is to end the session while an experimenter is in the room.

        Raising is how that is signalled: the composition root runs the actors in a task
        group, which cancels the siblings when a child fails, so the session comes down in
        order rather than the task dying silently the way an unawaited one would.

        ``except Exception`` and not ``BaseException``, so cancelling this task at shutdown
        stays an ordinary stop rather than being logged as a model failure.

        **``task_done`` is in a ``finally`` and that is load-bearing.** ``drain`` waits for
        one ``task_done`` per item taken; skip it on the failing item and the unfinished
        count never reaches zero, so shutdown blocks forever. A fold bug would then present
        as a freeze — the exact symptom the fatal-error policy exists to eliminate.

        Note there is no ``await`` between taking an item and marking it done, because
        publishing is synchronous. Cancellation therefore has nowhere to land inside the
        body: an item is either fully folded and published, or never taken off the queue.
        """
        while True:
            evidence = await self._queue.get()
            try:
                self._observers.publish(evidence)
                state = self._state_writer(evidence)
                self._observers.publish(state)
            except Exception:
                log.exception("Affect model failed — session cannot continue: %r", evidence)
                raise
            finally:
                self._queue.task_done()

    async def drain(self) -> None:
        """Wait until everything submitted so far has been folded and published.

        Shutdown drains rather than cancelling. Evidence sitting on the queue at the end of
        a session was generated by the participant, and cancelling the consumer would lose
        rows that ``utterances.jsonl`` says happened. The composition root therefore stops
        the producers, awaits this, and only then cancels the consumer.

        **Producers must have stopped first.** This returns when the queue is empty and every
        item taken has been marked done, so anything still submitting keeps it waiting.

        **The normal path only — never call this after ``run`` has failed.** The ``finally``
        in ``run`` acknowledges the item in hand, but anything still queued behind it was
        never taken and so will never be acknowledged by anybody. Draining a queue whose
        consumer has died therefore waits forever, converting a clean fatal error into a
        hang. Teardown on that path cancels and closes the streams without draining.
        """
        await self._queue.join()
