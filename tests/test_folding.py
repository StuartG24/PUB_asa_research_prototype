#
# Test - affect model folding
#

"""Tests for how new evidence moves an existing belief.

Three kinds of thing worth testing. The **arithmetic** — that weight 1.0 assigns, 0.0 is a
no-op and anything between is the proportion it claims to be. The **guards**, which stop a
caller getting a wrong number silently rather than loudly, and which here include one
``decay.py`` does not have: a fold pairs two vectors, so an axis missing from either side is
a question with no answer. And the **policies**, where exactly one claim is not a matter of
taste — §8.2's rule that an unstated confidence must never behave as certainty, because
getting it wrong inverts the comparison the whole `source` vocabulary exists to protect.

Not tested: which weighting rule is *right*, which is open question 23 and expected to be
tuned throughout the research; and composability, which `decay.py` needs and this does not —
folds are order-dependent by design, since that is what "fold, never overwrite" means.
"""

import pytest

from asa.affect_model.folding import Assign, ConfidenceWeighted, FoldDecision, FoldPolicy, folded
from asa.core.affect import AffectEvidence, AffectVector, Target
from asa.core.representations import BASIC4, EKMAN6


def _vector(**axes: float) -> AffectVector:
    """A complete ``ekman6/1`` vector — every axis at rest unless named.

    ``dict.fromkeys`` seeds every axis, so the keys are ``SixEmotions`` members; updating one
    with an equal plain-string key keeps the original key object, which is why a vector built
    this way still writes enum values into a record.
    """
    values = dict.fromkeys(EKMAN6.axes, EKMAN6.rest)
    values.update(axes)
    return AffectVector(representation=EKMAN6.id, values=values)


def _evidence(confidence: float | None = None) -> AffectEvidence:
    """One observation of the human, at a stated confidence or none at all."""
    return AffectEvidence(target=Target.OTHER, affect=_vector(happiness=0.8),
                          confidence=confidence, source="test:decoder")


POLICIES: tuple[FoldPolicy, ...] = (
    ConfidenceWeighted(unstated_confidence=0.5, max_weight=1.0, refresh_above=0.5),
    Assign(),
)
"""Both shipped policies, bound *through the protocol*.

The conformance claim is **static**, so the annotation is the test and `pyright` is what runs
it — which is why `test_types.py` checks `tests/` as well as `src/`. A runtime `callable()`
check would pass for anything at all and would be verifying the claim with a mechanism that
cannot see it.
"""

#
# ── The arithmetic ──────────────────────────────────────────────────────────────────────
#


def test_a_full_weight_assigns_the_estimate():
    """Weight 1.0 is assignment — what `Assign` and `self_fold_weight = 1.0` rely on."""
    belief = _vector(happiness=0.2, sadness=0.6)
    estimate = _vector(happiness=1.0)

    result = folded(belief=belief, estimate=estimate, weight=1.0, rep=EKMAN6)

    assert dict(result.values) == pytest.approx(dict(estimate.values))


def test_a_zero_weight_leaves_the_belief_alone():
    """Weight 0.0 ignores the evidence entirely — the other end of the same knob."""
    belief = _vector(happiness=0.2, sadness=0.6)

    result = folded(belief=belief, estimate=_vector(happiness=1.0), weight=0.0, rep=EKMAN6)

    assert dict(result.values) == pytest.approx(dict(belief.values))


def test_a_half_weight_is_the_midpoint_on_every_axis():
    """Two axes moving in opposite directions, so a sign error cannot pass unnoticed."""
    belief = _vector(happiness=0.2, sadness=0.6)
    estimate = _vector(happiness=1.0, sadness=0.0)

    result = folded(belief=belief, estimate=estimate, weight=0.5, rep=EKMAN6)

    assert result.values["happiness"] == pytest.approx(0.6)     # moved up
    assert result.values["sadness"] == pytest.approx(0.3)       # moved down


