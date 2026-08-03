#
# Test - affect types
#

"""Tests for the affect representation.

These types are nearly pure data, so a test per field would mostly be testing
``dataclasses`` rather than this module. What is covered instead is the small amount of
behaviour the module adds — the timezone guard — plus the properties other components
will silently depend on: that ``Emotion`` members work as ``str`` keys, that a record
survives ``dataclasses.asdict()`` on its way to JSONL, and that each record gets its own
identifier.
"""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from asa.core.affect import (
    AffectEvidence,
    AffectHistory,
    AffectObservation,
    AffectState,
    AffectVector,
    Emotion,
    Target,
    Utterance,
)

NAIVE = datetime(2026, 8, 1, 14, 30)                # no tzinfo — the value under test
AWARE = datetime(2026, 8, 1, 14, 30, tzinfo=UTC)

HAPPY = AffectVector(space="ekman4/1", values={"happiness": 0.9, "surprise": 0.3})
NEUTRAL = AffectVector(space="ekman4/1", values={"happiness": 0.0, "sadness": 0.0,
                                                 "anger": 0.0, "surprise": 0.0})


def test_utterance_rejects_a_naive_timestamp():
    """A caller-supplied naive ``at`` fails where it was created, not later."""
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        Utterance(text="I got the job", source="input:text_console", at=NAIVE)


def test_evidence_rejects_a_naive_timestamp():
    """The same guard on evidence."""
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        AffectEvidence(target=Target.OTHER, affect=HAPPY, at=NAIVE)


def test_state_rejects_a_naive_timestamp():
    """``AffectState.at`` has no default, so it is the field most exposed to this."""
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        AffectState(other=HAPPY, self_=NEUTRAL, at=NAIVE)


def test_computed_from_rejects_a_naive_timestamp():
    """The optional second timestamp is guarded too, and the message names it."""
    with pytest.raises(ValueError, match="computed_from must be timezone-aware"):
        AffectEvidence(target=Target.OTHER, affect=HAPPY, computed_from=NAIVE)


def test_computed_from_may_be_none():
    """Perception derives from no snapshot, so ``None`` must pass the guard untouched."""
    observation = AffectObservation(target=Target.OTHER, affect=HAPPY, source="decoder:rule")

    assert observation.computed_from is None


def test_defaults_are_timezone_aware():
    """The ordinary construction path never trips the guard."""
    assert Utterance(text="hello", source="input:random").at.utcoffset() is not None
    assert AffectEvidence(target=Target.SELF, affect=NEUTRAL).at.utcoffset() is not None


def test_each_utterance_gets_its_own_id():
    """``default_factory`` is called per instance, not once at class definition.

    Worth a test because the alternative fails silently: ``id: str = new_id()`` is legal
    Python and gives every record in a run the same identifier, so ``of_input`` would
    point at all of them at once — data that looks joinable and is not.
    """
    first = Utterance(text="one", source="input:random")
    second = Utterance(text="two", source="input:random")

    assert first.id != second.id


def test_emotion_members_are_usable_as_str_keys():
    """``values`` is keyed by ``str``, and ``StrEnum`` members hash as their value.

    This is what lets a component write ``{Emotion.HAPPINESS: 0.9}`` for the enum's
    safety while the container stays open to a ``vad/1`` vector whose axes are not
    ``Emotion`` members at all. A plain ``Enum`` would hash by member *name* and raise
    ``KeyError`` on the lookup below.
    """
    vector = AffectVector(space="ekman4/1", values={Emotion.HAPPINESS: 0.9})

    assert vector.values["happiness"] == 0.9
    assert Emotion.HAPPINESS == "happiness"
    assert f"{Emotion.HAPPINESS}" == "happiness"        # what reaches the JSONL record


def test_state_round_trips_to_plain_data():
    """``asdict()`` is how a record reaches JSONL, and it must arrive as plain containers.

    Also the standing guard on the ``MappingProxyType`` decision: wrapping
    ``AffectVector.values`` to make it read-only at runtime raises ``cannot pickle
    'mappingproxy'`` here, so this test fails the moment someone tries it.
    """
    record = asdict(AffectState(other=HAPPY, self_=NEUTRAL, at=AWARE))

    assert record["other"] == {"space": "ekman4/1",
                               "values": {"happiness": 0.9, "surprise": 0.3}}
    assert record["schema"] == "state/1"


