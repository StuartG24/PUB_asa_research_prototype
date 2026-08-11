#
# NRC-EIL lexicon loading
#
# Build step 7b-i


"""What ``nrc_eil.load_tables`` promises, checked against a fixture small enough to read.

**Every test here builds its own artefact in ``tmp_path``**, and none needs the real lexicon.
That is deliberate rather than a convenience: the licensed file cannot be committed, so a suite
depending on it would be unrunnable on a fresh clone and unrunnable in CI. What these tests check
is the *loader* — the mapping, the two guards, the threshold and where ``source`` comes from — all
of which are properties of ten lines of code and not of ten thousand words. A test that the real
lexicon populates every axis is a separate thing and belongs with the notebook that prepares it.

The fixture carries one word per emotion, which makes a failure legible: a wrong mapping shows up
as a wrong *word* under an axis, not as a count that has to be trusted.
"""

import json
from pathlib import Path

import pytest

from asa.core.representations import BASIC4, EKMAN6, PLUTCHIK8
from asa.perception.nrc_eil import NATIVE, PLUTCHIK8_FROM_NRC, load_tables

#
# ── The fixture ─────────────────────────────────────────────────────────────────────────
#

ENTRIES = {
    "anger":        {"furious": 0.9, "annoyed": 0.4},
    "anticipation": {"eager": 0.7},
    "disgust":      {"revolted": 0.9},
    "fear":         {"terrified": 0.9},
    "joy":          {"delighted": 0.9},         # the lexicon's name for happiness
    "sadness":      {"devastated": 0.9},
    "surprise":     {"astonished": 0.8},
    "trust":        {"reliable": 0.8},
}


def _artefact(tmp_path: Path, *, entries=None, id_="nrc-eil", omit_id=False) -> Path:
    """A prepared lexicon file, shaped exactly as the notebook will write one."""
    prepared: dict[str, object] = {
        "lexicon": "NRC-Emotion-Intensity-Lexicon-v1",
        "prepared_by": "notebooks/lexicons.ipynb",
        "entries": ENTRIES if entries is None else entries,
    }
    if not omit_id:
        prepared["id"] = id_

    path = tmp_path / "lexicon.json"
    path.write_text(json.dumps(prepared), encoding="utf-8")
    return path


#
# ── The mapping ─────────────────────────────────────────────────────────────────────────
#


def test_the_native_table_carries_every_axis_with_joy_renamed():
    """The mapping is total, so loading drops nothing — dropping happens in ``restrict``."""
    assert set(PLUTCHIK8_FROM_NRC.values()) == set(PLUTCHIK8.axes)
    assert NATIVE is PLUTCHIK8


def test_loading_maps_the_lexicons_vocabulary_onto_the_representations(tmp_path: Path):
    """``joy`` becomes ``happiness``, and the word proves which entry moved."""
    got = load_tables(_artefact(tmp_path), [PLUTCHIK8])

    table = got.tables[PLUTCHIK8.id]
    assert tuple(table) == PLUTCHIK8.axes                   # declared order, all eight
    assert table["happiness"] == {"delighted": 0.9}         # arrived from "joy"
    assert "joy" not in table


def test_one_call_yields_a_table_per_requested_representation(tmp_path: Path):
    """The façade's whole purpose, and the reason ``restrict`` runs on the native table too."""
    got = load_tables(_artefact(tmp_path), [PLUTCHIK8, EKMAN6])

    assert set(got.tables) == {"plutchik8/1", "ekman6/1"}
    assert tuple(got.tables["ekman6/1"]) == EKMAN6.axes
    assert "anticipation" not in got.tables["ekman6/1"]
    assert "trust" not in got.tables["ekman6/1"]
    assert got.tables["ekman6/1"]["anger"] == {"furious": 0.9, "annoyed": 0.4}


def test_a_representation_the_lexicon_cannot_reach_is_refused(tmp_path: Path):
    """``basic4/1`` merges, so it is refused — by ``restrict``, not by a check written here."""
    with pytest.raises(ValueError, match="anger_disgust, fear_surprise"):
        load_tables(_artefact(tmp_path), [BASIC4])


#
# ── Provenance ──────────────────────────────────────────────────────────────────────────
#


def test_the_source_name_comes_from_the_file(tmp_path: Path):
    """Read, never assumed — which is what stops a swapped artefact being mislabelled."""
    got = load_tables(_artefact(tmp_path, id_="nrc-eil-v2-draft"), [PLUTCHIK8])

    assert got.source == "nrc-eil-v2-draft"


def test_an_artefact_with_no_id_is_refused(tmp_path: Path):
    """There would be nothing to stamp on a record, and a decoder must not invent one."""
    with pytest.raises(ValueError, match="no 'id'"):
        load_tables(_artefact(tmp_path, omit_id=True), [PLUTCHIK8])


def test_a_floor_drops_entries_and_reaches_the_source_name(tmp_path: Path):
    """Two floors over one lexicon are two instruments, so the name has to say which.

    Without the suffix, a run at 0.5 and a run at 0.0 write identical ``source`` strings over
    identical representations — the same indistinguishability the third source segment was added
    to remove, arriving one level down.
    """
    got = load_tables(_artefact(tmp_path), [PLUTCHIK8], floor=0.5)

    assert got.source == "nrc-eil@0.5"
    assert got.tables[PLUTCHIK8.id]["anger"] == {"furious": 0.9}     # "annoyed" 0.4 dropped


#
# ── The two guards ──────────────────────────────────────────────────────────────────────
#


def test_a_file_missing_a_mapped_emotion_is_refused(tmp_path: Path):
    """The wrong-version guard, and the realistic mistake it catches.

    NRC's earlier affect-intensity lexicon scores four emotions rather than eight. Loaded
    without this check it would build a decoder whose four unlisted axes sit at rest forever —
    a plausible-looking instrument that is quietly measuring half of what it claims.
    """
    four_only = {k: v for k, v in ENTRIES.items()
                 if k in {"anger", "fear", "joy", "sadness"}}

    with pytest.raises(ValueError, match="anticipation, disgust, surprise, trust"):
        load_tables(_artefact(tmp_path, entries=four_only), [PLUTCHIK8])


def test_a_file_carrying_an_unmapped_emotion_is_refused(tmp_path: Path):
    """The other direction, and it raises rather than dropping — Stuart's ruling.

    A later lexicon version adding a ninth emotion is the case. Skipping it silently would lose
    data with no signal, which is exactly what ``folding.py``'s completeness guard was added for
    after an extra axis vanished into a comprehension and produced an ordinary-looking result.
    The cost is that a superset file breaks rather than degrading, and the fix is one line in
    ``PLUTCHIK8_FROM_NRC``.
    """
    with_ninth = ENTRIES | {"contempt": {"sneering": 0.8}}

    with pytest.raises(ValueError, match="contempt has no axis in plutchik8/1"):
        load_tables(_artefact(tmp_path, entries=with_ninth), [PLUTCHIK8])
