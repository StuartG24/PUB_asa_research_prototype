#
# Affect model — folding
#
# How new evidence enters an existing belief


"""How new evidence moves an existing belief — how far, and whether the ageing clock renews.

A strategy module beside ``belief.py`` (§14.1's ordinary rule) and the companion to
``decay.py``: that one says how a belief ages when nothing arrives, this one says what
happens when something does. ``belief.py`` owns the targets and calls both.

**"Fold" is the functional-programming word, and it is load-bearing.** A fold reduces a
sequence into an accumulator, combining each newcomer *into* what is already there rather
than replacing it — which is exactly §9.3's *fold, never overwrite*. The hazard the rule
exists for: an appraisal computed from the state as it stood at *t₀* arrives at *t₀+2s*, by
which time decay has moved the belief and new utterances have arrived. Assigning that result
silently reverts them, and it corrupts data rather than crashing.

**The fold has TWO independent knobs:

- ``weight`` — how far the belief moves toward the estimate;
- ``refresh`` — whether the *ageing clock* resets to this evidence's ``at``.

They looked like one knob because every fold necessarily re-anchored. Separating them makes a
real behaviour expressible that was not: **evidence may inform a belief without renewing
it.** The case that shows why is a talkative appraiser — repeated low-confidence "still
mildly happy" barely moves the value, yet under a single knob it restarts the fade every time
and the belief never finishes decaying. *"How stale is this?"* has then been quietly
conflated with *"how strong is this?"*.

**What must be right here is the SIGNATURE, not the rule.** The rule is expected to be tuned
throughout the research (open question 23), so ``FoldPolicy`` hands a policy the evidence
*entire* — ``confidence``, ``computed_from``, ``target``, ``source`` and the vector are all
reachable — together with the current belief and the time elapsed since the anchor. Anything
absent from that signature is a change to every caller later, which is the whole cost this
seam exists to avoid. ``elapsed_s`` is consequently accepted and unused by both policies
below: deliberate, and the one place this build accepts a parameter ahead of its first reader.

**``confidence=None`` means *unstated*, and must never resolve to 1.0** (§8.2, §9.3). A
keyword decoder leaves it ``None`` precisely so that it does not look maximally certain
beside an LLM honestly reporting 0.7. Resolving ``None`` to 1.0 would hand maximum influence
to the decoder that declined to answer and make the honest one the weaker, inverting the very
comparison the vocabulary exists to protect. So the resolution is a stated parameter, and
``ConfidenceWeighted`` refuses to be constructed at 1.0 or above — the inversion is
unreachable rather than merely warned against.

**Nothing here knows about targets**, which is the same structural answer ``decay.py`` gives.
The per-target table lives in ``belief.py``, so "``EXPRESSED`` is assigned rather than
weighted" is enforced by which policy it is mapped to, not by a branch inside a policy.
``Assign`` has two consumers on the day it lands — ``EXPRESSED``, which is a fact rather than
an estimate, and ``SELF`` while ``intention.self_fold_weight`` is 1.0 (§11) — so it is not an
``EXPRESSED`` special case.

**Both vectors must carry every axis, and that is stricter than ``decay.py``.** Ageing is
per-axis and independent, so a partial vector ages correctly; a fold *pairs* two vectors, so
an axis present on one side and absent on the other is a question with no answer — "no claim,
leave it alone" and "claimed nothing" are opposite behaviours, and would be settled by
accident. The decoder already guarantees completeness for exactly this reason (§8.4), so the
guard below holds it to its word rather than inventing a new rule.
"""

from dataclasses import dataclass
from typing import Protocol

from asa.core.affect import AffectEvidence, AffectVector
from asa.core.representations import AffectRepresentation

#
# ── The fold itself ─────────────────────────────────────────────────────────────────────
#