def test_asdict_does_not_serialise_datetimes():
    """Pins what the recorder must still do for itself at step 12.

    ``asdict()`` converts the dataclasses to dicts but leaves scalars alone, so ``at``
    is still a ``datetime`` and ``json.dumps`` refuses the record. Enum members survive
    unaided, being ``str`` subclasses. The recorder therefore needs a ``default=``
    handler for datetimes and nothing else.
    """
    record = asdict(AffectEvidence(target=Target.OTHER, affect=HAPPY, at=AWARE))

    assert json.dumps(record["target"]) == '"other"'
    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps(record)


def test_replace_revalidates():
    """``replace()`` re-runs ``__post_init__``, so the guard cannot be dodged by copying.

    This is the route that matters in practice: the types are frozen, so a component
    needing a modified record makes a new one with ``replace()`` rather than assigning.
    """
    evidence = AffectEvidence(target=Target.OTHER, affect=HAPPY)

    with pytest.raises(ValueError, match="at must be timezone-aware"):
        replace(evidence, at=NAIVE)


def test_observation_is_an_alias_not_a_subclass():
    """Perception produces evidence like anything else, distinguished by ``source``."""
    assert AffectObservation is AffectEvidence


#
# ── AffectHistory — the snapshot the reasoning ports read ───────────────────────────────
#


def a_state(at: datetime = AWARE) -> AffectState:
    """A throwaway state, for tests whose subject is the history around it."""
    return AffectState(other=HAPPY, self_=NEUTRAL, at=at)


def test_history_rejects_a_naive_timestamp():
    """``at`` has no default here either, so it carries the same exposure as ``AffectState``."""
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        AffectHistory(current=a_state(), states=(), evidence=(), at=NAIVE)


def test_history_tolerates_an_empty_window():
    """The cold start: a belief exists and nothing has happened yet.

    This is the intention planner's very first tick, before any evidence has arrived. It
    is also why ``current`` is a field rather than ``states[-1]`` — that read would raise
    here, so every reader wanting only the value now would need an empty-window branch.
    """
    history = AffectHistory(current=a_state(), states=(), evidence=(), at=AWARE)

    assert history.states == ()
    assert history.current.other is HAPPY


def test_history_sequences_are_immutable():
    """The snapshot must not change under a reader, and ``tuple`` is what says so.

    Pinned rather than left to the annotation because the *reason* is several files away:
    both reasoning ports may hold this across an ``await`` on a language-model call, and a
    sequence that grew mid-call would give a torn read and an unreproducible appraisal.
    Someone rewriting the field as ``list`` for convenience would see none of that.
    """
    history = AffectHistory(current=a_state(), states=(a_state(),), evidence=(), at=AWARE)

    with pytest.raises(AttributeError):
        history.states.append(a_state())            # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        history.evidence.append(                    # type: ignore[attr-defined]
            AffectEvidence(target=Target.OTHER, affect=HAPPY))


def test_history_coerces_a_list_to_a_tuple():
    """The test with teeth: annotations are not enforced at runtime.

    ``states=[...]`` is accepted by the dataclass and Pylance is the only thing objecting,
    so without ``__post_init__`` normalising it the immutability above is a claim rather
    than a guarantee — and the likely route in is the affect model assembling its window
    as a list and never converting it.
    """
    history = AffectHistory(current=a_state(), states=[a_state()],    # type: ignore[arg-type]
                            evidence=[], at=AWARE)                    # type: ignore[arg-type]

    assert isinstance(history.states, tuple)
    assert isinstance(history.evidence, tuple)


def test_history_asdict_recurses_and_json_returns_lists():
    """Pins a step-12 comparison gotcha, on the same grounds as the datetime test above.

    ``asdict()`` rebuilds each sequence as its own type, so a ``tuple`` stays a ``tuple``.
    ``json.dumps`` then writes it as an array, which reads back as a ``list`` — so a record
    loaded from disk is *not* equal to the record that was written, and any analysis
    comparing the two fails on the container type rather than on the data.
    """
    record = asdict(AffectHistory(current=a_state(), states=(a_state(),),
                                  evidence=(), at=AWARE))

    assert isinstance(record["states"], tuple)
    assert record["states"][0]["schema"] == "state/1"

    round_tripped = json.loads(json.dumps(record, default=str))
    assert isinstance(round_tripped["states"], list)
