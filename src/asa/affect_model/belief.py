#
# Affect model
#
# The research core, and the sole author of state


"""The model itself: evidence folded into belief, and belief aged.

**The sole author of `AffectState`** (§9.2). Perception, deliberation and the intention planner
all produce *evidence*; none of them writes state. That is what removes the conflict-resolution
problem between two independent authors, and it is why the type system keeps ``AffectEvidence``
and ``AffectState`` apart rather than trusting anyone to remember the difference.

**The model is not a port** (§4). It owns state and a lifetime rather than being a transform, so
nothing declares a Protocol for it and the evidence loop reaches it through the ``StateWriter``
callable alias instead.

**Named ``belief.py`` under §14.1's fourth convention**, not for a strategy. There is no strategy
to name — the model is the region's single occupant and, not being a port, has no alternative to
be one of. ``model.py`` stutters at the import site and a strategy-shaped name such as
``decay_fold.py`` would assert a swappability the architecture declines. ``folding.py`` and
``decay.py`` beside it *are* strategies and follow the ordinary rule.

**It owns no clock** (§9.5). Every instant it works with arrives as a parameter — the evidence's
own ``at``, or the ``t`` a caller asks about. Decay is evaluated lazily at read time, so nothing
runs on a schedule for a belief to be correctly aged when someone looks, and a belief nobody reads
needs no ageing at all. Construction takes ``started_at`` for the same reason: a clock read there
would be a clock read.

**Two markers per target, and v0.6 is why there are two rather than one.**

- ``valid_at`` — the instant the stored value is the belief *for*. Moves on **every** fold, and it
  is what ``state_at`` ages from.
- ``fresh_since`` — when the belief was last renewed by evidence substantial enough to count. Moves
  only when a fold policy says ``refresh``.

v0.5 made the second knob the ageing clock and v0.6 corrected it, because that could not work:
decay composes, so a fold that re-anchors and one that does not give the identical belief at every
later instant — measured at a difference of zero. What the knob genuinely governs is *currency*,
which is a claim about staleness rather than about magnitude. Nothing reads ``fresh_since`` yet
beyond the policy's own ``elapsed_s``; the intention planner and the deliberator are its intended
readers, and it becomes an ``AffectState`` field, and a ``state/3``, when one of them consults it.

**Everything the model does is per target, and the differences are enforced rather than
remembered.** ``EXPRESSED`` is a completed fact rather than an estimate, so it is assigned whole,
it never decays, and it never reaches ``self_``. The first is which policy it maps to; the second
is enforced twice over — ``half_lives`` refuses an ``EXPRESSED`` key at construction, and
``state_at`` never calls ``decayed()`` on it; the third holds because nothing here ever folds one
target's evidence into another's belief.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from asa.affect_model.decay import decayed
from asa.affect_model.folding import FoldPolicy, folded
from asa.core.affect import AffectEvidence, AffectState, AffectVector, Target
from asa.core.representations import AffectRepresentation

DECAYING: tuple[Target, ...] = (Target.OTHER, Target.SELF)
"""The targets that age. Deliberately not "every target except ``EXPRESSED``".

