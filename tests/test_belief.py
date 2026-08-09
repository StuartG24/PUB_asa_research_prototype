#
# Test - the affect model
#

"""Tests for the model that owns belief: folding, ageing, and the two markers.

Four kinds of thing are worth testing here, and one deliberately is not.

The **contract the rest of the architecture leans on** — a belief exists before any evidence,
one call returns the state it produced, and evidence reaches only its own target. The
**guards**, which turn claims made in prose into things that cannot be configured wrongly. The
**lazy ageing**, including the two cases that are only claims until something checks them:
`EXPRESSED` never decaying, and a query into the past being refused rather than guessed. And
**the two markers**, which is v0.6's correction and the one behaviour that could not exist at
all under v0.5's definition of `refresh`.

Not tested: the fold arithmetic and the decay curve, which belong to `test_folding.py` and
`test_decay.py`. Duplicating them here would mean two tests failing per cause, and the seam
guards are exercised through the model only once, to confirm it surfaces them rather than
swallowing them.
"""

from datetime import UTC, datetime, timedelta

import pytest

from asa.affect_model.belief import AffectModel
from asa.affect_model.folding import Assign, ConfidenceWeighted, FoldDecision, FoldPolicy
from asa.core.affect import AffectEvidence, AffectVector, Target
from asa.core.representations import BASIC4, EKMAN6, AffectRepresentation

T0 = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
HALF_LIFE = 45.0


def _t(seconds: float) -> datetime:
    """An instant *seconds* after the model was built. Every time in these tests is explicit —
    the model owns no clock, so nothing here needs one either."""
    return T0 + timedelta(seconds=seconds)


def _vector(**axes: float) -> AffectVector:
    """A complete ``ekman6/1`` vector, at rest unless an axis is named."""
    values = dict(EKMAN6.rest_vector().values)
    values.update(axes)
    return AffectVector(representation=EKMAN6.id, values=values)


def _evidence(target: Target, *, happiness: float, seconds: float,
              confidence: float | None = None) -> AffectEvidence:
    """One piece of evidence about *target*, at a stated instant."""
    return AffectEvidence(target=target, affect=_vector(happiness=happiness),
                          confidence=confidence, at=_t(seconds), source="test:decoder")


def _model(other: FoldPolicy | None = None, self_: FoldPolicy | None = None) -> AffectModel:
    """A model at rest at ``T0``. Any target not given a policy assigns."""
    return AffectModel(representation=EKMAN6,
                       policies={Target.OTHER: other or Assign(),
                                 Target.SELF: self_ or Assign(),
                                 Target.EXPRESSED: Assign(),
                                 },
                       half_lives={Target.OTHER: HALF_LIFE, Target.SELF: HALF_LIFE},
                       started_at=T0)


class _Recorder:
    """A real policy, wrapped to record the ``elapsed_s`` it was handed on each call.

    Currency has no reader in iteration 1 beyond the policy's own argument, so this is the only
    place it is observable — which is exactly what makes it worth pinning now rather than when
    the planner arrives and a wrong answer becomes a wrong expression.
    """

    def __init__(self, inner: FoldPolicy) -> None:
        self.inner = inner
        self.elapsed: list[float] = []

    def __call__(self, *, evidence: AffectEvidence, belief: AffectVector,
                 elapsed_s: float) -> FoldDecision:
        self.elapsed.append(elapsed_s)
        return self.inner(evidence=evidence, belief=belief, elapsed_s=elapsed_s)

#
# ── The contract ────────────────────────────────────────────────────────────────────────
#


def test_a_belief_exists_before_any_evidence():
    """§4's cold start. The planner's first tick may precede the first utterance, so a reader
    wanting the value now must never need an empty-state branch."""
    state = _model().state_at(T0)

    assert state.other == EKMAN6.rest_vector()
    assert state.self_ == EKMAN6.rest_vector()
    assert state.expressed == EKMAN6.rest_vector()
    assert state.at == T0


