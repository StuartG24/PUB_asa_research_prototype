#
# NRC-EIL lexicon loading
#
# Decode & Infer, iteration 1 — a second table for the same matching algorithm


"""The NRC Emotion Intensity Lexicon, as keyword tables the decoder already knows how to use.

Roughly ten thousand English words with real-valued intensities obtained by best–worst scaling,
against Plutchik's eight. It replaces nothing: ``decode_keyword.py``'s hand-written tables stay
exactly as they are, and this module produces tables of the same shape from a different source,
so the two are comparable through one algorithm.

**This module reads a PREPARED artefact, not the lexicon as published.** The NRC lexicon may be
used freely for research and teaching but **may not be redistributed**, so it cannot ship beside
the module that reads it — the rule that puts `core/defaults.toml` next to `core/config.py` is
simply unavailable here. A notebook converts the published TSV into the JSON this loads, under
``data_in/``, which is already untracked. Consequences worth stating rather than discovering: a
fresh clone cannot construct a lexicon decoder until the notebook has been run, and the run
manifest's content hash becomes the only record of what was actually read, since a commit cannot
describe a file it does not contain.

**The artefact is deliberately inert.** The notebook performs format conversion and nothing else —
its keys are the *lexicon's* emotion names, unmapped, unrenamed and unthresholded. Every decision
that changes what the decoder believes lives here instead, in version-controlled code beside the
argument for it: which lexicon emotion reaches which axis, ``joy`` becoming ``happiness``, and the
magnitude floor. So regenerating the artefact is a no-op, and a checkout missing it is missing a
*file* rather than a *decision*.

**The artefact does not name a representation, and must not.** Its keys are ``joy`` and
``anticipation`` — the lexicon's vocabulary, not ``plutchik8/1``'s, which says ``happiness``. One
differing axis name is enough to make such a stamp false. Worse, it would put "which representation
is this lexicon native to" half in an untracked file and half in ``NATIVE`` below, leaving two
sources of truth that can disagree with no good way to resolve it. What the file *is* — an
identifier and a name — it carries; how the build reads it stays here.

**One module per lexicon, and that is the right granularity** because each needs its own mapping
anyway. A second lexicon brings its own ``NATIVE``, its own alias map and its own module, and
imports ``restrict`` from the same place this does.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from asa.core.representations import PLUTCHIK8, AffectRepresentation, EightEmotions
from asa.perception.decode_keyword import restrict

NATIVE = PLUTCHIK8
"""The representation this lexicon is annotated in. Every other table is restricted from it.

Declared in code rather than read from the artefact, deliberately — see the module docstring.
It is also what makes a second lexicon cheap: a lexicon native to a dimensional representation
would declare its own here and share nothing else.
"""

PLUTCHIK8_FROM_NRC: Mapping[str, str] = {
    "anger":        EightEmotions.ANGER,
    "anticipation": EightEmotions.ANTICIPATION,
    "disgust":      EightEmotions.DISGUST,
    "fear":         EightEmotions.FEAR,
    "joy":          EightEmotions.HAPPINESS,        # the one rename; see EightEmotions
    "sadness":      EightEmotions.SADNESS,
    "surprise":     EightEmotions.SURPRISE,
    "trust":        EightEmotions.TRUST,
}
"""Lexicon emotion → ``plutchik8/1`` axis.

**Total, and that is the point.** Every emotion the lexicon scores has an axis to land on, so
nothing is dropped in the act of loading. A coarser representation is reached afterwards, by
``restrict``, where the dropping is an operation with a name and a check rather than a silent
absence from a table literal.

