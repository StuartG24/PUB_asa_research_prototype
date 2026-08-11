#
# Test - affect representations
#

"""Tests for the declared ways of modelling affect.

Two kinds of thing are worth testing here and one is not. The **guards** matter, because a
malformed declaration is a module-level constant shared by every component in the process and
would be wrong for a whole run. The **axis vocabularies** matter, because those strings are
written into research data. What is *not* tested is whether the declarations are the right
ones — that four axes should merge fear with surprise is a research position, not something
a suite can hold to account.

Also deliberately untested: that ``BASIC4.axes == tuple(FourEmotions)``. It is written that
way in the source, so the assertion would restate the line rather than constrain it.
"""

from collections.abc import Mapping

import pytest

from asa.core.affect import AffectVector
from asa.core.representations import (
    BASIC4,
    EKMAN6,
    PLUTCHIK8,
    REPRESENTATIONS,
    AffectRepresentation,
    EightEmotions,
    FourEmotions,
    SixEmotions,
)


def test_the_declared_axis_vocabularies_are_pinned():
    """Whole-vocabulary comparisons, on the same grounds as the facial vocabulary test.

    An axis added or removed silently changes the shape of every record written in that
    representation, and old data becomes incomparable with new without anything failing.
    Pinning the vocabulary whole means such a change has to be a deliberate edit here —
    which is the point, because the reasons for a merged ``fear_surprise`` are invisible at
    the moment somebody would think to split it.

    **Ordered tuples rather than sets, and the order is the half that was missing.** Declared
    order *is* the column order of every record: ``rest_vector()`` builds from ``axes`` and the
    decoder walks ``axes``. A reorder therefore produces two pilots whose columns disagree
    while every ``schema`` tag still matches — the same silent-incomparability failure as an
    added axis, and until this test compared tuples nothing in the suite could see it.

    **Literals rather than a computed check**, and deliberately: ``list(axes) == sorted(axes)``
    would be self-maintaining and would assert the wrong property twice over. It is false for
    ``basic4/1``, which groups its axes rather than alphabetising them, and it would accept a
    change from one stable order to another — where what the design needs is *stability*, not
    alphabetisation. ``SixEmotions`` calls its own order "arbitrary but stable", and stability
    is exactly what a written-down literal enforces and a sort does not.
    """
    assert tuple(axis.value for axis in FourEmotions) == (
        "happiness", "sadness", "fear_surprise", "anger_disgust",
    )
    assert tuple(axis.value for axis in SixEmotions) == (
        "anger", "disgust", "fear", "happiness", "sadness", "surprise",
    )
    assert tuple(axis.value for axis in EightEmotions) == (
        "anger", "anticipation", "disgust", "fear",
        "happiness", "sadness", "surprise", "trust",
    )


def test_axis_names_are_usable_as_str_keys():
    """``AffectVector.values`` is keyed by ``str``, and ``StrEnum`` members hash as values.

    This is what lets a decoder write ``{FourEmotions.HAPPINESS: 0.9}`` for the enum's
    safety while the container stays open to a dimensional vector whose axes are not enum
    members at all. A plain ``Enum`` would hash by member *name* and raise ``KeyError`` on
    the lookup below.
    """
    vector = AffectVector(representation=BASIC4.id, values={FourEmotions.HAPPINESS: 0.9})

    assert vector.values["happiness"] == 0.9
    assert FourEmotions.HAPPINESS == "happiness"
    assert f"{FourEmotions.HAPPINESS}" == "happiness"       # what reaches the JSONL record


def test_axis_names_interoperate_across_representations():
    """The convenience above is also a hazard — and the *annotation* is what hides it.

    Two unrelated ``StrEnum`` classes with equal values produce equal, interchangeable
    mapping keys. Pyright will catch that where it can infer the narrow key type, which the
    ignored line below demonstrates. But a keyword table is annotated ``Mapping[str, ...]``,
    because the decoder has to accept whichever representation's table it is handed — and
    that annotation erases the very distinction the checker was relying on.

    So the hazard is real exactly where the port makes it unavoidable, and no amount of type
    checking will reach it. That is why the decoder compares its table against its
    representation at construction.
    """
    assert FourEmotions.HAPPINESS == SixEmotions.HAPPINESS

    as_the_decoder_sees_it: Mapping[str, float] = {FourEmotions.HAPPINESS: 0.9}
    assert as_the_decoder_sees_it[SixEmotions.HAPPINESS] == 0.9      # nothing objects

    narrowly_typed = {FourEmotions.HAPPINESS: 0.9}                   # inferred as the enum
    assert narrowly_typed[SixEmotions.HAPPINESS] == 0.9              # type: ignore[index]