Written as the positive list so that adding a fourth ``Target`` is a decision about whether it
ages, taken here, rather than a default inherited from how the exclusion happened to be phrased.
"""

#
# ── What is stored ──────────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class _Belief:
    """One target's stored value and the two instants that govern it.

    Frozen and replaced rather than mutated, following the same rule as everything else the
    model touches: §9.3 requires the fold to build new objects, and a mutable bookkeeping record
    beside immutable vectors is an invitation to break that by accident.

    Private to this module. It is not an ``AffectState`` — that type is the model's *answer*,
    covering all three targets at one instant, whereas this is one target's working state.
    """

    value: AffectVector
    valid_at: datetime          # the instant `value` is the belief for; moves on every fold
    fresh_since: datetime       # last renewal by substantial evidence; moves only on refresh

#
# ── The model ───────────────────────────────────────────────────────────────────────────
#


class AffectModel:
    """The sole author of ``AffectState``: folds evidence into belief, and ages it."""

    def __init__(self, *, representation: AffectRepresentation,
                 policies: Mapping[Target, FoldPolicy],
                 half_lives: Mapping[Target, float],
                 started_at: datetime) -> None:
        """Build a model at rest, with a policy per target and a half-life per ageing target.

        **No parameter has a default.** Every one of them is a parameter of the behaviour being
        evaluated, so every one must appear in the run manifest — and a defaulted parameter is
        one that can be omitted from a manifest and then differ silently between two runs that
        claim to be the same (§9.5, open question 23). Keyword-only because ``policies`` and
        ``half_lives`` are both mappings keyed by ``Target``, which nothing else could tell apart.

        **The cold start is a belief at rest, not an absent one.** §4 requires ``current`` to
        exist before any evidence, because the planner's first tick may precede the first
        utterance and a reader wanting the value now should never need an empty-state branch.

        Raises if a policy is missing for any target, or if ``half_lives`` does not cover exactly
        the ageing ones — an ``EXPRESSED`` half-life is refused by name, because a record of what
        was commanded has nothing to go stale about and a decay applied to it would be silent.
        """
        missing = set(Target) - set(policies)
        if missing:
            raise ValueError(f"no fold policy for {sorted(missing)}")

        if set(half_lives) != set(DECAYING):
            trouble = ("EXPRESSED must not have a half-life — it is a completed fact, not a "
                       "belief, and holds until the next render replaces it"
                       if Target.EXPRESSED in half_lives
                       else f"expected a half-life for {sorted(DECAYING)}")
            raise ValueError(f"half_lives {sorted(half_lives)} is wrong: {trouble}")

        self._rep = representation
        self._policies = dict(policies)
        self._half_lives = dict(half_lives)

        at_rest = representation.rest_vector()
        self._beliefs = {target: _Belief(value=at_rest, valid_at=started_at,
                                         fresh_since=started_at)
                         for target in Target}

    def observe(self, evidence: AffectEvidence) -> AffectState:
        """Fold one piece of evidence and return the state it produced.

        **Synchronous, and it must stay that way.** Because publishing is synchronous and this is
        a plain callable, the evidence loop has no ``await`` between taking an item off the queue
        and marking it done — so an item is either fully folded and published, or never taken.
        Making this ``async`` would silently destroy that atomicity and reintroduce the shutdown
        hang the loop's ``finally`` exists to prevent.

        One call returning the state, rather than a write followed by a separate query: the loop
        must publish *each fold with the state it produced*, and two calls would let it ask about
        an instant this had not just computed.

        The order is fixed by what each step needs. The belief is aged to the evidence's own
        instant first, so the policy compares like with like and the fold is not mixing a value
        from one moment with an estimate from another. ``elapsed_s`` reports the time since the
        belief was last *renewed*, not since it was last touched — that is the currency §9.3
        defines, and a rule that wanted "how long since anything at all arrived" would be asking
        a question about traffic rather than about evidence.

        Raises if the evidence is older than the belief it would fold into: ageing backwards is
        undefined and §3.4 rules that a raise from the model is a bug rather than a transient, so
        it stops the session instead of writing a value nothing can account for. Also raises,
        through ``folded``, if the evidence's vector names another representation or is missing
        an axis.
        """
        at = evidence.at
        held = self._beliefs[evidence.target]
        aged = self._aged(evidence.target, at)

        decision = self._policies[evidence.target](evidence=evidence,
                                                   belief=aged,
                                                   elapsed_s=(at - held.fresh_since).total_seconds())
        self._beliefs[evidence.target] = replace(held,
                                                 value=folded(belief=aged, estimate=evidence.affect,
                                                              weight=decision.weight, rep=self._rep),
                                                 valid_at=at,
                                                 fresh_since=at if decision.refresh else held.fresh_since)
        return self.state_at(at)

    def state_at(self, at: datetime) -> AffectState:
        """What the model believes at *at* — the one question it answers (§9.1).

        A pure function of the evidence folded so far and the instant asked about, which is what
        lets §12.4 replay a session through a changed model with no clock control at all.

        **It answers now or later, never earlier.** Ageing backwards raises, so a query into the
        past is refused rather than guessed at. That is not a limitation to work around: §9.5
        holds that the past is recovered by *replaying* the evidence, and a live model that
        cheerfully answered about an instant before its own anchor would be inventing the very
        thing replay exists to reconstruct.
        """
        return AffectState(other=self._aged(Target.OTHER, at),
                           self_=self._aged(Target.SELF, at),
                           expressed=self._beliefs[Target.EXPRESSED].value,
                           at=at)

    def _aged(self, target: Target, at: datetime) -> AffectVector:
        """*target*'s stored value, aged to *at* — or returned untouched if it does not age."""
        held = self._beliefs[target]
        if target not in DECAYING:
            return held.value
        return decayed(held.value,
                       elapsed_s=(at - held.valid_at).total_seconds(),
                       rep=self._rep,
                       half_life_s=self._half_lives[target])
