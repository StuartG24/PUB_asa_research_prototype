#
# Test - perception
#

"""Tests for the input port and the text console adapter.

The adapter is a loop around a call, so what is worth testing is not that it reads. It is
the four things other components rely on: that it satisfies the port at all, that it tags
its records with its own name, that end of input *ends* rather than raises — since that is
what tells the evidence loop it may drain — and that reading does not freeze the event
loop, which is the one decision in this module that could be "simplified" away with
nothing failing.
"""

import asyncio
import time

from asa.core.affect import Utterance
from asa.perception.base import InputSource
from asa.perception.text_console import SOURCE, TextConsole


def _scripted(*lines: str):
    """A reader returning each line in turn, then signalling end of input.

    Stands in for ``input``: same signature, same ``EOFError`` at the end, no keyboard.
    """
    remaining = list(lines)

    def read(prompt: str) -> str:
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    return read


async def _collect(source: InputSource) -> list[Utterance]:
    """Drain an adapter to a list — the ``async for`` a driver will run for real."""
    return [utterance async for utterance in source.events()]


def test_text_console_satisfies_the_input_source_port():
    """A protocol claim is a STATIC claim, so this is checked by pyright, not at runtime.

    The annotation is the test. ``isinstance`` against a protocol would only confirm that
    an ``events`` attribute exists — it cannot see the signature or the return type, and
    at step 3b that difference hid a real bug for an afternoon. ``test_types.py`` runs
    pyright over this file, so a signature drifting from the port fails the suite here.
    """
    source: InputSource = TextConsole()

    assert source is not None       # the annotation above is what actually asserts


def test_each_line_becomes_one_utterance_tagged_with_this_adapter():
    """Text through unchanged, and `source` set from the module constant.

    ``source`` is provenance: nothing branches on it, so a wrong value does not change
    behaviour — it mislabels every row this adapter writes, and is found at analysis.
    """
    console = TextConsole(read=_scripted("I just got the job!", "though I am nervous"))
    seen = asyncio.run(_collect(console))

    assert [utterance.text for utterance in seen] == [
        "I just got the job!",
        "though I am nervous",
    ]
    assert {utterance.source for utterance in seen} == {SOURCE}
    assert all(utterance.intended is None for utterance in seen)


def test_end_of_input_ends_the_stream_rather_than_raising():
    """``EOFError`` — Ctrl-D — must terminate the iterator cleanly.

    This is the shutdown signal, not an error condition: the driver's ``async for`` ends,
    perception's task finishes, and only then is the evidence loop allowed to drain. If
    this raised instead, a normal end of session would look identical to a crash and would
    take the drain with it.
    """
    console = TextConsole(read=_scripted())      # end of input immediately
    seen = asyncio.run(_collect(console))

    assert seen == []


def test_blank_lines_are_skipped():
    """Whitespace-only input yields nothing, and surrounding whitespace is trimmed.

    An empty utterance decodes to nothing, so a row for it would sit in
    ``utterances.jsonl`` with no evidence ever pointing at it, meaning only that somebody
    pressed Enter.
    """
    console = TextConsole(read=_scripted("", "   ", "  I just got the job!  ", "\t"))
    seen = asyncio.run(_collect(console))

    assert [utterance.text for utterance in seen] == ["I just got the job!"]


def test_the_blocking_read_does_not_freeze_the_event_loop():
    """The reason for ``asyncio.to_thread``, tested because nothing else would catch it.

    ``input`` blocks the thread it runs on, and the agent has one thread. Called directly,
    it would stop the intention planner, the evidence loop and the render loop for as long
    as a person sat thinking — with no error anywhere, just a robot that goes still
    whenever it is someone's turn to type.

    A concurrent task is the instrument: it can only advance if the event loop is still
    running during the read. Asserted as "more than zero" rather than a count, because the
    number depends on the machine while the property does not — without the thread the
    counter cannot advance at all.
    """
    async def scenario() -> tuple[int, list[Utterance]]:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.005)

        remaining = ["I just got the job!"]

        def slow_read(prompt: str) -> str:
            time.sleep(0.05)            # a person deciding what to say
            if not remaining:
                raise EOFError
            return remaining.pop(0)

        tick = asyncio.create_task(ticker())
        try:
            seen = await _collect(TextConsole(read=slow_read))
        finally:
            tick.cancel()

        return ticks, seen

    ticks, seen = asyncio.run(scenario())

    assert ticks > 0, "the event loop was frozen for the whole read"
    assert [utterance.text for utterance in seen] == ["I just got the job!"]
