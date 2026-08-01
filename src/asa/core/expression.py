#
# Expression types
#
# The platform-neutral vocabulary between the affect model and the robot


"""The expression representation — what the agent intends to display, before any platform.

The output half of the two-stage mapping. An ``ExpressionEncoder`` turns a ``DesiredSignal``
(the affect the agent should convey) into an ``ExpressionPlan`` (a platform-NEUTRAL description
of how to convey it), and an embodiment adapter turns that into Furhat gestures or into the
primitives of whatever robot comes next. Nothing in this module names a platform.

A facial expression is a **vector with its vocabulary named**, for the same reason affect is
(see ``asa.core.affect``). A fixed set of prototype expressions cannot express a *blend* of
prototypes, which is the first extension the encoder is planned to grow — so ``FacialVector``
carries a descriptor-name → magnitude mapping plus a ``vocabulary`` saying what those names
mean. ``prototype/1`` names whole expressions; a later ``facs/1`` would name action units
instead. Same container, different vocabulary: one new encoder and one new renderer, not a
new type.

The naming pattern that follows: the vocabulary identifier stays a free ``str`` because records
outlive code and a retired vocabulary must still load, while the descriptor names within one
vocabulary are an enum, so the encoder that writes them and the adapter that looks them up
cannot disagree about spelling. ``prototype/1`` ↔ ``FacialPrototype``; a later ``facs/1`` ↔
``FacialActionUnit``. Those enums belong here in ``core/`` because the two components that need
them sit in different packages, so this is the only place both can depend on.

The magnitude *is* the rendering intensity, so there is no separate ``intensity`` field and the
two cannot disagree in recorded data. Neutral is the zero vector, not a vocabulary term.

``FacialVector`` deliberately does NOT reuse ``AffectVector`` despite the identical shape. A
facial descriptor is not affect, and holding the two apart is the whole point of the two-stage
mapping — sharing one type would let a descriptor be passed where affect is expected and
nothing would complain.

An expression is **multimodal**: face now, voice by experimental condition, head gesture and
gaze later. Channels are separate typed objects so that adding one is an optional field with a
default, and records written before it still read.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from asa.core.affect import AffectVector, _require_aware, utc_now

#
# ── Vocabulary ──────────────────────────────────────────────────────────────────────────
#


class FacialPrototype(StrEnum):
    """Descriptor NAMES for the ``prototype/1`` facial vocabulary — not a value type.

    A ``FacialVector`` in this vocabulary carries a magnitude for each named prototype, so a
    plan is never a bare category and a blend of two prototypes is expressible.

    Descriptors must be **independent of one another**, not points on each other's scale — the
    same requirement placed on affect axes. There is deliberately no ``BIG_SMILE`` beside
    ``SMILE``: magnitude already is the intensity, so ``{smile: 1.0}`` is a big smile and
    holding both would give one face two encodings, making a blend of the two meaningless and
    stopping the rows aggregating at analysis. Where a platform ships separate ``Smile`` and
    ``BigSmile`` primitives, absorbing that redundancy is the adapter's job — a neutral
    vocabulary carrying it would be the two-stage mapping failing at its one purpose.

    There is likewise no ``NEUTRAL`` member, matching ``Emotion``: neutral is the zero vector,
    and a ``{"neutral": 1.0}`` entry sitting beside ``{"smile": 0.5}`` would be incoherent. An
    adapter given an empty or all-zero vector returns the face to rest.

    Explicit string values rather than ``auto()``: these strings are the keys written into the
    JSONL trial records, and ``auto()`` numbers members by position — reordering or inserting a
    member would silently change the meaning of data already on disk.
    """

    SMILE = "smile"
    FROWN = "frown"
    SCOWL = "scowl"
    BROW_RAISE = "brow_raise"


class ExpressionCondition(StrEnum):
    """Which output channels the embodiment is permitted to execute.

    An experimental FACTOR, not a feature roadmap: these three combinations are what the study
    compares. Set in configuration and written into every trial record — without it in the
    record the conditions are not separable at analysis, which is an unrecoverable omission
    rather than a late addition.

    ``FACE_ONLY`` is the default deliberately. If the agent speaks emotionally congruent words
    the verbal channel carries most of the recognisable signal, and recognition accuracy can no
    longer be attributed to the face.
    """

    FACE_ONLY = "face_only"
    FACE_NEUTRAL_VOICE = "face_neutral_voice"
    FACE_EMOTIVE_VOICE = "face_emotive_voice"

#
# ── Facial representation and channels ──────────────────────────────────────────────────
#


@dataclass(frozen=True)
class FacialVector:
    """A facial expression, with the meaning of its descriptors named.

    In ``prototype/1`` the descriptors are ``FacialPrototype`` members: one entry is the
    ordinary iteration-1 case, two entries are a blend. A later ``facs/1`` would name action
    units instead, in the same container.

    Any component that *interprets* one must assert the vocabulary it supports and read
    descriptors by name — the same discipline ``AffectVector`` requires, for the same reason. A
    renderer built for one vocabulary would otherwise treat an action unit as a prototype.

    Magnitudes are independent values in 0.0–1.0; they do not sum to 1. The magnitude is the
    rendering intensity, which is what gives a continuous dial into the platform and what makes
    interpolation between expressions feasible at all.

    As with ``AffectVector``, ``frozen=True`` protects the binding and not the contents, and
    ``MappingProxyType`` is deliberately not used — it does not survive
    ``dataclasses.asdict()``.
    """

    vocabulary: str                 # "prototype/1" | "facs/1" — what the descriptors MEAN
    values: Mapping[str, float]     # descriptor name → magnitude, 0.0–1.0


@dataclass(frozen=True)
class FacialChannel:
    """The facial channel of a plan: what to show, and for how long.

    ``duration_s`` is a rendering parameter of *this channel*, which is why it sits here and
    not on ``FacialVector`` — it is not part of the descriptor — and not on ``ExpressionPlan``,
    where it would silently claim to apply to every channel at once.
    """

    facial: FacialVector
    duration_s: float


@dataclass(frozen=True)
class VoiceChannel:
    """The spoken channel of a plan — present only when the condition permits it.

    Named for the output side to match ``ExpressionCondition``'s ``…_VOICE`` members, and so
    that "speech" keeps meaning ASR input (the planned ``FurhatSpeech`` adapter). Speech in,
    voice out.

    One field today. It is a type rather than a bare ``str`` so that the prosody parameters
    ``FACE_EMOTIVE_VOICE`` will need can land inside it without changing ``ExpressionPlan``.
    """

    text: str

#
# ── Signal and plan ─────────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class DesiredSignal:
    """The affect the agent should CONVEY — the response planner's output.

    A distinct type from ``AffectState`` even though iteration-1 mimicry makes them isomorphic.
    Empathic responding is frequently not mirroring — sympathy, reassurance and de-escalation
    all produce a signal that differs from the perceived state — so collapsing the two would
    hard-code mimicry into the architecture. This one type distinction is the difference
    between an affect mirror and a prototype that can become an empathic agent.

    ``source``
        Which planner produced it, ``<role>:<implementation>``. A planned LLM planner is
        compared against the mimicry stub over the same inputs, and without this the record
        cannot say which one ran.
    ``rationale``
        Why this signal, when it is not a mirror. When the agent looks reassuring at an angry
        human this is the only record of the reasoning, which for a claim about empathic
        responding is closer to primary data than a nicety.
    """

    affect: AffectVector                    # what to CONVEY — not what was perceived
    source: str = ""                        # "planner:mimicry" | "planner:llm" | …
    rationale: str | None = None            # free-text why; the mimicry stub leaves it None
    at: datetime = field(default_factory=utc_now)
    schema: str = "signal/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)


@dataclass(frozen=True)
class ExpressionPlan:
    """A platform-NEUTRAL description of what to express, ready for an embodiment adapter.

    The output of the only component that interprets the affect representation. Everything
    downstream — the adapters, the recorder — treats this as opaque data, which is what
    contains a representation change to a new encoder rather than to ``if space == …`` branches
    scattered through the response loop.

    ``face`` is required rather than optional: all three expression conditions include it, and
    the empty case already has a value, since a zero vector returns the face to rest exactly as
    zero affect is neutral. Further channels arrive as optional fields with defaults, so adding
    head gesture or gaze leaves records written before it still readable.

    ``condition`` travels with the plan because it gates which channels the adapter may
    execute, and because it must reach the trial record for the conditions to be separable at
    analysis.

    ``at`` is carried here as on every other record type, so the encode and express intervals
    are derivable from the recorded data rather than trusted to whatever the response loop
    reports as its own latency.
    """

    face: FacialChannel
    condition: ExpressionCondition
    voice: VoiceChannel | None = None       # None unless the condition permits speaking
    at: datetime = field(default_factory=utc_now)
    schema: str = "expression/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)