def _require_complete(name: str, vector: AffectVector, rep: AffectRepresentation) -> None:
    """Reject a vector that names another representation, or that is missing an axis."""
    if vector.representation != rep.id:
        raise ValueError(
            f"{name} names {vector.representation!r}, but the fold was asked "
            f"against {rep.id!r}"
        )
    if set(vector.values) != set(rep.axes):
        raise ValueError(
            f"{name} carries axes {sorted(vector.values)}, but {rep.id} declares "
            f"{sorted(rep.axes)} — a fold needs every axis on both sides"
        )


def folded(*, belief: AffectVector, estimate: AffectVector,
           weight: float, rep: AffectRepresentation) -> AffectVector:
    """*belief*, moved *weight* of the way toward *estimate*, one axis at a time.

    Returns a **new** ``AffectVector``; neither argument is touched. That is a requirement
    rather than a courtesy — §9.6 promises the reasoning ports a *snapshot*, and an in-place
    fold would change one while a language-model call was in flight against it, giving a torn
    read invisibly: no error, just an appraisal that cannot be reproduced from the recorded
    evidence.

    At ``weight=1.0`` this assigns the estimate; at ``0.0`` it returns the belief unchanged.

    **Every parameter is keyword-only, and *belief* and *estimate* are why.** Both are
    ``AffectVector`` in the same representation, so nothing — not a type checker, not a
    runtime guard — can tell one from the other, and swapping them gives a different, silently
    wrong number for every weight except 0.5. This is ``decay.py``'s two-bare-floats lesson at
    one more seam, except that there a guard was possible and here it is not: keyword-only is
    the whole defence.

    The result's axes are written in ``rep.axes`` order rather than either input's, so a
    record's column order comes from the representation and not from whichever dict happened
    to be built first.

    Raises if either vector names another representation or is missing an axis (see the module
    docstring), or if *weight* falls outside 0.0–1.0 — above 1.0 overshoots past the estimate
    and below 0.0 moves the belief away from it, both of which produce a plausible number and
    no error.
    """
    _require_complete("belief", belief, rep)
    _require_complete("estimate", estimate, rep)
    if not 0.0 <= weight <= 1.0:
        raise ValueError(f"weight must be between 0.0 and 1.0, got {weight}")

    return AffectVector(
        representation=rep.id,
        values={axis: belief.values[axis] + (estimate.values[axis] - belief.values[axis]) * weight
                for axis in rep.axes},
    )

#
# ── The two knobs ───────────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class FoldDecision:
    """What a policy decides about one piece of evidence — §9.3's two knobs, together.

    One type rather than a ``tuple[float, bool]``, because a tuple is unpacked positionally
    and a policy returning them the wrong way round would break nowhere near where it was
    written. Named fields also keep the *reason* for the second knob in the code: the two were
    one knob only because every fold necessarily re-anchored.

    Not keyword-only, unlike ``ConfidenceWeighted`` below, and the difference is not
    inconsistency. The swap that keyword-only would prevent is already caught here by the type
    checker — ``float`` is not assignable to ``bool``, so ``FoldDecision(True, 0.5)`` is a
    reported error. ``ConfidenceWeighted``'s three parameters are all bare floats, where a
    checker can see nothing.
    """

    weight: float       # how far the belief moves toward the estimate, 0.0–1.0
    refresh: bool       # does the ageing anchor reset to this evidence's ``at``?

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be between 0.0 and 1.0, got {self.weight}")

#
# ── The policy seam ─────────────────────────────────────────────────────────────────────
#


class FoldPolicy(Protocol):
    """What ``belief.py`` consults before every fold: evidence in, two knobs out.

    A ``Protocol`` rather than a ``Callable[...]`` alias because the signature is the point
    and ``Callable`` cannot express keyword-only parameters. Structural, as every protocol in
    this build is, so a plain function satisfies it as readily as a class — which is what lets
    a test supply a two-line stub policy without importing anything from here but the return
    type.

    Note what the protocol does and does not pin. It fixes the parameter *names*, since
    keyword-only parameters are passed by name, along with their types, the return type and
    the fact that callers must use keywords. It does **not** force an implementation to
    declare its own parameters keyword-only: a policy accepting them positionally can still be
    called with keywords, so it satisfies the wider contract.
    """

    def __call__(self, *, evidence: AffectEvidence, belief: AffectVector,
                 elapsed_s: float) -> FoldDecision:
        """Decide how far *evidence* moves *belief*, and whether it renews the ageing clock.

        *belief* is the current value — aged to the evidence's own instant, so a policy
        comparing the two is comparing like with like. *elapsed_s* is how long the belief has
        been ageing since its anchor, which is what a rule discounting a well-established
        belief against a fresh reading would need.
        """
        ...

