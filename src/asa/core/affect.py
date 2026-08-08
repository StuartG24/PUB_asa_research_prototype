#
# Affect types
#
# The representation that flows through every component


"""The affect record types — the load-bearing data structures of the agent.

Everything the agent perceives, believes, plans and records is expressed in these types,
and they are what the evaluation analyses.

Affect is a **vector with its representation named**. ``AffectVector`` carries an axis-name
→ magnitude mapping plus a ``representation`` identifier saying what those axis names mean.
What a given identifier means — which axes exist and in what order, over what range, what an
axis rests at, and whether distance between two vectors is meaningful — is declared in
``asa.core.representations``, not here. **This module holds the containers; that one holds
the ways of modelling affect.**

Any component that *interprets* a vector must assert the representation it supports and read
axes by name rather than by position. An encoder built for one representation would
otherwise read valence as happiness and cheerfully smile.

Magnitudes are **independent intensities, not a distribution**: they do not sum to 1,
because surprised *and* happy is an ordinary human state, and ageing independent values is
honest where ageing a distribution is a fudge. There is consequently no separate
``intensity`` field — the magnitude *is* the intensity, so the magnitude and the label
cannot disagree in recorded data. Note what is **not** claimed here: the range those
magnitudes take and the value an axis rests at are properties of the representation, not of
this container, and treating either as universal is the mistake that made
``representations`` a module of its own.

``representation`` and ``schema`` version different things: ``schema`` versions the record
shape for data already on disk, ``representation`` versions the meaning of the axes.
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
# ── Affect and target ───────────────────────────────────────────────────────────────────
#


class Target(StrEnum):
    """What a piece of evidence is about.

    - Self: the agent's own affect — what it FEELS. Written by the intention planner
    - Other: the human interactant — what the agent BELIEVES they feel
    - Expressed: the affect the agent actually CONVEYED. Written by the response loop

    **``EXPRESSED`` is deliberately not named for a channel.** Iteration 1 expresses through the
    face alone, but the same claim covers tone of voice, gesture and posture as those arrive:
    what is recorded is *affect*, in the representation's axes, not a description of the
    machinery that produced it. Naming this member ``FACIAL`` would have needed renaming the
    day a second channel is driven independently, and renaming a ``Target`` costs a ``schema``
    bump and two record shapes in one analysis. Which channel did what is recorded separately,
    on the render (``ExpressionPlan`` already carries a face channel and a voice channel).

    **``EXPRESSED`` is not a belief, and holding it apart from ``SELF`` is the whole point of
    having it.** ``self_`` is what the agent feels; folding an executed expression into it
    would merge *intended* with *shown*, and the difference between those two is the quantity
    an empathic agent's evaluation most wants to report. Kept separate, one record answers
    three questions: what the human feels, what the agent feels, and what the agent showed.

    This is also why it is **not** facial feedback. Nothing lets ``EXPRESSED`` evidence reach
    ``self_``, so the agent knowing that it smiled does not make it feel happier. That remains
    a deliberate modelling position; if a later iteration wants it, it becomes a fold policy
    and an explicit theoretical commitment rather than a consequence of where a value was put.
    """

    SELF = "self"
    OTHER = "other"
    EXPRESSED = "expressed"


@dataclass(frozen=True)
class AffectVector:
    """An affect estimate, with the meaning of its axes named.

    ``representation`` is a free ``str`` and not a reference to an ``AffectRepresentation``,
    deliberately. Records outlive the code that wrote them, so a stream from an earlier pilot
    may name a representation this build no longer declares — a string still loads and the
    row stays readable, where a reference would fail to resolve and make the data unopenable
    by the current code. ``asa.core.representations`` is the lookup from one to the other.

    The mapping's contents can still be changed in place — values altered, axes added or removed.
    ``frozen=True`` protects the *binding*, not the contents.
    ``values`` is annotated ``Mapping`` to say "treat as read-only", but a ``dict`` passed
    in stays mutable in place.
    Deliberately not wrapped in ``MappingProxyType``: that does not survive
    ``dataclasses.asdict()`` (it raises ``cannot pickle 'mappingproxy'``), which would
    break the recorder for the sake of a guarantee no component needs.
    """

    representation: str             # "basic4/1" | "ekman6/1" — what the axis names MEAN
    values: Mapping[str, float]     # axis name → magnitude, within the representation's range

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
        The audit trail for why this evidence says what it does. When the agent looks
        concerned because the human went quiet, this is the only record of why — and a
        decoder fills it with what it matched on, so that an analysis can tell a genuinely
        mild reading from a false positive without re-running the decoder. Every producer
        may fill it; ``source`` is what distinguishes them.
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
    rationale: str | None = None            # free-text why; any producer may fill it
    computed_from: datetime | None = None   # the snapshot it was derived from
    of_input: str | None = None             # the input record's id — Utterance.id today
    at: datetime = field(default_factory=utc_now)
    schema: str = "evidence/1"

    def __post_init__(self) -> None:
        _require_aware("at", self.at)
        _require_aware("computed_from", self.computed_from)


AffectObservation = AffectEvidence
"""Perception's output: an alias, not a new type.