``joy`` → ``happiness`` is the only entry where the two vocabularies disagree. The rename is
argued for on ``EightEmotions``; recorded here because this mapping is where somebody checking the
correspondence would look.
"""


def _native_table(prepared: Mapping[str, object], path: Path,
                  floor: float) -> Mapping[str, Mapping[str, float]]:
    """The artefact's entries as a ``plutchik8/1`` table, with both vocabularies reconciled.

    **Both directions of disagreement raise, and neither is hypothetical.** An emotion this
    module maps but the file does not carry means the wrong file: NRC's earlier affect-intensity
    lexicon scores four emotions rather than eight, and loading it would otherwise yield a
    decoder with four axes permanently at rest and nothing said about it. An emotion the file
    carries but this module does not map means the file has outgrown the mapping — a later
    lexicon version adding a ninth emotion — and silently dropping it would lose data with no
    signal, which is the failure mode ``folding.py``'s completeness guard exists for. Both are
    one line to fix and neither should be guessed at.

    ``floor`` is applied here rather than after restriction because it is a property of the
    lexicon, not of any representation derived from it. Entries at or below the resting value
    contribute nothing under the decoder's ``max`` and are dropped rather than carried.
    """
    entries = prepared.get("entries")
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: no 'entries' object — not a prepared lexicon")

    missing = set(PLUTCHIK8_FROM_NRC) - set(entries)
    if missing:
        named = ", ".join(sorted(missing))
        raise ValueError(f"{path}: no entries for {named} — wrong lexicon or wrong version")

    unmapped = set(entries) - set(PLUTCHIK8_FROM_NRC)
    if unmapped:
        named = ", ".join(sorted(unmapped))
        raise ValueError(f"{path}: {named} has no axis in {NATIVE.id} — mapping is out of date")

    threshold = max(floor, NATIVE.rest)
    return {axis: {word: score for word, score in entries[emotion].items() if score > threshold}
            for emotion, axis in PLUTCHIK8_FROM_NRC.items()}


@dataclass(frozen=True, slots=True)
class Lexicon:
    """Tables for the representations that were asked for, and the name to stamp on records.

    **The two travel together because they have to agree.** A caller that built its tables here
    and then passed a remembered constant to ``KeywordDecoder`` could label them with a lexicon
    they did not come from — a swapped file, a regenerated artefact, a copied line — and nothing
    downstream would catch it, because ``source`` is provenance and nothing branches on it.
    Returning the name beside the tables removes the opportunity rather than warning about it.
    """

    source: str
    tables: Mapping[str, Mapping[str, Mapping[str, float]]]     # keyed by representation id


def load_tables(path: Path, wanted: Iterable[AffectRepresentation],
                floor: float = 0.0) -> Lexicon:
    """One prepared lexicon file in, one keyword table per requested representation out.

    **Every table goes through ``restrict``, including ``NATIVE``'s own.** Restricting a
    representation onto itself keeps every axis and copies the entries, so there is no special
    case here and no path along which a table reaches a caller unchecked. A requested
    representation the lexicon cannot reach raises there, naming the axes it has no value for:
    ``basic4/1`` fails on ``anger_disgust`` and ``fear_surprise``, which is the collapse refusal
    arriving without this function having to know that ``basic4/1`` exists.

    **``source`` is composed from what was read, never from what the caller assumed.** The
    artefact names itself and that name reaches every record. A non-zero ``floor`` joins it,
    because two floors over one lexicon are two instruments and a run that cannot say which it
    used has unreproducible evidence — a stopgap until the manifest carries decoder parameters
    properly.

    ``path`` has no default. A module-level relative path would resolve against the working
    directory, working from the repository root and misbehaving quietly anywhere else; where the
    file lives is a composition-root decision that has no configuration key yet.
    """
    prepared = json.loads(path.read_text(encoding="utf-8"))
    if "id" not in prepared:
        raise ValueError(f"{path}: no 'id' — nothing to name the decoder's source with")

    native = _native_table(prepared, path, floor)
    return Lexicon(
        source=f"{prepared['id']}@{floor}" if floor else prepared["id"],
        tables={representation.id: restrict(native, NATIVE, representation)
                for representation in wanted},
    )
