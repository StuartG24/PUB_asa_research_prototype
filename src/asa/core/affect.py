#
# Affect types
#
# The representation that flows through every component


"""The affect representation — the load-bearing data structure of the agent.

Everything the agent perceives, believes, plans and records is expressed in these types,
and they are what the evaluation analyses.

Affect is a **vector with its space named**. ``AffectVector`` carries an axis-name →
magnitude mapping plus a ``space`` saying what those axes mean. 
- ``ekman4/1`` axes are not — the midpoint between anger and surprise is not an emotion
- ``vad/1`` is a metric space — distance and midpoints are meaningful

Any component that *interprets* a vector must therefore assert the space
it supports, and must read axes by name rather than by position — an encoder built for one
space would otherwise read valence as happiness and cheerfully smile.

Values are independent intensities in 0.0–1.0, not a distribution; they do not sum to 1.
Surprised *and* happy is an ordinary human state, per-axis decay toward zero is honest
where ageing a distribution is a fudge, and "neutral" falls out as the zero vector.
There is consequently no separate ``intensity`` field: the magnitude *is* the intensity, 
so the magnitude and the label cannot disagree in recorded data.

``space`` and ``schema`` version different things: ``schema`` versions the record shape for
data already on disk, ``space`` versions the meaning of the axes.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

#
# ── Dates and IDs ───────────────────────────────────────────────────────────────────────
#


def utc_now() -> datetime:
    """The current instant, timezone-aware UTC.

    One named source of "now", so the default timestamps below are a single thing for a
    test to patch, and one the clocks in the system can line up with. The affect model is
    not among them — it owns no clock and takes time as a parameter. The clocks belong to
    the intention planner, to deliberation and to the response loop, all injectable.
    """
    return datetime.now(UTC)


def new_id() -> str:
    """A short opaque identifier, for records that others refer back to."""
    return uuid.uuid4().hex[:12]


def _require_aware(field_name: str, value: datetime | None) -> None:
    """Reject a naive datetime, naming the field that carried it.

    Timezone-naive values are wall-clock readings with no record of which clock, so a BST
    pilot and a GMT one cannot be reliably ordered and an interval spanning the autumn
    clock change can come out zero or negative. Nothing raises on its own — the numbers are
    simply wrong — and once written the offset is not merely hidden but absent, so the
    record cannot be repaired afterwards.

    Rejects rather than coerces. Attaching UTC to a naive value would be a guess about
    which clock the caller meant, and a wrong guess is invisible in the results.

    ``utcoffset()`` rather than ``tzinfo is None``, because a ``tzinfo`` object can itself
    return ``None`` for the offset — this is the check that answers the actual question.
    """
    if value is not None and value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be timezone-aware — use asa.core.affect.utc_now()"
        )

#
# ── Emotions and affect and target ──────────────────────────────────────────────────────
#


class Emotion(StrEnum):
    """Axis NAMES for the ``ekman4/1`` space — not a value type.

    An ``AffectVector`` in this space carries a magnitude for each of these, so affect is
    never held as a bare category. There is no ``NEUTRAL`` member: neutral is every axis at
    or below a configured threshold.

    Explicit string values rather than ``auto()``: these strings are the keys written into
    the JSONL trial records, and ``auto()`` numbers members by position — reordering or
    inserting a member would silently change the meaning of data already on disk.
    """

    HAPPINESS = "happiness"
    SADNESS = "sadness"
    ANGER = "anger"
    SURPRISE = "surprise"


class Target(StrEnum):
    """Whose affect a piece of evidence is about.

    - Self: Is the agent, robot
    - Other: Is the human interactant

    """

    SELF = "self"
    OTHER = "other"


@dataclass(frozen=True)
class AffectVector:
    """An affect estimate, with the meaning of its axes named.

    For example an Ekman4 or a VAD representation of affect

    The mapping's contents can still be changed in place — values altered, axes added or removed.
    ``frozen=True`` protects the *binding*, not the contents. 
    ``values`` is annotated ``Mapping`` to say "treat as read-only", but a ``dict`` passed
    in stays mutable in place. 
    Deliberately not wrapped in ``MappingProxyType``: that does not survive
    ``dataclasses.asdict()`` (it raises ``cannot pickle 'mappingproxy'``), which would
    break the recorder for the sake of a guarantee no component needs.
    """

    space: str                      # "ekman4/1" | "vad/1" — what the axes MEAN
    values: Mapping[str, float]     # axis name → magnitude, 0.0–1.0

#
# ── Utterance and evidence ──────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class Utterance:
    """Something the human said, from any input adapter.

    Text and speech converge here: the input is a sentence, so the moment ASR returns a
    string the two are indistinguishable and one decoder serves both.

    No ``context`` slot is reserved for the framework's Context/Background moderators. An
    always-``None`` field with no type is documentation that lies, and it is trivial to add
    the day a ``Context`` type exists.

    ``intended`` is the affect a sentence was *meant* to convey, and only a source that
    knows it may set it. Two do: the generated source, which chose the affect before
    writing the sentence, and a labelled benchmark set, whose rows were written to convey a
    stated affect. A person typing at a console does not declare their intent and leaves it
    ``None`` — which is why those two sources are the only ones a decoder's accuracy can be
    measured against, offline from a notebook or replayed through the live agent.
    """

    text: str
    source: str                             # "input:text_console" | "input:random" | …
    intended: AffectVector | None = None    # ground truth — generated and benchmark sources
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)
    schema: str = "utterance/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)


@dataclass(frozen=True)
class AffectEvidence:
    """One estimate of affect at an instant in time. From: perception or deliberation.

    Distinct from ``AffectState``: evidence is an *estimate*, state is the model's *belief*. 
    Keeping the types apart means an estimate cannot be assigned over a belief, so the fold rule
    is enforced by the type system rather than remembered.

    The five fields beyond the estimate itself:

    ``confidence``
        How far the *evidence* is to be trusted — a garbled ASR transcript, an appraisal
        the model flags as speculative. **Not** how the estimate is spread across axes: a
        decoder torn between two readings says so in the vector, not by attaching 0.5
        here. A keyword decoder should therefore leave this ``None`` rather than claim
        ``1.0``, which would make a rule decoder look maximally sure beside an LLM
        honestly reporting 0.7.
    ``rationale``
        The audit trail for autonomous behaviour. When the agent looks concerned because
        the human went quiet, this is the only record of why.
    ``computed_from``
        The state snapshot this was derived from, so a late-arriving appraisal can be
        discounted by how stale it is rather than trusted equally.
    ``of_input``
        Provenance back to the raw input, so the recorder can reconstruct what was actually
        said. Without it the trial record has an inferred vector and no text. Named for the
        input generally, not for ``Utterance``, eg deferred physiological and
        vision inputs produce no utterance 
    ``target``
        Which of the two entirely different claims this is.
    """

    target: Target                          # ie Self or Other
    affect: AffectVector
    confidence: float | None = None
    source: str = ""                        # "decoder:rule" | "deliberation:llm" | …
    rationale: str | None = None            # free-text why; only deliberation fills it in I1
    computed_from: datetime | None = None   # the snapshot it was derived from
    of_input: str | None = None             # the input record's id — Utterance.id today
    at: datetime = field(default_factory=utc_now)
    schema: str = "evidence/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)
        _require_aware("computed_from", self.computed_from)


AffectObservation = AffectEvidence
"""Perception's output: an alias, not a new type.

