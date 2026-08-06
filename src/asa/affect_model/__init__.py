#
# Affect model
#
# The research core, and the sole author of state — NOT YET BUILT


"""Affective States Modelling — the agent's belief about how both parties feel.

Figure 1's *Affective States Modelling* boxes, all three of them: ``other`` folded from
evidence, ``self_`` written by the intention planner on every decision, and the temporal
dimension as per-axis decay evaluated when state is read rather than on a tick.

**This is a stub, and build step 6 replaces it.** It deliberately does not fold naively.
A placeholder that averaged its inputs would run, publish plausible state rows and leave a
recording indistinguishable from a working agent's — which is the one failure mode research
data cannot survive, because nothing downstream can tell an invented belief from a held one.
Raising makes the missing component missing rather than quietly wrong.

**The model is not a port** (§4). It owns state and a lifetime rather than being a
transform, so nothing declares a Protocol for it and the evidence loop reaches it through
the ``StateWriter`` callable alias instead.
"""

from asa.core.affect import AffectEvidence, AffectState


class AffectModel:
    """The sole author of ``AffectState``: folds evidence into belief, and ages it.

    In the package's ``__init__.py`` rather than a ``model.py``, per §14.1 — ``affect_model.model``
    stutters at every import site, and the model is the package rather than one strategy within it.
    """

    def observe(self, evidence: AffectEvidence) -> AffectState:
        """Fold one piece of evidence and return the state it produced. **Step 6 builds this.**

        **Synchronous, and step 6 must keep it that way.** Because publishing is synchronous
        and this is a plain callable, the evidence loop has no ``await`` between taking an
        item off the queue and marking it done — so an item is either fully folded and
        published, or never taken. Making this ``async`` would silently destroy that
        atomicity and reintroduce the shutdown hang the ``finally`` exists to prevent.

        One call returning the state, rather than a write followed by a separate query: the
        loop must publish *each fold with the state it produced*, and two calls would let it
        ask about an instant this had not just computed.
        """
        raise NotImplementedError(
            "the affect model is build step 6 — the agent can hear and decode, "
            "but cannot yet form beliefs"
        )
