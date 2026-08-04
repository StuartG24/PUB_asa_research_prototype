#
# Perception ports
#
# The two seams on the producer side of the cycle


"""``InputSource`` and ``AffectDecoder`` — the seams that let hearing and interpreting move.

Two elements live here. **Multimodal Perception** produces ``Utterance``s;
**Decode & Infer** turns one into an estimate of what the human feels. They are separate
ports because they are separate elements: text, speech and generated input are three ways
of hearing, rule and LLM decoding are two ways of interpreting, and much of the research
consists of varying the second while holding the first fixed.

Structural, like every other port here — an implementation satisfies one of these by having
the method, never by inheriting. A fake in a test is a class with that method and nothing
else.

**Nothing here publishes, and nothing here holds an observer registry.** Both an input
adapter and a decoder are pure producers. Publishing belongs to whatever drives them, for
the same reason the evidence loop is the single publisher of evidence: three adapters each
remembering to publish is three chances to forget, and the fourth that somebody adds later
silently loses data.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from asa.core.affect import AffectObservation, Utterance

#
# ── Multimodal Perception ───────────────────────────────────────────────────────────────
#


class InputSource(Protocol):
    """Anything that produces utterances, one at a time, taking as long as it needs.

    One method, and the type it returns is the whole design. An **asynchronous** iterator
    is required rather than an ordinary one because the next utterance does not have to be
    *computed*, it has to be *waited for*: a person decides when to speak. An ordinary
    iterator can only block the single thread while that happens, which would freeze the
    render loop and the intention planner along with it.

    ``events`` is declared as a plain ``def`` returning an ``AsyncIterator``, which is
    satisfied both by an ``async def`` containing ``yield`` (an async generator function,
    what the adapters here actually are) and by a plain ``def`` handing back somebody
    else's iterator. Both are callables returning an async iterator, which is all this
    asks for.
    """

    def events(self) -> AsyncIterator[Utterance]: ...

#
# ── Decode & Infer ──────────────────────────────────────────────────────────────────────
#


class AffectDecoder(Protocol):
    """One utterance in, one estimate of the human's affect out. Always ``target=OTHER``.

    **Stateless, and that is load-bearing rather than tidy.** A decoder sees the utterance
    and nothing else — no history, no context, no access to the belief it is contributing
    to. It is what makes the planned rule-decoder versus LLM-decoder comparison valid,
    because both see identical input with no memory and neither is confounded by
    accumulated state. Interpretation that depends on prior state — "they said 'fine' but
    they have been sad for ten minutes" — is a genuine research direction and is deferred
    to a later iteration as an explicit claim, not smuggled in here.

    **``async`` for the successor, not for the incumbent.** Iteration 1's decoder is a
    keyword lookup that could not be more synchronous. The port is asynchronous because
    Decode & Infer becomes an LLM inference, and a port whose implementations disagree
    about async-ness cannot be swapped — every caller would have to change with the
    implementation, which is the one thing a port exists to prevent. Awaiting a coroutine
    that never awaits anything itself costs a function call and does not even yield to the
    event loop, so the incumbent pays almost nothing for this.

    **A Protocol with a method, not a ``Callable`` alias**, unlike ``StateWriter`` in
    ``core.loops``. That one is a bare callable because the affect model is one object with
    one entry point; a decoder needs *construction* — an LLM decoder is built with a
    client, a model identifier and a prompt. Iteration 1's keyword decoder will therefore
    have an ``__init__`` that does nothing, which looks like ceremony and is not: it is the
    port paying for its successor, and is not to be "simplified" to a function.

    **Absence and failure are different claims, and only the second raises.** An affectless
    sentence decodes to the zero vector — under a vector representation that *is* "no
    affect expressed", exactly, which is why there is no NEUTRAL axis. A decoder that
    cannot do its job raises instead. For a keyword lookup the two collapse into one and
    the raise never happens; for an LLM decoder they are opposites, and returning a
    fabricated neutral for a timed-out call would put an invented belief into research
    data. The driver contains the raise and carries on, which leaves an utterance row with
    no evidence row after it — the same failure signature a fold that did not complete
    already has, read the same way.

    **The estimate is stamped with the utterance's ``at``, not the moment of decoding.** It
    is a claim about what the human felt when they spoke. A decoder taking most of a second
    would otherwise shift the whole timeline by its own latency, and replaying a recorded
    session through a changed decoder would move the timestamps with it.

    This is also the one producer inside the latency budget: roughly a second from
    end-of-input to expression onset, of which the decode is a part. Deliberation is slow
    and nothing waits for it; this is not.
    """

    async def decode(self, utterance: Utterance) -> AffectObservation: ...