def test_the_cold_start_is_at_rest_and_not_at_zero():
    """A third representation, because the two declared ones cannot tell the difference.

    `basic4/1` and `ekman6/1` both rest at 0.0, so a model that hardcoded a zero vector would
    pass every other test in this file. "Start at zero" reads as a universal truth and is not
    one: in a dimensional representation zero is a *position*, and on a 0–1 scaling a valence of
    zero is maximally negative — so a model starting every belief there would open every session
    in misery and raise nothing. That is the mistake `rest` exists to prevent, and this is the
    only test that can see it.
    """
    off_zero = AffectRepresentation(id="test/1", axes=("mood",), value_range=(0.0, 1.0),
                                    rest=0.4, metric=False)
    model = AffectModel(representation=off_zero,
                        policies={target: Assign() for target in Target},
                        half_lives={Target.OTHER: HALF_LIFE, Target.SELF: HALF_LIFE},
                        started_at=T0)

    state = model.state_at(T0)

    assert state.other.values["mood"] == pytest.approx(0.4)
    assert state.self_.values["mood"] == pytest.approx(0.4)
    assert state.expressed.values["mood"] == pytest.approx(0.4)


def test_a_fold_returns_the_state_it_produced():
    """The ``StateWriter`` contract: one call, and the state is the one this fold made.

    Also that asking again gives the same answer — the model is a pure function of the evidence
    folded so far and the instant asked about, which is what lets §12.4 replay with no clock.
    """
    model = _model()

    state = model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=0))

    assert state.at == _t(0)
    assert state.other.values["happiness"] == pytest.approx(0.8)
    assert state == model.state_at(_t(0))


def test_evidence_reaches_only_its_own_belief():
    """`EXPRESSED` is not facial feedback, and the architecture says so structurally.

    Nothing lets what the agent showed reach what it feels, so knowing that it smiled does not
    make it happier. Holding that as a modelling position rather than a consequence of where a
    value was put is the whole reason `EXPRESSED` is a separate target.
    """
    model = _model()

    state = model.observe(_evidence(Target.EXPRESSED, happiness=0.9, seconds=0))

    assert state.expressed.values["happiness"] == pytest.approx(0.9)
    assert state.self_ == EKMAN6.rest_vector()
    assert state.other == EKMAN6.rest_vector()


def test_a_later_fold_leaves_an_earlier_snapshot_untouched():
    """§9.3's hard requirement, and the reason it is a requirement rather than a preference.

    `AffectHistory` promises the reasoning ports a snapshot, and `frozen=True` protects a
    vector's binding but not its `values` mapping. A fold that updated that mapping in place
    would change a snapshot *while a language-model call was in flight against it* — no error,
    just an appraisal that cannot be reproduced from the recorded evidence.
    """
    model = _model()
    first = model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=0))
    before = dict(first.other.values)

    model.observe(_evidence(Target.OTHER, happiness=0.0, seconds=1))

    assert dict(first.other.values) == before


def test_each_target_folds_under_its_own_policy():
    """The per-target table, which is how §9.7's "the policy is per target" is implemented."""
    weighted = ConfidenceWeighted(unstated_confidence=0.25, max_weight=1.0, refresh_above=0.5)
    model = _model(other=weighted)              # SELF keeps the default Assign()

    other = model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=0))
    mine = model.observe(_evidence(Target.SELF, happiness=0.8, seconds=0))

    assert other.other.values["happiness"] == pytest.approx(0.2)     # 0.8 × an unstated 0.25
    assert mine.self_.values["happiness"] == pytest.approx(0.8)      # assigned whole

#
# ── The two markers ─────────────────────────────────────────────────────────────────────
#


def test_hesitant_evidence_moves_the_belief_without_renewing_its_currency():
    """v0.6's correction, and the behaviour that could not exist under v0.5's definition.

    Three folds at 0s, 30s and 60s, none of them substantial enough to renew. The value moves
    every time, but the currency clock keeps running from the start — so the third fold is
    handed 60 seconds, not 30. A talkative appraiser cannot make a belief *look* well-founded
    by repeating itself.
    """
    hesitant = _Recorder(ConfidenceWeighted(unstated_confidence=0.5, max_weight=1.0,
                                            refresh_above=0.9))
    model = _model(other=hesitant)

    for seconds in (0, 30, 60):
        model.observe(_evidence(Target.OTHER, happiness=0.8, confidence=0.3, seconds=seconds))

    assert hesitant.elapsed == [0.0, 30.0, 60.0]
    assert model.state_at(_t(60)).other.values["happiness"] > 0.0    # it did inform


