#
# Runtime
#
# What runs when the agent runs — the long-lived tasks, and the order they stop in


"""Every long-lived task in one place, and the teardown that stops them.

``cli.py`` decides what the agent is *made of*; this decides what it *does*. Read this file
to answer "what is running?" — design §3 lists four actors plus the producer tasks, and the
ones not yet built are named in comments where they will go.

**Nothing here constructs an adapter.** That is what lets a notebook — which already owns an
event loop — drive a whole agent with fakes by awaiting ``run_agent`` directly, and it is
why this module sits above the subpackages rather than inside one: it may import any of
them, and only ``cli.py`` and notebooks import it.
"""

import asyncio

from asa.core.loops import EvidenceLoop, StateWriter
from asa.core.observers import Observers
from asa.perception.base import AffectDecoder, InputSource
from asa.perception.drive import run_perception


async def run_agent(source: InputSource,
                    decoder: AffectDecoder,
                    state_writer: StateWriter,
                    observers: Observers) -> None:
    """Start the actors, run until the input ends, then stop them in the design's order.

    **The teardown order is §3.4's and it is not interchangeable.** Stop the producers,
    drain what they left on the queue, and only then cancel the consumer. Cancelling first
    would discard evidence the participant generated and that ``utterances.jsonl`` says
    happened — a recording that looks complete and is not.

    **A task group is what makes the fatal path work.** ``EvidenceLoop.run`` raises when the
    affect model fails, which cancels this body wherever it has got to. Two consequences,
    both verified rather than assumed: the drain is never reached on that path, so §3.4's
    "never drain after a fatal fold" cannot be violated by forgetting it; and cancelling the
    consumer from inside the body on the *normal* path lets no ``CancelledError`` escape the
    group, so no suppression is needed here.

    Without the cancel, the group would wait forever on a consumer that never returns —
    the session would simply not end.

    **The ``EvidenceLoop`` is constructed here rather than passed in**, unlike the observer
    registry. The composition root chooses what can *vary* — which source, which decoder,
    which model, which observers watch the run. The evidence loop has no alternatives to
    choose between, so requiring every caller to build one correctly first would be
    ceremony rather than composition.

    **Perception is awaited in the body rather than created as a task**, which is correct
    while there is exactly one input source. Step 13's generated source and step 16's speech
    input make that two, at which point they become tasks and the body waits for both.
    """
    evidence_loop = EvidenceLoop(state_writer, observers)

    async with asyncio.TaskGroup() as group:
        consumer = group.create_task(evidence_loop.run())

        # Step 8  — the intention planner, on its own slow clock, submitting SELF evidence
        # Step 10 — the response loop, on its own fast clock, rendering through the embodiment

        await run_perception(source, decoder, evidence_loop.submit, observers)
        await evidence_loop.drain()
        consumer.cancel()
