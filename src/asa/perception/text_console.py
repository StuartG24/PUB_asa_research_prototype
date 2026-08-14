#
# Text console input
#
# The scope's stated input, and the one that is deterministic and replayable


"""Typed sentences from the terminal, as ``Utterance``s.

The simplest adapter and the one every other component is developed against, because it
is deterministic and replayable in a way a microphone is not.

**The whole difficulty here is that ``input`` blocks.** It stops the thread it is on until
somebody presses Enter, and the agent has exactly one thread — so a bare ``input()`` would
freeze the intention planner, the evidence loop and the render loop for as long as a person
sat thinking. ``asyncio.to_thread`` moves that wait onto a worker thread and gives the
event loop back until it returns. See ``TextConsole.events``.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

from asa.core.affect import Utterance

SOURCE = "input:text_console"
"""This adapter's name, written once.

Declared as a constant rather than repeated at the construction site so that a typo is
wrong for every record this adapter ever writes — visible the first time the data is
looked at — instead of being scattered across call sites with one in ten misspelt.
"""


class TextConsole:
    """Reads lines from the terminal and yields one ``Utterance`` per non-empty line.

    ``read`` is injected so the adapter can be tested without a keyboard, and defaults to
    the built-in ``input``. A callable seam rather than a patched global: the same shape as
    the observer and state-writer seams elsewhere, and a test that monkey-patches
    ``builtins.input`` ends up testing the patch as much as the adapter.
    """

    def __init__(self, prompt: str = "> ", read: Callable[[str], str] = input) -> None:
        self._prompt = prompt
        self._read = read

    async def events(self) -> AsyncIterator[Utterance]:
        """Yield an ``Utterance`` per typed line, until end of input.

        **``asyncio.to_thread(self._read, self._prompt)``, and the argument is passed
        separately for a reason.** ``to_thread`` takes the function *and* its arguments so
        that it can do the calling, on the other thread. Writing
        ``to_thread(self._read(self._prompt))`` would call the reader first, on this
        thread, blocking exactly as if no thread were involved — and then hand the
        resulting string to ``to_thread`` to be called, which fails. The freeze happens
        first and the error second, so the error does not point at the freeze.

        Threads help here only because ``input`` is blocked on **I/O**, during which Python
        releases the interpreter lock. The same trick buys nothing for computation.

        **Known limitation: cancelling this does not stop the read.** The worker thread
        stays blocked in ``input`` until Enter is pressed, and ``asyncio.run`` waits for
        the executor on the way out — so a session torn down while the prompt is waiting
        does not exit until somebody presses a key. Harmless for iteration 1, where
        evaluation is local and an experimenter is in the room, and it never arises on the
        normal path because that path *ends* with end-of-input. It would need revisiting
        for remote delivery.

        **End of input ends the stream** rather than raising. Returning from an async
        generator raises ``StopAsyncIteration`` in the consumer, which ends its
        ``async for`` — and that is the signal that producers have stopped, which is what
        licenses the evidence loop to drain.

        **Blank lines are skipped, not yielded.** An empty utterance decodes to nothing, so
        yielding one would put a row in ``utterances.jsonl`` that no evidence ever refers
        to and that means only "somebody pressed Enter".
        """
        while True:
            try:
                text = await asyncio.to_thread(self._read, self._prompt)
            except EOFError:
                return
            text = text.strip()
            if text:
                yield Utterance(text=text, source=SOURCE)
