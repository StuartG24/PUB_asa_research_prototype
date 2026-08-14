#
# Affect representations
#
# The declared ways of modelling affect, and the axis names belonging to each


"""How affect is modelled — the axis vocabularies an ``AffectVector`` can be written in.

An ``AffectVector`` carries a ``representation`` identifier and an axis-name → magnitude
mapping. This module declares what those identifiers mean: which axes exist, in what order,
over what range, what an axis decays toward, and whether distance between two vectors means
anything.

**Not called "space", and the reason is a correction rather than a preference.** A space
implies that distance and midpoints are meaningful, and for a categorical representation
they are not — the midpoint between anger and surprise is not an emotion. Calling every
representation a space would misname exactly the case that motivated separating them.
Dimensional representations such as VAD *are* metric, which is precisely why the difference
has to be sayable, and is why ``metric`` is a declared property below rather than a remark.

**Representations are independent by design.** ``FourEmotions`` is not a subset of
``SixEmotions`` and no table, axis or enum is shared: ``basic4/1`` merges fear with surprise
and anger with disgust, which ``ekman6/1`` holds apart. Sharing would have to assert an
equivalence between the two, and that equivalence is a theoretical claim rather than an
implementation convenience — the sort of claim this design refuses to smuggle into a lookup
table. The cost is honest: happiness and sadness appear in both, so a comparison that
differs on *those* may be showing a difference between the tables rather than between the
representations, and the tables should be checked before anything is concluded.

**Class names describe; identifiers attribute where the attribution earns its place.** The
classes are ``FourEmotions`` and ``SixEmotions`` because a class name crediting a theorist
becomes a claim the code has to keep honest, and Ekman's own list did not stay at six. The
identifiers answer to a different reader: they are what appears in recorded data and what an
analyst greps, so ``ekman6/1`` is worth its attribution by being recognisable at a glance
where a described name would need a lookup. ``basic4/1`` gets no attribution because the
merged four-way set is nobody's in particular. The rule behind both: **attribute where the
attribution is recognised, precise and useful to a reader of the data; describe where it is
not.** A Plutchik representation would properly be ``plutchik8/1`` on the same test.

**Adding a representation is a declaration in this module**, not an edit anywhere else. That
is the whole point: the scope names affect coding as one of its extension points, and until
now the axis names lived in ``core/affect.py`` under a universal-sounding name, so every new
way of modelling affect would have meant editing the module every other subpackage depends
on.

**The identifier stays a free ``str`` on the record.** A recorded row may name a
representation this build no longer declares, and it must still load — which is why the
registry below is a lookup rather than the record carrying a reference.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from asa.core.affect import AffectVector

#
# ── The descriptor ──────────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class AffectRepresentation:
    """One declared way of modelling affect: its axes, their range, their rest and its kind.

    **No field has a default, deliberately.** Every declaration must state all five, so that
    a new representation cannot silently inherit a property that happens to be true of the
    two declared here — a dimensional representation quietly picking up ``metric=False``
    would be wrong in a way nothing would report.

    ``rest`` is a single value rather than one per axis. That is sufficient for every
    representation declared here and is the first thing likely to need widening: a
    dimensional representation may well want a different resting value per axis, since
    arousal at rest and valence at rest are not the same claim.

    ``rest`` is also the field that shows why this type had to exist. "Decay toward zero"
    reads as a universal truth and is not one: for an intensity-style representation zero is
    the *absence* of that emotion, so it is genuinely neutral, whereas in a dimensional
    representation zero is a *position*, and on a 0–1 scaling a valence of zero is
    maximally negative. An affect model that decayed every representation toward zero would
    age a neutral person into misery and raise nothing.

    ``metric`` decides what an error measure may legitimately do. Where it is false, an
    aggregate across axes — a mean, and still more a Euclidean distance — asserts a
    commensurability the representation does not have, so accuracy has to be reported per
    axis and categorically. Where it is true, distance is available.

    ``axes`` is **coerced** to a tuple rather than merely annotated as one. These are
    module-level constants shared by every component in the process, so a list passed in
    would hand out a mutable axis order that anything could rewrite — and the annotation
    alone stops nothing at runtime. Same reasoning as ``AffectHistory``: coercing is not a
    departure from the reject-never-coerce rule, because ``tuple(a_list)`` has exactly one
    right answer.

    **Not yet declared, and deliberately so:** whether axes are *bipolar*. Plutchik's wheel
    pairs its eight emotions as four opposites, and an opposite pair is naturally one
    two-ended axis rather than two independent ones — which contradicts the independent
    intensities this container is built on. That is a change to the container, not another
    property of the descriptor, so it waits for a representation that needs it.
    """

    id: str                             # "basic4/1" | "ekman6/1" — what the axis names MEAN
    axes: tuple[str, ...]               # canonical order; the order records are written in
    value_range: tuple[float, float]    # (low, high) an axis magnitude may take
    rest: float                         # what an axis decays toward, in this representation
    metric: bool                        # is distance between two vectors meaningful?

    def __post_init__(self) -> None:
        object.__setattr__(self, "axes", tuple(self.axes))
        if not self.axes:
            raise ValueError(f"{self.id} declares no axes")
        if len(set(self.axes)) != len(self.axes):
            raise ValueError(f"{self.id} declares a duplicate axis: {self.axes}")

        low, high = self.value_range
        if low >= high:
            raise ValueError(f"{self.id} has an empty value_range {self.value_range}")
        if not low <= self.rest <= high:
            raise ValueError(
                f"{self.id} rests at {self.rest}, outside its range {self.value_range}"
            )

    def rest_vector(self) -> AffectVector:
        """Every axis at ``rest`` — this representation's neutral, as a vector.

        Three call sites wanted it before it existed: the affect model's cold start, which must
        hold a belief before any evidence arrives (§4); a benchmark row's unannotated axes; and
        every test that needs a complete vector. Written out three times it would eventually be
        written *wrongly* once — as a zero vector, which is only coincidentally the same thing
        and only for the two representations declared here. That is the exact mistake ``rest``
        exists to prevent, so the descriptor that owns ``rest`` is what should build it.

        **This is the one place ``representations`` reaches into ``affect``, and the direction
        matters.** A representation knowing how to make a container is the specific knowing the
        general. The reverse would not be: ``affect`` stays entirely ignorant of what any
        identifier means, which is what lets a recorded row name a representation this build no
        longer declares and still load.
        """
        return AffectVector(representation=self.id,
                            values=dict.fromkeys(self.axes, self.rest))

#
# ── basic4/1 ────────────────────────────────────────────────────────────────────────────
#


class FourEmotions(StrEnum):
    """Axis NAMES for ``basic4/1`` — four categories, two of them merged.

    Fear and surprise share an axis, as do anger and disgust: a collapsed basic-emotion set
    with a basis in the facial-signalling literature rather than an arbitrary simplification.
    Named for what it is rather than for anyone, because no four-category set is Ekman's.

    The merged names use an **underscore**, not a slash. A slash already separates a
    representation identifier from its version (``basic4/1``), and an axis called
    ``fear/surprise`` inside it would have the same character doing two unrelated jobs in
    one record.

    Explicit string values rather than ``auto()``, for the reason every enum here gives:
    these strings are the keys written into recorded data, and ``auto()`` numbers by
    position, so reordering a member would silently change what is already on disk.
    """

    HAPPINESS = "happiness"
    SADNESS = "sadness"
    FEAR_SURPRISE = "fear_surprise"
    ANGER_DISGUST = "anger_disgust"


BASIC4 = AffectRepresentation(
    id="basic4/1",
    axes=tuple(FourEmotions),
    value_range=(0.0, 1.0),
    rest=0.0,               # an intensity, so zero is the absence of the emotion
    metric=False,           # the midpoint between two categories is not an emotion
)

#
# ── ekman6/1 ────────────────────────────────────────────────────────────────────────────
#


class SixEmotions(StrEnum):
    """Axis NAMES for ``ekman6/1`` — the six most commonly cited basic emotions.

    Commonly attributed to Ekman, and the identifier carries that attribution because it is
    what makes a row of recorded data recognisable at a glance. The class name does not,
    because Ekman later proposed a considerably longer set — so the attribution names a
    widely cited moment rather than a settled position, and that is a caveat neither name
    can hold. Worth checking the primary source before citing it in a write-up.

    Alphabetical, which is arbitrary but stable: the order fixes the column order of every
    record written in this representation, so it is worth being a rule rather than a
    preference.

    A member here compares and hashes equal to a ``FourEmotions`` member of the same value,
    because ``StrEnum`` delegates both to ``str`` — so ``SixEmotions.HAPPINESS`` and
    ``FourEmotions.HAPPINESS`` are interchangeable as mapping keys. That is convenient and it
    is also a hazard: nothing stops one representation's table being handed to the other, so
    a component that pairs a table with a representation must check it explicitly rather
    than trusting the type checker to notice.
    """

    ANGER = "anger"
    DISGUST = "disgust"
    FEAR = "fear"
    HAPPINESS = "happiness"
    SADNESS = "sadness"
    SURPRISE = "surprise"


EKMAN6 = AffectRepresentation(
    id="ekman6/1",
    axes=tuple(SixEmotions),
    value_range=(0.0, 1.0),
    rest=0.0,
    metric=False,
)

#
# ── plutchik8/1 ─────────────────────────────────────────────────────────────────────────
#


class EightEmotions(StrEnum):
    """Axis NAMES for ``plutchik8/1`` — the eight primaries, held apart from the wheel.

    Declared because a lexicon has a basis of its own. The NRC Emotion Intensity Lexicon is
    annotated against these eight, so naming them lets the build read it without asserting a
    mapping in the act of reading — which is a different and much weaker claim than deciding
    that one emotion set translates into another.

    The identifier credits Plutchik because a reader of a record needs to know *which* eight.
    The class name does not, for the same reason ``SixEmotions`` does not: what is declared
    here is a **basis**, and Plutchik's model is a good deal more than a basis.

    **Flattened, and the flattening happened upstream.** The wheel proper carries opposing
    pairs (happiness↔sadness, trust↔disgust), intensity gradations and dyads. None of it is
    modelled here — these are eight independent unipolar axes, exactly as the lexicon
    publishes them, because its annotation was per word-emotion pair rather than an
    application of the theory. So this representation is no flatter than ``basic4/1`` or
    ``ekman6/1``; it is only more conspicuous about it, because the theory it names has
    structure the others never claimed. Bipolarity stays undeclared here for the same reason
    it is undeclared on ``AffectRepresentation``.

    **``happiness``, not Plutchik's ``joy``.** The rename costs the lexicon's own vocabulary
    and buys one axis name per emotion across all three representations, so an analysis can
    compare that axis without a translation table. The lexicon's term survives in the mapping
    that reads it, which is where somebody checking the correspondence would look.

    **Two of these axes cannot be scored.** The benchmark frame carries the ``ekman6/1``
    columns and nothing else, so ``anticipation`` and ``trust`` have no ground truth under it
    and never will. This representation is therefore **diagnostic rather than a third
    condition in an accuracy comparison** — it exists to answer how often the strongest
    lexical signal lands on an axis Ekman's six cannot represent. Anyone reporting accuracy
    over eight axes has scored two of them against nothing.

    Alphabetical, the same arbitrary-but-stable rule the other two follow.
    """

    ANGER = "anger"
    ANTICIPATION = "anticipation"
    DISGUST = "disgust"
    FEAR = "fear"
    HAPPINESS = "happiness"
    SADNESS = "sadness"
    SURPRISE = "surprise"
    TRUST = "trust"


PLUTCHIK8 = AffectRepresentation(
    id="plutchik8/1",
    axes=tuple(EightEmotions),
    value_range=(0.0, 1.0),
    rest=0.0,
    metric=False,
)

#
# ── Registry ────────────────────────────────────────────────────────────────────────────
#

REPRESENTATIONS: Mapping[str, AffectRepresentation] = {
    BASIC4.id: BASIC4,
    EKMAN6.id: EKMAN6,
    PLUTCHIK8.id: PLUTCHIK8,
}
"""Every declared representation, by the identifier that appears in recorded data.

The constants are named for their identifiers rather than their classes — ``BASIC4`` and
``EKMAN6``, not ``FOUR_EMOTIONS`` and ``SIX_EMOTIONS`` — so that the name in the source and
the string in the data are the same thing. Three names per representation, one convention
each: the class describes the set, the identifier is what the data carries, and the constant
mirrors the identifier.

The lookup a configuration file needs to turn ``representation = "basic4/1"`` into the axes,
and the one an analysis needs to make sense of an identifier it read from a stream.

Declared before it has a caller, deliberately and as an exception to this build's rule
against that. Without it each consumer grows its own ``if id == …`` dispatch, which is the
one-edit-per-new-representation failure this module exists to remove — and the alternative
is that the extension point is claimed in the design and absent from the code. If nothing
has called it by the time the composition root resolves configuration, delete it.
"""
