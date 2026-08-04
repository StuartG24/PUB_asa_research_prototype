#
# Keyword decoding
#
# Decode & Infer, iteration 1 — stated affect only, and deliberately no inference


"""Sentence in, affect vector out, by looking for emotion words.

The first implementation of Decode & Infer and a deliberately poor one. It decodes affect
that the human has **stated** — "I am happy" — and it cannot infer affect from a situation.
"I just got the job!" contains no emotion word and comes back at rest, which is not a defect
to be patched but the exact gap the planned LLM decoder exists to fill: the element is
Decode *and Infer*, and this half only decodes.

**One matching algorithm, one table per representation.** The class takes the representation
it speaks and the table to speak it with, so adding a representation adds a table rather than
a decoder. Which representation a run uses is a configuration choice, and only one can be
live at a time — the affect model holds a single belief, so there is nowhere to put a second.

**The tables are independent, with nothing shared between them.** ``basic4/1`` merges fear
with surprise and anger with disgust; ``ekman6/1`` holds them apart. A shared core would have
to assert an equivalence between the two, which is a theoretical claim rather than an
implementation convenience. The honest cost: happiness and sadness exist in both and their
entries currently coincide, but they are *maintained* separately, so if a comparison between
the two representations ever differs on those axes, check the tables before concluding
anything about the representations.

**A coarser representation simply has no word for what it cannot name.** ``basic4/1`` has no
entry for revulsion beyond what sits on its merged ``anger_disgust`` axis, and where a
sentence has no axis to land on it decodes at rest rather than being mapped to the nearest
thing. Collapsing would assert that disgust is a kind of anger, which is contested and would
then be buried in a lookup table — and it would ruin the comparison, since a wrong answer
could be the decoder or the mapping with no way to tell. The ground truth in a benchmark set
must follow the same rule.

**Why the tables are module constants and not configuration.** Configuration carries what is
common across implementations of a port, because a config file outlives the build that wrote
it and unknown keys are an error. A block shaped around keyword rows could not express an LLM
decoder's parameters — a model identifier, a prompt, a temperature — so adding one would make
every research config written against it unloadable the day the real decoder lands. What
belongs in configuration is the selection, ``strategy = "keyword"``, and that waits until
something reads it.

**Three limitations, all real and none worth patching here.**

*Negation is invisible.* "I am not happy" decodes as happiness. Handling it properly means
parsing, which is the LLM's job.

*Only whole words match, so phrases cannot.* Matching on substrings instead would be worse:
"ill" would fire inside "will".

*Magnitudes are not measurements.* They are a hand-set ordering — "delighted" above
"pleased" — and are comparable only within one table. Nothing calibrated them, and the
``source`` and ``representation`` on every record are what stop a later reader treating them
as though something had.
"""

import re
from collections.abc import Mapping

from asa.core.affect import AffectObservation, AffectVector, Target, Utterance
from asa.core.representations import AffectRepresentation, FourEmotions, SixEmotions

DECODER = "decoder:rule"
"""This decoder's name, written once — the same placement rule as an adapter's ``SOURCE``.

``rule`` rather than ``keyword``, and the mismatch with the module name is deliberate. The
vocabulary splits decoders the way the research does, rule against LLM, and it is written
into every record this ever produces. Recorded strings have to stay readable when the code
around them has been reorganised, so they name the approach rather than the file.

It does **not** name the representation, because the record already carries that on the
vector. One producer, one name; the representation is a separate axis of the data.
"""

NO_MATCH = "no keyword matched"
"""The ``rationale`` written when a sentence contains no emotion word.

A fixed string rather than ``None`` so that a reading at rest is *stated* in the record and
can be counted with a grep. ``None`` would mean "this producer does not fill rationale",
which is a different claim and the one an LLM decoder's failure would want.
"""

#
# ── basic4/1 keywords ───────────────────────────────────────────────────────────────────
#