def test_substantial_evidence_renews_the_currency():
    """The contrast, and the third fold is what separates them.

    Identical timing, a confidence above the threshold. Each fold renews, so the clock restarts
    and the third sees 30 seconds where the hesitant run saw 60.
    """
    confident = _Recorder(ConfidenceWeighted(unstated_confidence=0.5, max_weight=1.0,
                                             refresh_above=0.5))
    model = _model(other=confident)

    for seconds in (0, 30, 60):
        model.observe(_evidence(Target.OTHER, happiness=0.8, confidence=0.9, seconds=seconds))

    assert confident.elapsed == [0.0, 30.0, 30.0]

#
# ── Ageing, and what does not age ───────────────────────────────────────────────────────
#


def test_a_belief_ages_with_nobody_ticking():
    """Lazy evaluation (§9.5): nothing runs on a schedule, and the answer is still right.

    No clock, no tick and no component witnessing the decay between the fold and the question.
    """
    model = _model()
    model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=0))

    assert model.state_at(_t(HALF_LIFE)).other.values["happiness"] == pytest.approx(0.4)


def test_what_the_agent_expressed_does_not_age():
    """A completed fact has nothing to go stale about; it holds until the next render."""
    model = _model()
    model.observe(_evidence(Target.EXPRESSED, happiness=0.7, seconds=0))

    for seconds in (HALF_LIFE, 100 * HALF_LIFE):
        assert model.state_at(_t(seconds)).expressed.values["happiness"] == pytest.approx(0.7)


def test_a_query_into_the_past_is_refused():
    """§9.5's position, holding structurally rather than by convention.

    The past is recovered by *replaying* the evidence. A live model that answered about an
    instant before its own anchor would be inventing the thing replay exists to reconstruct.
    """
    model = _model()
    model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=60))

    with pytest.raises(ValueError, match="elapsed_s"):
        model.state_at(_t(10))


def test_evidence_older_than_the_belief_is_refused():
    """Ageing backwards is undefined, so it stops the session rather than writing a value
    nothing can account for — §3.4 rules that a raise from the model is a bug, not a
    transient, and producers stamp `at` at creation so a violation is one."""
    model = _model()
    model.observe(_evidence(Target.OTHER, happiness=0.8, seconds=60))

    with pytest.raises(ValueError, match="elapsed_s"):
        model.observe(_evidence(Target.OTHER, happiness=0.2, seconds=10))

#
# ── Construction guards ─────────────────────────────────────────────────────────────────
#


def test_refuses_a_half_life_for_what_was_expressed():
    """"`EXPRESSED` never decays" stops being a thing to remember: it cannot be configured.

    Enforced twice over — here, and by `state_at` never calling `decayed()` on it. One of the
    two alone would be a convention; together the claim has nowhere to fail.
    """
    with pytest.raises(ValueError, match="EXPRESSED must not have a half-life"):
        AffectModel(representation=EKMAN6,
                    policies={target: Assign() for target in Target},
                    half_lives={Target.OTHER: HALF_LIFE, Target.SELF: HALF_LIFE,
                                Target.EXPRESSED: HALF_LIFE},
                    started_at=T0)


def test_rejects_a_missing_fold_policy():
    """A target with no policy would fail on the first evidence of that kind rather than at
    construction — which in the case of `SELF` means mid-session, once the planner first acts."""
    with pytest.raises(ValueError, match="no fold policy"):
        AffectModel(representation=EKMAN6,
                    policies={Target.OTHER: Assign(), Target.SELF: Assign()},
                    half_lives={Target.OTHER: HALF_LIFE, Target.SELF: HALF_LIFE},
                    started_at=T0)


def test_rejects_an_incomplete_half_life_table():
    """The mirror of the `EXPRESSED` guard: everything that ages must say how fast."""
    with pytest.raises(ValueError, match="expected a half-life"):
        AffectModel(representation=EKMAN6,
                    policies={target: Assign() for target in Target},
                    half_lives={Target.OTHER: HALF_LIFE},
                    started_at=T0)


def test_evidence_in_another_representation_is_surfaced_not_swallowed():
    """The seam guard belongs to `folded()`; this only checks the model does not absorb it.

    One representation per run (§11), and `AffectState` holds a single vector per target, so
    there is nowhere for a second one to go even if it were wanted.
    """
    model = _model()
    wrong = AffectVector(representation=BASIC4.id, values=dict.fromkeys(BASIC4.axes, 0.5))

    with pytest.raises(ValueError, match="estimate names 'basic4/1'"):
        model.observe(AffectEvidence(target=Target.OTHER, affect=wrong,
                                     at=_t(0), source="test:decoder"))
