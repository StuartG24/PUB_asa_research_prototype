#
# Affect model
#
# The research core — the region, not the model


"""Affective States Modelling — the agent's belief about how both parties feel.

Figure 1's *Affective States Modelling* boxes, all three of them: ``other`` folded from
evidence, ``self_`` written by the intention planner on every decision, and the temporal
dimension as per-axis decay evaluated when state is read rather than on a tick.

``AffectModel`` is in ``belief.py`` and imported from there, with ``folding.py`` and
``decay.py`` beside it at step 6. **Nothing is re-exported here**, so a reader tracing
control flow reaches the code by the same path the import line names — see §14.1, whose
fourth convention exists for this package.
"""