def test_returns_a_new_vector_and_leaves_both_inputs_untouched():
    """§9.3's hard requirement: an in-place fold tears a snapshot an LLM call is reading."""
    belief = _vector(happiness=0.2)
    estimate = _vector(happiness=1.0)
    before_belief, before_estimate = dict(belief.values), dict(estimate.values)

    result = folded(belief=belief, estimate=estimate, weight=0.5, rep=EKMAN6)

    assert result is not belief
    assert result is not estimate
    assert result.values is not belief.values
    assert dict(belief.values) == before_belief
    assert dict(estimate.values) == before_estimate


def test_the_result_is_written_in_the_representations_axis_order():
    """The record's column order comes from the representation, not from either input.

    The inputs are deliberately built in reverse, so the assertion cannot pass by accident —
    a dict preserves insertion order, so a fold that copied either input's order would fail.
    """
    reversed_order = AffectVector(representation=EKMAN6.id,
                                  values={axis: 0.1 for axis in reversed(EKMAN6.axes)})
    assert tuple(reversed_order.values) != EKMAN6.axes       # the test has something to catch

    result = folded(belief=reversed_order, estimate=reversed_order, weight=0.5, rep=EKMAN6)

    assert tuple(result.values) == EKMAN6.axes

#
# ── The guards ──────────────────────────────────────────────────────────────────────────
#


def test_rejects_a_vector_naming_another_representation_and_says_which_side():
    """Validate at the seam (decision 4). Naming the side is half the point of the message.

    Both arguments are ``AffectVector``, so "one of them is wrong" would leave the reader
    with two candidates and no way to choose between them.

    **The wrong vector carries ekman6's own axes**, and that is what makes this test isolate
    the guard it names. Handing it a real ``basic4/1`` vector was the first version, and it
    passed with this check deleted — the *completeness* guard fired instead, on the different
    axis set, and its message names the side too. The case here is a record whose
    ``representation`` field is simply wrong, which nothing else can catch. Both ``match``
    patterns pin a fragment unique to this message for the same reason.
    """
    right = _vector(happiness=0.5)
    mislabelled = AffectVector(representation=BASIC4.id,
                               values=dict.fromkeys(EKMAN6.axes, 0.0))

    with pytest.raises(ValueError, match="belief names 'basic4/1'"):
        folded(belief=mislabelled, estimate=right, weight=0.5, rep=EKMAN6)

    with pytest.raises(ValueError, match="estimate names 'basic4/1'"):
        folded(belief=right, estimate=mislabelled, weight=0.5, rep=EKMAN6)


def test_rejects_a_vector_missing_an_axis():
    """Stricter than ``decay.py``, and deliberately so.

    Ageing is per-axis and independent, so a partial vector ages correctly. A fold *pairs*
    two vectors, so an axis on one side and not the other means either "no claim, leave it
    alone" or "claimed nothing" — opposite behaviours, settled by accident if not rejected.
    The decoder already promises completeness for this exact reason (§8.4).
    """
    partial = AffectVector(representation=EKMAN6.id, values={"happiness": 0.5})

    with pytest.raises(ValueError, match="every axis"):
        folded(belief=_vector(), estimate=partial, weight=0.5, rep=EKMAN6)


def test_rejects_a_vector_carrying_an_axis_the_representation_does_not_declare():
    """The half of the completeness guard that fails **silently** without it.

    A missing axis is loud on its own — the fold walks ``rep.axes`` and raises ``KeyError``
    the moment it looks for one that is not there. An extra axis is not: the fold only ever
    reads the axes the representation declares, so an axis nobody declared is dropped
    together with whatever it claimed, and the result looks entirely ordinary. Demonstrated
    with the guard removed: a ``contempt`` of 0.9 vanished and nothing raised.

    Which is the realistic direction of drift, too — a decoder gaining an axis its
    representation has not, rather than losing one.
    """
    extra = AffectVector(representation=EKMAN6.id,
                         values=dict.fromkeys(EKMAN6.axes, 0.2) | {"contempt": 0.9})

    with pytest.raises(ValueError, match="every axis"):
        folded(belief=_vector(), estimate=extra, weight=0.5, rep=EKMAN6)


def test_rejects_a_weight_outside_the_range():
    """Above 1.0 overshoots past the estimate; below 0.0 moves the belief away from it.

    Neither raises on its own — both produce a plausible number in a research record.
    """
    vector = _vector(happiness=0.5)

    with pytest.raises(ValueError, match="weight"):
        folded(belief=vector, estimate=vector, weight=1.5, rep=EKMAN6)

    with pytest.raises(ValueError, match="weight"):
        folded(belief=vector, estimate=vector, weight=-0.1, rep=EKMAN6)