def test_a_duplicate_axis_is_rejected():
    """A copy-paste error in a declaration, and otherwise entirely silent.

    The zero-fill is keyed by axis, so a duplicated axis simply produces one entry — a
    representation that claims more axes than the vectors it describes ever carry.
    """
    with pytest.raises(ValueError, match="duplicate axis"):
        AffectRepresentation(id="broken/1", axes=("joy", "joy"),
                             value_range=(0.0, 1.0), rest=0.0, metric=False)


def test_a_representation_with_no_axes_is_rejected():
    """Nothing downstream has a sensible response to a representation with no axes."""
    with pytest.raises(ValueError, match="declares no axes"):
        AffectRepresentation(id="empty/1", axes=(),
                             value_range=(0.0, 1.0), rest=0.0, metric=False)


def test_a_rest_point_outside_the_range_is_rejected():
    """Decay heads for ``rest``, so one outside the range is a state no axis can hold."""
    with pytest.raises(ValueError, match="outside its range"):
        AffectRepresentation(id="bad/1", axes=("a",),
                             value_range=(0.0, 1.0), rest=-0.5, metric=False)


def test_an_inverted_range_is_rejected():
    """``(1.0, 0.0)`` is a plausible typo and admits no valid magnitude at all."""
    with pytest.raises(ValueError, match="empty value_range"):
        AffectRepresentation(id="bad/2", axes=("a",),
                             value_range=(1.0, 0.0), rest=0.0, metric=False)


def test_axes_are_coerced_to_a_tuple():
    """The test with teeth: the annotation alone guarantees nothing at runtime.

    ``axes=["a", "b"]`` is accepted by the dataclass and only a type checker objects, so
    without ``__post_init__`` normalising it a module-level constant would hand every
    component in the process a mutable axis order.
    """
    built = AffectRepresentation(id="listy/1", axes=["a", "b"],      # type: ignore[arg-type]
                                 value_range=(0.0, 1.0), rest=0.0, metric=False)

    assert isinstance(built.axes, tuple)
    with pytest.raises(AttributeError):
        built.axes.append("c")                                      # type: ignore[attr-defined]


def test_no_property_may_acquire_a_default():
    """Every declaration must state all five, and this is what keeps that true.

    Adding ``metric: bool = False`` would break nothing visible and would let a dimensional
    representation silently declare itself non-metric — which decides what an error measure
    is allowed to do with it, several components away and long after the fact.
    """
    with pytest.raises(TypeError, match="missing 3 required"):
        AffectRepresentation(id="bad/3", axes=("a",))                # type: ignore[call-arg]


def test_the_registry_is_keyed_by_its_own_identifiers():
    """The lookup an analysis uses on a string read back out of a stream.

    Keys are read off the objects rather than written as literals, so this cannot drift —
    but it can be *undone* by someone typing a key by hand, and then a lookup succeeds and
    returns the wrong representation.
    """
    assert all(key == rep.id for key, rep in REPRESENTATIONS.items())
    assert REPRESENTATIONS[BASIC4.id] is BASIC4
    assert REPRESENTATIONS[EKMAN6.id] is EKMAN6
    assert REPRESENTATIONS[PLUTCHIK8.id] is PLUTCHIK8


def test_ekman6_is_a_strict_subset_of_plutchik8():
    """The fact the whole lexicon plan rests on, pinned so it cannot quietly stop being true.

    Every ``ekman6/1`` axis is also a ``plutchik8/1`` axis, so the coarser table is reached by
    *dropping* two axes and never by combining any. That is what makes deriving one from the
    other selection rather than merging — and it is exactly the property ``restrict`` will
    check, so it is worth asserting once here where the representations are declared rather
    than only where the operation lives.

    ``basic4/1`` is the contrast and belongs in the same test: its merged axes exist in
    neither of the others, so no amount of dropping reaches it.
    """
    assert set(EKMAN6.axes) <= set(PLUTCHIK8.axes)
    assert set(PLUTCHIK8.axes) - set(EKMAN6.axes) == {"anticipation", "trust"}

    assert set(BASIC4.axes) - set(PLUTCHIK8.axes) == {"anger_disgust", "fear_surprise"}


def test_plutchik8_rests_with_every_axis_present():
    """A vector in this representation carries all eight axes, not the six that overlap.

    ``rest_vector()`` is what seeds a belief and what fills a benchmark row's unannotated
    axes, so a representation that built a short vector would put incomplete records into
    research data — and the fold's completeness guard would then reject them at a point far
    from the cause.
    """
    resting = PLUTCHIK8.rest_vector()

    assert resting.representation == "plutchik8/1"
    assert tuple(resting.values) == PLUTCHIK8.axes           # every axis, in declared order
    assert set(resting.values.values()) == {0.0}