BASIC4_KEYWORDS: Mapping[str, Mapping[str, float]] = {
    FourEmotions.HAPPINESS: {
        "good": 0.4, "glad": 0.6, "pleased": 0.6, "great": 0.6, "happy": 0.7,
        "joyful": 0.8, "excited": 0.8, "wonderful": 0.8, "delighted": 0.9, "thrilled": 0.9,
    },
    FourEmotions.SADNESS: {
        "disappointed": 0.6, "lonely": 0.7, "sad": 0.7, "unhappy": 0.7, "upset": 0.7,
        "gutted": 0.8, "miserable": 0.9, "devastated": 0.9,
    },
    FourEmotions.FEAR_SURPRISE: {
        "nervous": 0.5, "unexpected": 0.6, "anxious": 0.6, "worried": 0.6, "startled": 0.7,
        "surprised": 0.8, "amazed": 0.8, "scared": 0.8, "afraid": 0.8, "frightened": 0.8,
        "astonished": 0.9, "shocked": 0.9, "terrified": 0.9,
    },
    FourEmotions.ANGER_DISGUST: {
        "annoyed": 0.5, "irritated": 0.5, "distasteful": 0.5, "frustrated": 0.6,
        "angry": 0.8, "disgusted": 0.8, "sickened": 0.8, "revolting": 0.8,
        "revolted": 0.9, "repulsed": 0.9, "outraged": 0.9, "furious": 0.9, "livid": 0.9,
    },
}
"""Emotion word → magnitude for ``basic4/1``, grouped by the axis it contributes to.

Grouped this way because that is how it is read and revised — as four lists to argue about,
which is the form it would take in a write-up. Polysemous words are left out rather than
included and hedged: "down", "low", "mad" and "cross" all carry an unrelated everyday sense,
and a decoder that fires on "down the road" produces evidence that looks exactly like
evidence.

**Word coverage is kept level with ``EKMAN6_KEYWORDS`` by hand, and that is the standing cost
of keeping the tables independent.** These two representations differ in *resolution*, not in
*coverage*: ``basic4/1``'s merged axes between them span everything ``ekman6/1`` splits, so
there is no emotion one can name and the other cannot. A word present in one table and absent
from the other therefore produces a difference that looks representational and is not — the
confound that would quietly invalidate a comparison. Adding a word to either table means
deciding, deliberately, which axis it belongs on in the other.
"""

#
# ── ekman6/1 keywords ───────────────────────────────────────────────────────────────────
#

EKMAN6_KEYWORDS: Mapping[str, Mapping[str, float]] = {
    SixEmotions.ANGER: {
        "annoyed": 0.5, "irritated": 0.5, "frustrated": 0.6, "angry": 0.8,
        "outraged": 0.9, "furious": 0.9, "livid": 0.9,
    },
    SixEmotions.DISGUST: {
        "distasteful": 0.5, "revolting": 0.8, "sickened": 0.8, "disgusted": 0.8,
        "repulsed": 0.9, "revolted": 0.9,
    },
    SixEmotions.FEAR: {
        "nervous": 0.5, "anxious": 0.6, "worried": 0.6, "scared": 0.8, "afraid": 0.8,
        "frightened": 0.8, "terrified": 0.9,
    },
    SixEmotions.HAPPINESS: {
        "good": 0.4, "glad": 0.6, "pleased": 0.6, "great": 0.6, "happy": 0.7,
        "joyful": 0.8, "excited": 0.8, "wonderful": 0.8, "delighted": 0.9, "thrilled": 0.9,
    },
    SixEmotions.SADNESS: {
        "disappointed": 0.6, "lonely": 0.7, "sad": 0.7, "unhappy": 0.7, "upset": 0.7,
        "gutted": 0.8, "miserable": 0.9, "devastated": 0.9,
    },
    SixEmotions.SURPRISE: {
        "unexpected": 0.6, "startled": 0.7, "surprised": 0.8, "amazed": 0.8,
        "astonished": 0.9, "shocked": 0.9,
    },
}
"""Emotion word → magnitude for ``ekman6/1``, grouped by the axis it contributes to.

Written independently of ``BASIC4_KEYWORDS`` rather than derived from it. The six-way split
is not a refinement of the four-way one: "shocked" is surprise here and shares an axis with
fear there, and neither is a subset of the other.
"""

#
# ── The decoder ─────────────────────────────────────────────────────────────────────────
#


def _words(text: str) -> set[str]:
    """The lowercased words of a sentence, as a set for membership testing.

    ``[a-z]+`` after lowercasing, so punctuation and digits split words rather than joining
    them and "I'm" becomes "i" and "m" — harmless, since no entry in either table contains
    an apostrophe. A set because the question asked of it is only ever "does this word
    appear", and a word said twice is not felt twice.
    """
    return set(re.findall(r"[a-z]+", text.lower()))