Perception produces evidence like anything else — ``target=OTHER`` and a ``source`` naming
the decoder. The alias exists so call sites read as what they are.
"""


#
# ── State and history ───────────────────────────────────────────────────────────────────
#


@dataclass(frozen=True)
class AffectState:
    """What the model holds at one instant: two beliefs, and a record of what was shown.

    The two beliefs are held separately because they age by two different processes:
    — the estimate of other's state goes stale as *evidence*, an epistemic decay
    — whereas the agent's own affect ages as an emotional one.
    Plausibly different time constants and different shapes, so must not be conflated

    ``self_`` is written by the intention planner, which publishes its decision as evidence
    targeted at ``SELF`` rather than commanding an expression — so the agent's own affect is
    folded and aged like any other belief. Perception and deliberation only ever target
    ``OTHER``. The rule across the whole architecture: **everything infers about other; only
    the planner decides self.**

    ``expressed`` is the third vector and the odd one out: **it is a fact, not an estimate.**
    The response loop reports the ``self_`` value it actually rendered from, so this says what
    the agent was *commanded* to convey. Three consequences, and they are why the fold and the
    ageing are **per target** rather than uniform. It is assigned rather than weighted, because
    a record of what was commanded must not drift toward anything. It does not decay, because
    it has nothing to go stale about — it holds until the next render replaces it. And it never
    reaches ``self_``: see ``Target``.

    **Why a third vector rather than a change to ``self_``.** Merged, *intended* and *conveyed*
    become one number and "did the agent express what it meant?" stops being answerable — which
    is the question a study of empathic expression is largely asking. The cost of keeping them
    apart is one field; the cost of merging them is not recoverable afterwards.

    **One vector across all channels, and its limit is known.** Iteration 1 drives one channel,
    so one vector says everything. When face and voice are driven independently — an
    experimental factor in the design — a single vector cannot record that the face conveyed one
    thing and the voice another, and a channel *disabled by condition* is **not applicable**
    rather than at rest. That is a ``state/3`` decision and a research one, deliberately left
    open rather than guessed at.
    """

    other: AffectVector                     # the belief about the human — what it FEELS
    self_: AffectVector                     # the agent's own affect — what it FEELS
    expressed: AffectVector                 # the affect it actually CONVEYED, any channel
    at: datetime                            # the instant this state is valid for
    schema: str = "state/2"                 # was state/1, before ``expressed``

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

    Because a snapshot is a whole ``AffectState``, both reasoning ports also see ``expressed``
    without this type changing or gaining a second parameter — so a deliberator can ask whether
    the agent has been conveying what it intended, which is a different question from what it
    feels.

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
