#
# Perception driver
#
# The producer task — hear, publish, decode, submit


"""``run_perception`` — the task that drives an input source and a decoder.

Design §3 lists four actors and then adds *"plus producer tasks — the input adapters —
which only ever write"*. This is that producer task. It is the only module in
``perception/`` that is neither a port nor a strategy: the adapters know how to hear and
the decoder knows how to interpret, and neither of them knows it is part of an agent.

**One driver module per package, beside the strategies it drives.** Driving from the
composition root instead would put a loop somewhere that cannot be tested without standing
up the CLI, and driving from ``core/loops.py`` is forbidden outright — ``core/`` may not
import ``perception/``, so both ports would have to be flattened into ``Callable`` aliases
at exactly the place a reader wants to see their names.
"""

import logging
from collections.abc import Callable

from asa.core.affect import AffectEvidence
from asa.core.observers import Observers
from asa.perception.base import AffectDecoder, InputSource

log = logging.getLogger(f"{__name__}.app")


async def run_perception(source: InputSource,
                         decoder: AffectDecoder,
                         submit: Callable[[AffectEvidence], None],
                         observers: Observers) -> None:
    """Hear an utterance, record it, interpret it, put the result on the evidence queue.

    **The utterance is published before the decode is attempted**, so a decoder that fails
    leaves an utterance row with no evidence row after it. That is the same signature the
    evidence loop already gives a fold that did not complete, read the same way, and it
    costs no extra field to say it.

    **A failing decoder is contained here, where a failing state writer is fatal there**,
    and the asymmetry is the design's rather than a preference. §9.4 separates the flaky
    components from the deterministic ones on purpose: the decoder becomes an LLM call with
    a network and a timeout, so a failure is a transient and losing one utterance's evidence
    is a gap in the record. The affect model is a pure fold with neither, so a raise from it
    is a bug and continuing would mean an agent that has silently stopped forming beliefs.

    ``except Exception`` rather than ``BaseException``, so cancelling this task at teardown
    stays an ordinary stop instead of being logged as a decoder failure.

    **``submit`` is the bound method, not the ``EvidenceLoop``.** A producer's whole
    business with the transport is one call, and handing over the object would also hand
    over ``drain()`` — which this must never call, since draining waits for the producers to
    have stopped and this one by definition has not. It also means a test of the driver
    needs no evidence loop at all, so a broken loop cannot fail a driver test.

    **Only the utterance is published here.** The evidence derived from it is published by
    the evidence loop on behalf of all three producers, so publishing it here as well would
    put every row in ``evidence.jsonl`` twice with nothing anywhere failing — an error that
    surfaces as an analysis that quietly double-counts.

    **Returning is the signal.** The ``async for`` ends when the source's stream ends, and
    that return is what tells the runtime the producers have stopped, which is what licenses
    it to drain the queue before cancelling the consumer.
    """
    async for utterance in source.events():
        observers.publish(utterance)

        try:
            observation = await decoder.decode(utterance)
        except Exception:
            log.exception("Decoder failed, so no evidence for this utterance: %r", utterance)
            continue

        submit(observation)