#
# ── Iteration 1's policies ──────────────────────────────────────────────────────────────
#


@dataclass(frozen=True, kw_only=True)
class ConfidenceWeighted:
    """Weight the estimate by how far its producer says it is to be trusted.

    **Provisional, and known to be** — open question 23 asks what function of the available
    inputs actually sets the weight, and what condition ought to make evidence refresh rather
    than merely inform. This is the simplest rule that exercises both knobs honestly, not a
    finding. Whatever it becomes, it is a *recorded* parameter: §9.5's reconstruction
    guarantee fails silently if a manifest cannot name the law the belief was folded under.

    ``refresh_above`` is the talkative-appraiser guard from §9.3. Evidence below the threshold
    still moves the belief, but leaves the fade running.

    **No field has a default**, following ``AffectRepresentation``'s rule for the same reason:
    a defaulted parameter is one that can be omitted from a manifest and then differ silently
    between two runs that claim to be the same.

    ``kw_only=True`` because all three are bare floats in a row. Nothing distinguishes them —
    not the type checker, not any runtime guard — and a swapped pair produces a wrong weight
    rather than an error. Same argument as ``decayed()``'s keyword-only elapsed and half-life.
    """

    unstated_confidence: float      # what ``confidence=None`` resolves to — never 1.0 or above
    max_weight: float               # the weight fully-confident evidence earns
    refresh_above: float            # at or above this confidence, the ageing clock restarts

    def __post_init__(self) -> None:
        if not 0.0 <= self.unstated_confidence < 1.0:
            raise ValueError(
                f"unstated_confidence must be in [0.0, 1.0), got {self.unstated_confidence} "
                "— resolving an unstated confidence to 1.0 would give a decoder maximum "
                "influence for declining to answer (§8.2)"
            )
        if not 0.0 <= self.max_weight <= 1.0:
            raise ValueError(f"max_weight must be between 0.0 and 1.0, got {self.max_weight}")

    def __call__(self, *, evidence: AffectEvidence, belief: AffectVector,
                 elapsed_s: float) -> FoldDecision:
        """Resolve the confidence, then scale the weight by it and threshold the refresh."""
        confidence = (self.unstated_confidence if evidence.confidence is None
                      else evidence.confidence)
        return FoldDecision(
            weight=self.max_weight * confidence,
            refresh=confidence >= self.refresh_above,
        )


@dataclass(frozen=True)
class Assign:
    """Take the estimate whole and restart the clock — for a fact, not an estimate.

    ``belief.py`` maps ``EXPRESSED`` here because what the agent was commanded to convey is a
    completed fact: a record of what was commanded must not drift toward anything, and there
    is nothing for it to be uncertain about. ``SELF`` maps here too while
    ``intention.self_fold_weight`` is 1.0, which §11 sets deliberately for iteration 1 so that
    the recognition stimulus is not muddied by a blended self-state.

    It ignores ``confidence`` entirely, and that is the difference from
    ``ConfidenceWeighted(max_weight=1.0, …)``: a weight-1.0 confidence rule still scales by
    whatever the producer claimed, where this one asserts that the question does not arise.
    """

    def __call__(self, *, evidence: AffectEvidence, belief: AffectVector,
                 elapsed_s: float) -> FoldDecision:
        """Weight 1.0 and a refreshed clock, whatever the evidence says about itself."""
        return FoldDecision(weight=1.0, refresh=True)
