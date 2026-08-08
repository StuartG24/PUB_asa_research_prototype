#
# Test - affect model decay
#

"""Tests for per-axis exponential decay.

Three kinds of thing worth testing: the **decay property itself** (half-life halves the
distance to rest — the one fact a caller trusts this module for), **composability** (chunked
ageing equals one-shot ageing, which §9.5's reconstruction depends on), and the **guards**
that stop a caller getting a wrong number silently rather than a wrong number loudly.

Not tested: any particular half-life or curve shape being "right" for affect — that is a
research question this module has no opinion on, and question 1 says so explicitly.
"""

import pytest

from asa.affect_model.decay import decayed
from asa.core.affect import AffectVector
from asa.core.representations import BASIC4, EKMAN6, AffectRepresentation

HALF_LIFE = 45.0


def test_one_half_life_halves_the_distance_to_rest():
    """The property the function exists to have — checked against ekman6/1's rest of 0.0."""
    vector = AffectVector(representation="ekman6/1", values={"happiness": 0.8})

    aged = decayed(vector, elapsed_s=HALF_LIFE, rep=EKMAN6, half_life_s=HALF_LIFE)

    assert aged.values["happiness"] == pytest.approx(0.4)


def test_decay_heads_for_a_nonzero_rest():
    """Decay moves TOWARD rest, not toward zero — the property §9.4 exists to state.

    A representation whose rest sits away from zero is what makes the two claims
    distinguishable: heading for zero and heading for rest agree only when rest is zero.
    """
    off_zero = AffectRepresentation(id="test/1", axes=("mood",), value_range=(0.0, 1.0),
                                    rest=0.4, metric=False)
    vector = AffectVector(representation="test/1", values={"mood": 0.9})

    aged = decayed(vector, elapsed_s=1000 * HALF_LIFE, rep=off_zero, half_life_s=HALF_LIFE)

    assert aged.values["mood"] == pytest.approx(0.4, abs=1e-9)


def test_ageing_upward_toward_a_nonzero_rest():
    """A value BELOW rest moves up, not down — decay is toward rest, from either side."""
    off_zero = AffectRepresentation(id="test/1", axes=("mood",), value_range=(0.0, 1.0),
                                    rest=0.6, metric=False)
    vector = AffectVector(representation="test/1", values={"mood": 0.1})

    aged = decayed(vector, elapsed_s=HALF_LIFE, rep=off_zero, half_life_s=HALF_LIFE)

    assert aged.values["mood"] == pytest.approx(0.35)


def test_every_axis_ages_independently():
    """Two axes at different magnitudes age by the same factor, each toward its own start."""
    vector = AffectVector(representation="ekman6/1", values={"happiness": 0.8, "sadness": 0.2})

    aged = decayed(vector, elapsed_s=HALF_LIFE, rep=EKMAN6, half_life_s=HALF_LIFE)

    assert aged.values["happiness"] == pytest.approx(0.4)
    assert aged.values["sadness"] == pytest.approx(0.1)


def test_chunked_ageing_equals_one_shot_ageing():
    """Composability — what §9.5's reconstruction-by-replay depends on.

    Evidence arrives in whatever intervals a conversation happened to have, so ageing by
    30s in one call must equal ageing by 7s, then 3s, then 20s in three.
    """
    start = AffectVector(representation="ekman6/1", values={"happiness": 0.9})

    one_shot = decayed(start, elapsed_s=30, rep=EKMAN6, half_life_s=HALF_LIFE)

    chunked = decayed(start, elapsed_s=7, rep=EKMAN6, half_life_s=HALF_LIFE)
    chunked = decayed(chunked, elapsed_s=3, rep=EKMAN6, half_life_s=HALF_LIFE)
    chunked = decayed(chunked, elapsed_s=20, rep=EKMAN6, half_life_s=HALF_LIFE)

    assert chunked.values["happiness"] == pytest.approx(one_shot.values["happiness"])


def test_returns_a_new_vector_and_leaves_the_original_untouched():
    """The whole reason for a whole-vector signature: no caller can break this by looping."""
    original = AffectVector(representation="ekman6/1", values={"happiness": 0.9})
    before = dict(original.values)

    aged = decayed(original, elapsed_s=HALF_LIFE, rep=EKMAN6, half_life_s=HALF_LIFE)

    assert aged is not original
    assert aged.values is not original.values
    assert dict(original.values) == before


def test_rejects_a_vector_aged_against_the_wrong_representation():
    """Validate at the seam (decision 4) — this is one more seam, not a new rule."""
    wrong = AffectVector(representation="basic4/1", values={"happiness": 0.9})

    with pytest.raises(ValueError, match="basic4/1"):
        decayed(wrong, elapsed_s=HALF_LIFE, rep=EKMAN6, half_life_s=HALF_LIFE)


def test_rejects_negative_elapsed():
    """Out-of-order evidence is not hypothetical — see ``computed_from`` — and must not age
    a belief backwards past where it started."""
    vector = AffectVector(representation="ekman6/1", values={"happiness": 0.9})

    with pytest.raises(ValueError, match="elapsed_s"):
        decayed(vector, elapsed_s=-1.0, rep=EKMAN6, half_life_s=HALF_LIFE)


def test_rejects_a_non_positive_half_life():
    vector = AffectVector(representation="ekman6/1", values={"happiness": 0.9})

    with pytest.raises(ValueError, match="half_life_s"):
        decayed(vector, elapsed_s=HALF_LIFE, rep=EKMAN6, half_life_s=0.0)


def test_arguments_are_keyword_only():
    """The two bare floats are what a caller could swap silently — see the module docstring.

    Keyword-only removes the chance rather than relying on anyone reading the signature
    carefully, which is the same argument decision 4 makes for validating at the seam.
    """
    vector = AffectVector(representation="basic4/1", values={"happiness": 0.9})

    with pytest.raises(TypeError):
        decayed(vector, HALF_LIFE, BASIC4, HALF_LIFE)  # type: ignore[misc]
