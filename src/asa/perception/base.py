#
# Perception port
#
# The one seam every input adapter satisfies


"""``InputSource`` — the port that text, speech and generated input all satisfy.

One method, and the type it returns is the whole design. An **asynchronous** iterator is
required rather than an ordinary one because the next utterance does not have to be
*computed*, it has to be *waited for*: a person decides when to speak. An ordinary
iterator can only block the single thread while that happens, which would freeze the
render loop and the intention planner along with it.

Structural, like every other port here — an adapter satisfies this by having the method,
never by inheriting. A fake in a test is a class with an ``events`` method and nothing
else.

**Adapters do not publish, and hold no observer registry.** An adapter is a pure source of
``Utterance``s. Publishing belongs to whatever drives it, for the same reason the evidence
loop is the single publisher of evidence: three adapters each remembering to publish is
three chances to forget, and the fourth adapter someone adds later silently loses data.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from asa.core.affect import Utterance


class InputSource(Protocol):
    """Anything that produces utterances, one at a time, taking as long as it needs.

    ``events`` is declared as a plain ``def`` returning an ``AsyncIterator``, which is
    satisfied both by an ``async def`` containing ``yield`` (an async generator function,
    what the adapters here actually are) and by a plain ``def`` handing back somebody
    else's iterator. Both are callables returning an async iterator, which is all this
    asks for.
    """

    def events(self) -> AsyncIterator[Utterance]: ...