Perception produces evidence like anything else — ``target=OTHER``, no ``rationale``, a
``source`` naming the decoder. The alias exists so call sites read as what they are.
"""


#
# ── State and history ───────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class AffectState:
    """The model's belief about both parties (self and other) at one instant.

    Self and other are held separately because they age by two different processes:
    — the estimate of other's state goes stale as *evidence*, an epistemic decay
    — whereas the agent's own affect ages as an emotional one.
    Plausibly different time constants and different shapes, so must not be conflated

    ``self_`` is written by the intention planner, which publishes its decision as evidence
    targeted at ``SELF`` rather than commanding an expression — so the agent's own affect is
    folded and aged like any other belief. Perception and deliberation only ever target
    ``OTHER``. The rule across the whole architecture: **everything infers about other; only
    the planner decides self.**
    """

    other: AffectVector
    self_: AffectVector
    at: datetime                            # the instant this state is valid for
    schema: str = "state/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)


@dataclass(frozen=True)
class AffectHistory:
    """A snapshot of the model's belief and how it got there, for the reasoning ports.

    Both the deliberator and the intention planner read this rather than an ``AffectState``,
    because a snapshot at an instant cannot express a *change*: sadness at 0.6 looks
    identical whether it arrived gradually or in one step. The salient input to appraisal and
    to responding is often the trajectory rather than the value.

    A **copy, never a live handle.** Either reader may be slow — an LLM call can sit behind
    both — and a handle on state that mutates mid-call gives torn reads and appraisals that
    cannot be reproduced. ``states`` and ``evidence`` are therefore coerced to ``tuple``
    below, so the guarantee holds even when the model builds them as lists.

    Coercing rather than rejecting is not a departure from ``_require_aware``'s rule: that
    one refuses to guess *which clock* a naive datetime meant, whereas ``tuple(a_list)`` is
    the same sequence in the same order, with one right answer.

    **The sequence is immutable; the snapshot is not deeply so.** Each ``AffectState`` is
    frozen, but the ``values`` mapping inside its vectors is usually a real ``dict`` — see
    ``AffectVector``. So the outer guarantee only holds if the affect model treats §9.3's
    *fold, never overwrite* as producing new ``AffectVector`` objects rather than updating
    one in place.

    ``current`` is not ``states[-1]``. It is the belief at ``at``, whereas ``states`` is the
    bounded window behind it, so a reader wanting only the value now never has to handle an
    empty window. Iteration 1's mimicry planner reads only ``current``, which is what makes
    it a stub rather than a strategy.
    """

    current: AffectState                        # the belief at ``at``
    states: tuple[AffectState, ...]             # oldest first, bounded by config
    evidence: tuple[AffectEvidence, ...]        # what produced them, same window
    at: datetime                                # when the snapshot was taken
    schema: str = "history/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)
        # frozen, so normalising has to go through object.__setattr__
        object.__setattr__(self, "states", tuple(self.states))
        object.__setattr__(self, "evidence", tuple(self.evidence))