class KeywordDecoder:
    """Matches emotion words against one table and reports what it found.

    **The constructor is where the representation and the table are made to agree**, once,
    rather than being trusted at every call. It has to be checked in code, and the reason is
    narrower than "the type system cannot help". ``StrEnum`` members compare and hash as
    their values, so one representation's axis name is a valid key in another's mapping — and
    a type checker *does* catch that where it can infer the specific enum as the key type.
    What it cannot catch is this: a table is annotated ``Mapping[str, ...]``, because the
    port has to accept whichever representation's table it is given, and that annotation
    erases the distinction the checker was relying on. The hazard survives precisely where
    the port makes the annotation unavoidable.

    An axis with **no** entries is allowed rather than rejected. It can never fire, so it is
    always at rest — which is a fact about the instrument worth surfacing in a benchmark
    result, not a construction error. A table naming an axis the representation does not
    have is the opposite case: it is a pairing mistake and cannot be anything else.

    Stateless in the strong sense the design asks for. It holds nothing between calls, so
    the same sentence decodes to the same vector whenever it arrives, whatever has been said
    before. That is what makes a rule-versus-LLM comparison a comparison of decoders rather
    than of two different accumulated histories — and it is also what makes benchmarking
    tractable, since scoring is a loop over rows with no agent, no clock and no session.
    """

    def __init__(self, representation: AffectRepresentation,
                 table: Mapping[str, Mapping[str, float]]) -> None:
        unknown = set(table) - set(representation.axes)
        if unknown:
            named = ", ".join(sorted(unknown))
            raise ValueError(
                f"table names axes {representation.id} does not have: {named}"
            )
        self._representation = representation
        self._table = table

    async def decode(self, utterance: Utterance) -> AffectObservation:
        """One utterance to one observation of the human's affect.

        **Every axis of the representation is present, at rest where nothing fired.** The
        representation names a basis, so a vector in it carries every axis of that basis; a
        missing one would be a malformed vector rather than a modest one. Two things follow.
        Every row in ``evidence.jsonl`` has the same axes in the same order, so the analysis
        has no missing values to decide about. And the affect model is spared an ambiguity it
        would otherwise have to resolve — an omitted axis meaning either "no claim, leave it
        alone" or "claimed nothing", which are opposite behaviours and would be settled by
        accident rather than by argument.

        **A sentence with no emotion word therefore decodes to the rest vector**, not to
        nothing. Under a vector representation that *is* "no affect expressed", exactly,
        which is why there is no NEUTRAL axis to report instead. What the model should do
        with such an observation is the fold's decision, not this one's — the decoder
        reports, the model believes.

        **Several matches all contribute, combined per axis by ``max``.** "Delighted but
        astonished" is an ordinary human state and the representation holds independent
        intensities rather than a distribution, so both axes rise. Summing within an axis
        would leave the range and would make a word repeated for emphasis read as a stronger
        feeling; ``max`` says the strongest word stands.

        **The axes are walked in the representation's order, not the table's.** The table is
        a literal somebody wrote and its order is a convention; the representation's order is
        the one the record is written in. Driving the loop from the representation makes the
        rationale's pairs line up with the vector beside them however the table was arranged,
        and gives an axis with no entries nothing special to do.

        **``rationale`` carries the words that fired, and it is there for the benchmark.**
        Measuring how well decoding works means asking not only whether a sentence scored
        correctly but *why* it did not, and the vector alone cannot say — "good grief"
        scoring as mild happiness looks identical to a sentence that really was mildly
        happy. Written as ``axis=word`` pairs so a row explains itself without the reader
        holding the table, and every firing word appears including one that lost the
        ``max``, since a word that fired and was overruled is exactly what an error analysis
        is looking for.

        ``confidence`` is left ``None``: a keyword matched or it did not, and a fabricated
        ``1.0`` would make this decoder look more certain than an LLM honestly reporting
        0.7 — confounding the comparison.

        **This never raises**, because there is no failure mode: absence of a keyword is an
        answer. The port's contract still says a decoder raises when it cannot do its job,
        and that clause is there for the LLM implementation, where a timeout and a genuinely
        affectless sentence must not produce the same record.
        """
        words = _words(utterance.text)
        values: dict[str, float] = dict.fromkeys(self._representation.axes, self._representation.rest)
        matched: list[str] = []

        for axis in self._representation.axes:
            for word, magnitude in self._table.get(axis, {}).items():
                if word in words:
                    values[axis] = max(values[axis], magnitude)
                    matched.append(f"{axis}={word}")

        return AffectObservation(
            target=Target.OTHER,
            affect=AffectVector(representation=self._representation.id, values=values),
            source=DECODER,
            rationale=("matched: " + ", ".join(matched)) if matched else NO_MATCH,
            of_input=utterance.id,
            at=utterance.at,       # what they felt when they spoke, not when we finished parsing
        )