def test_belief_and_estimate_cannot_be_passed_positionally():
    """The one hazard no guard can catch, so keyword-only is the whole defence.

    Both are ``AffectVector`` in the same representation. Swapped, the fold moves the
    *estimate* toward the *belief* — a different answer for every weight except 0.5, with
    nothing to distinguish the two at runtime or statically.
    """
    vector = _vector(happiness=0.5)

    with pytest.raises(TypeError):
        folded(vector, vector, 0.5, EKMAN6)         # type: ignore[misc]


def test_a_decision_cannot_carry_a_weight_outside_the_range():
    """Caught where the policy is written, not one call later where it is used."""
    with pytest.raises(ValueError, match="weight"):
        FoldDecision(weight=1.5, refresh=True)

#
# ── The policies ────────────────────────────────────────────────────────────────────────
#


def test_an_unstated_confidence_never_behaves_as_certainty():
    """§8.2's rule, and the one claim here that is not a matter of taste.

    A keyword decoder leaves ``confidence`` as ``None`` precisely so it does not look
    maximally certain beside an LLM honestly reporting 0.7. If ``None`` resolved to 1.0 the
    decoder that declined to answer would gain maximum influence and the honest one would
    become the weaker — inverting the comparison the ``source`` vocabulary exists to protect.
    """
    policy = ConfidenceWeighted(unstated_confidence=0.4, max_weight=1.0, refresh_above=0.5)
    belief = _vector()

    unstated = policy(evidence=_evidence(None), belief=belief, elapsed_s=0.0)
    stated = policy(evidence=_evidence(0.4), belief=belief, elapsed_s=0.0)
    certain = policy(evidence=_evidence(1.0), belief=belief, elapsed_s=0.0)

    assert unstated.weight == pytest.approx(stated.weight)      # unstated == the parameter
    assert unstated.weight < certain.weight                     # and never == certainty


def test_a_policy_cannot_be_configured_to_resolve_unstated_to_certainty():
    """The inversion above is unreachable, not merely warned against."""
    with pytest.raises(ValueError, match="unstated_confidence"):
        ConfidenceWeighted(unstated_confidence=1.0, max_weight=1.0, refresh_above=0.5)


def test_hesitant_evidence_informs_a_belief_without_renewing_it():
    """The behaviour the second knob exists to express (§9.3, v0.5).

    A talkative appraiser repeating "still mildly happy" should move the belief a little and
    leave the fade running. Under one knob it would restart the ageing clock every time and
    the belief would never finish decaying — "how stale is this?" quietly conflated with
    "how strong is this?".
    """
    policy = ConfidenceWeighted(unstated_confidence=0.2, max_weight=1.0, refresh_above=0.5)
    belief = _vector()

    hesitant = policy(evidence=_evidence(0.3), belief=belief, elapsed_s=0.0)
    confident = policy(evidence=_evidence(0.9), belief=belief, elapsed_s=0.0)

    assert hesitant.weight > 0.0            # it INFORMS
    assert hesitant.refresh is False        # but does not RENEW
    assert confident.refresh is True


def test_assign_ignores_what_the_evidence_claims_about_itself():
    """A fact, not an estimate — so confidence is not a question that arises.

    This is the difference from ``ConfidenceWeighted(max_weight=1.0, …)``, which would still
    scale by whatever the producer claimed.
    """
    policy = Assign()

    for confidence in (None, 0.1, 1.0):
        decision = policy(evidence=_evidence(confidence), belief=_vector(), elapsed_s=99.0)
        assert decision == FoldDecision(weight=1.0, refresh=True)


def test_every_policy_answers_with_both_knobs():
    """The runtime half of the conformance claim above — whatever the rule, both knobs come
    back. The static half is `POLICIES`' annotation, checked by `pyright`."""
    for policy in POLICIES:
        decision = policy(evidence=_evidence(0.6), belief=_vector(), elapsed_s=1.0)

        assert isinstance(decision, FoldDecision)
