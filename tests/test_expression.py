#
# Test - expression types
#

"""Tests for the expression representation.

These types are nearly pure data, so a test per field would mostly be testing ``dataclasses``
rather than this module. Covered instead is the small amount of behaviour the module adds —
the timezone guards — plus the properties other components will silently depend on: that
``FacialPrototype`` members work as ``str`` keys, that the condition parses back from the value
the config file carries, and the one genuinely new shape, a record that nests three levels deep
on its way to JSONL.

Not repeated from ``test_affect.py``: ``replace()`` re-validation, aware-by-default, and
``asdict()`` leaving datetimes alone. Those pin shared helpers that this module reuses
unchanged, and duplicating them here would mean two tests failing for every one cause.
"""

from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from asa.core.affect import AffectVector
from asa.core.expression import (
    DesiredSignal,
    ExpressionCondition,
    ExpressionPlan,
    FacialChannel,
    FacialPrototype,
    FacialVector,
    VoiceChannel,
)

NAIVE = datetime(2026, 8, 1, 14, 30)                # no tzinfo — the value under test
AWARE = datetime(2026, 8, 1, 14, 30, tzinfo=UTC)

HAPPY = AffectVector(space="ekman4/1", values={"happiness": 0.9})
SMILING = FacialVector(vocabulary="prototype/1", values={"smile": 0.7})
FACE = FacialChannel(facial=SMILING, duration_s=2.0)


def test_desired_signal_rejects_a_naive_timestamp():
    """A caller-supplied naive ``at`` fails where the record is created, not later."""
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        DesiredSignal(affect=HAPPY, source="planner:mimicry", at=NAIVE)


def test_expression_plan_rejects_a_naive_timestamp():
    """The same guard on the plan.

    Kept separate from the signal's test rather than parametrised: the two are independent
    ``__post_init__`` bodies, so either could be dropped without the other's test noticing.
    """
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        ExpressionPlan(face=FACE, condition=ExpressionCondition.FACE_ONLY, at=NAIVE)


def test_facial_prototype_members_are_usable_as_str_keys():
    """``values`` is keyed by ``str``, and ``StrEnum`` members hash as their value.

    The same property ``Emotion`` relies on, for the same reason: an encoder writes
    ``{FacialPrototype.SMILE: 0.7}`` and gets the enum's spelling safety, while the container
    stays open to a ``facs/1`` vector whose descriptors are not ``FacialPrototype`` members at
    all. A plain ``Enum`` would hash by member *name* and raise ``KeyError`` below.
    """
    vector = FacialVector(vocabulary="prototype/1", values={FacialPrototype.SMILE: 0.7})

    assert vector.values["smile"] == 0.7
    assert f"{FacialPrototype.BROW_RAISE}" == "brow_raise"      # what reaches the JSONL record


def test_condition_round_trips_from_its_config_value():
    """The config carries the enum VALUE, so the value is what has to parse.

    ``[expression] condition = "face_only"`` arrives from TOML as a plain string and is handed
    to ``ExpressionCondition(...)``. Uppercasing the values to match the member names would
    leave this as the only thing that notices, and the failure would then surface as a config
    file that silently stops loading rather than as an obviously wrong enum.
    """
    assert ExpressionCondition("face_only") is ExpressionCondition.FACE_ONLY
    assert ExpressionCondition.FACE_ONLY == "face_only"


def test_plan_round_trips_through_its_nested_channels():
    """``asdict()`` must recurse the whole channel structure on its way to JSONL.

    Every record in ``core/affect.py`` is flat; a plan is three levels deep, and step 12's
    recorder depends on it arriving as plain containers with no bespoke code. The literal below
    is therefore also the documented shape of the ``expressed`` half of a trial record.

    This is the standing ``MappingProxyType`` guard for ``FacialVector`` too: wrapping
    ``values`` to make it read-only at runtime raises ``cannot pickle 'mappingproxy'`` here,
    exactly as it does for ``AffectVector`` in ``test_affect.py``.
    """
    plan = ExpressionPlan(
        face=FACE,
        condition=ExpressionCondition.FACE_ONLY,
        voice=VoiceChannel(text="that's wonderful"),
        at=AWARE,
    )

    assert asdict(plan) == {
        "face": {"facial": {"vocabulary": "prototype/1", "values": {"smile": 0.7}},
                 "duration_s": 2.0},
        "condition": "face_only",
        "voice": {"text": "that's wonderful"},
        "at": AWARE,
        "schema": "expression/1",
    }


def test_an_absent_voice_channel_serialises_as_none():
    """The claim that adding a channel leaves older records readable rests on this.

    A plan with no voice must produce an explicit ``None`` rather than a missing key or an
    error — which is what lets an analysis written against a later, richer plan still read a
    record written before that channel existed.
    """
    plan = ExpressionPlan(face=FACE, condition=ExpressionCondition.FACE_ONLY, at=AWARE)

    assert asdict(plan)["voice"] is None


def test_the_vocabulary_holds_no_redundant_descriptors():
    """Pins two deliberate absences whose reasons are invisible at the point of re-adding one.

    ``BIG_SMILE`` is not a descriptor because the magnitude already carries strength, so
    holding it beside ``SMILE`` would give one face two encodings — making a blend of the two
    meaningless and stopping the rows aggregating at analysis. ``NEUTRAL`` is not one because
    neutral is the zero vector, as it already is for ``Emotion``. Both failures are silent and
    land in research data, so the vocabulary is asserted whole rather than trusted to review.
    """
    assert {member.value for member in FacialPrototype} == {
        "smile", "frown", "scowl", "brow_raise"}
