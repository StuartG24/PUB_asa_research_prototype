#
# Affect model
#
# The research core, and the sole author of state — NOT YET BUILT


"""The model itself: evidence folded into belief, and belief aged.

**This is a stub, and build step 6 replaces it.** It deliberately does not fold naively.
A placeholder that averaged its inputs would run, publish plausible state rows and leave a
recording indistinguishable from a working agent's — which is the one failure mode research
data cannot survive, because nothing downstream can tell an invented belief from a held one.
Raising makes the missing component missing rather than quietly wrong.

**The model is not a port** (§4). It owns state and a lifetime rather than being a
transform, so nothing declares a Protocol for it and the evidence loop reaches it through
the ``StateWriter`` callable alias instead.

**Named ``belief.py`` under §14.1's fourth convention**, not for a strategy. There is no
strategy to name — the model is the region's single occupant and, not being a port, has no
alternative to be one of. ``model.py`` stutters at the import site and a strategy-shaped
name such as ``decay_fold.py`` would assert a swappability the architecture declines, so
the module is named for what it holds. ``folding.py`` and ``decay.py`` arrive beside it at
step 6 and *are* strategies, so they follow the ordinary rule.
"""

# TODO: In Build step 6 restore the proper implementation commented out  below and remove the temp

# from asa.core.affect import AffectEvidence, AffectState


# class AffectModel:
#     """The sole author of ``AffectState``: folds evidence into belief, and ages it."""

#     def observe(self, evidence: AffectEvidence) -> AffectState:
#         """Fold one piece of evidence and return the state it produced. **Step 6 builds this.**

#         **Synchronous, and step 6 must keep it that way.** Because publishing is synchronous
#         and this is a plain callable, the evidence loop has no ``await`` between taking an
#         item off the queue and marking it done — so an item is either fully folded and
#         published, or never taken. Making this ``async`` would silently destroy that
#         atomicity and reintroduce the shutdown hang the ``finally`` exists to prevent.

#         One call returning the state, rather than a write followed by a separate query: the
#         loop must publish *each fold with the state it produced*, and two calls would let it
#         ask about an instant this had not just computed.
#         """
#         raise NotImplementedError(
#             "the affect model is build step 6 — the agent can hear and decode, "
#             "but cannot yet form beliefs"
#         )

# Temporary testing log

import logging

from asa.core.affect import AffectEvidence, AffectState, AffectVector

log = logging.getLogger(f"{__name__}.app")
_NOT_A_BELIEF = AffectVector(representation="stub/not-a-model", values={})


class AffectModel:
    """The sole author of ``AffectState``: folds evidence into belief, and ages it."""

    def observe(self, evidence: AffectEvidence) -> AffectState:
        # log.warning("Affect model not built (step 6) — returning a stub state, "
        #             "not a belief: %r", evidence)
        log.warning("Affect model not built (step 6) — returning a stub state")
        return AffectState(other=_NOT_A_BELIEF, self_=_NOT_A_BELIEF, at=evidence.at)
