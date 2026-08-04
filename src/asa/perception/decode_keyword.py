#
# Keyword decoding
#
# Decode & Infer, iteration 1 — stated affect only, and deliberately no inference


"""Sentence in, ``ekman4/1`` vector out, by looking for emotion words.

The first implementation of Decode & Infer and a deliberately poor one. It decodes affect
that the human has **stated** — "I am happy" — and it cannot infer affect from a situation.
"I just got the job!" contains no emotion word and comes back neutral, which is not a
defect to be patched but the exact gap the planned LLM decoder exists to fill: the element
is Decode *and Infer*, and this half only decodes.

**Why the table is a module constant and not configuration.** Configuration carries what is
common across implementations of a port, because a config file outlives the build that
wrote it and unknown keys are an error. A block shaped around keyword rows could not
express an LLM decoder's parameters — a model identifier, a prompt, a temperature — so
adding one would make every research config written against it unloadable the day the real
decoder lands. What belongs in configuration is the selection, ``strategy = "keyword"``,
and that waits until something reads it.

**Three limitations, all real and none worth patching here.**

*Negation is invisible.* "I am not happy" decodes as happiness at 0.7. Handling it properly
means parsing, which is the LLM's job.

*Only whole words match, so phrases cannot.* Matching on substrings instead would be worse:
"ill" would fire inside "will".

*Magnitudes are not measurements.* They are a hand-set ordering — "delighted" above
"pleased" — and are comparable only within this decoder. Nothing calibrated them, and the
``source`` on every record it writes is what stops a later reader treating them as though
something had.
"""

import re
from collections.abc import Mapping

from asa.core.affect import AffectObservation, AffectVector, Emotion, Target, Utterance

SPACE = "ekman4/1"
"""The space this decoder's table is written in.

Not configurable, and that is the difference between this and a tunable: a table of English
emotion words *is* an Ekman-4 table, so a decoder cannot be asked to emit ``vad/1`` by
changing a setting. Components that interpret a vector assert on this rather than assuming.
"""

DECODER = "decoder:rule"
"""This decoder's name, written once — the same placement rule as an adapter's ``SOURCE``.

``rule`` rather than ``keyword``, and the mismatch with the module name is deliberate. The
vocabulary splits decoders the way the research does, rule against LLM, and it is written
into every record this ever produces. Recorded strings have to stay readable when the code
around them has been reorganised, so they name the approach rather than the file.
"""

NO_MATCH = "no keyword matched"
"""The ``rationale`` written when a sentence contains no emotion word.

A fixed string rather than ``None`` so that a neutral reading is *stated* in the record and
can be counted with a grep. ``None`` would mean "this producer does not fill rationale",
which is a different claim and the one an LLM decoder's failure would want.
"""

KEYWORDS: Mapping[Emotion, Mapping[str, float]] = {
    Emotion.HAPPINESS: {
        "good": 0.4, "glad": 0.6, "pleased": 0.6, "great": 0.6, "happy": 0.7,
        "joyful": 0.8, "excited": 0.8, "wonderful": 0.8, "delighted": 0.9, "thrilled": 0.9,
    },
    Emotion.SADNESS: {
        "disappointed": 0.6, "lonely": 0.7, "sad": 0.7, "unhappy": 0.7, "upset": 0.7,
        "gutted": 0.8, "miserable": 0.9, "devastated": 0.9,
    },
    Emotion.ANGER: {
        "annoyed": 0.5, "irritated": 0.5, "frustrated": 0.6, "angry": 0.8,
        "outraged": 0.9, "furious": 0.9, "livid": 0.9,
    },
    Emotion.SURPRISE: {
        "unexpected": 0.6, "startled": 0.7, "surprised": 0.8, "amazed": 0.8,
        "astonished": 0.9, "shocked": 0.9,
    },
}
"""Emotion word → magnitude, grouped by the axis it contributes to.

Grouped this way because that is how it is read and revised — as four lists to argue about,
which is the form it would take in a write-up. Polysemous words are left out rather than
included and hedged: "down", "low", "mad" and "cross" all carry an unrelated everyday
sense, and a decoder that fires on "down the road" produces evidence that looks exactly like
evidence.
"""


def _words(text: str) -> set[str]:
    """The lowercased words of a sentence, as a set for membership testing.

    ``[a-z]+`` after lowercasing, so punctuation and digits split words rather than joining
    them and "I'm" becomes "i" and "m" — harmless, since no entry in the table contains an
    apostrophe. A set because the question asked of it is only ever "does this word appear",
    and a word said twice is not felt twice.
    """
    return set(re.findall(r"[a-z]+", text.lower()))


class KeywordDecoder:
    """Matches emotion words against ``KEYWORDS`` and reports what it found.

    No ``__init__``, because there is nothing to construct with — the table is the module's.
    That is what the port's shape costs here, and it is worth it one step later: an LLM
    decoder takes a client, a model and a prompt, so the port has to be a class with a
    method rather than a bare callable.

    Stateless in the strong sense the design asks for. It holds nothing between calls, so
    the same sentence decodes to the same vector whenever it arrives, whatever has been said
    before — which is what makes a rule-versus-LLM comparison a comparison of decoders
    rather than of two different accumulated histories.
    """

    async def decode(self, utterance: Utterance) -> AffectObservation:
        """One utterance to one observation of the human's affect.

        **All four axes are always present, zeros included.** ``ekman4/1`` names the basis,
        so a vector in it carries every axis of that basis; a missing one would be a
        malformed vector rather than a modest one. Two things follow. Every row in
        ``evidence.jsonl`` has the same four numbers in the same order, so the analysis has
        no missing values to decide about. And the affect model is spared an ambiguity it
        would otherwise have to resolve — an omitted axis meaning either "no claim, leave it
        alone" or "claimed zero", which are opposite behaviours and would be settled by
        accident rather than by argument.

        **A neutral sentence therefore decodes to the zero vector**, not to nothing. Under a
        vector representation that *is* "no affect expressed", exactly, which is why there is
        no NEUTRAL axis to report instead. What the model should do with a zero observation
        is the fold's decision, not this one's — the decoder reports, the model believes.

        **Several matches all contribute, combined per axis by ``max``.** "Delighted but
        astonished" is an ordinary human state and the representation holds independent
        intensities rather than a distribution, so both axes rise. Summing within an axis
        would leave the range and would make a word repeated for emphasis read as a stronger
        feeling; ``max`` says the strongest word stands.

        **The magnitudes are keyed by ``Emotion`` members and that is safe deliberately.**
        ``StrEnum`` hashes and compares as its *value*, so this mapping is equal to and
        interchangeable with one keyed by plain strings, and it survives the round trip
        through JSON unchanged. A plain ``Enum`` would hash by member name and would not.
        Iterating ``Emotion`` gives declaration order, so the axes land in a stable order in
        every record.

        ``confidence`` is left ``None``: a keyword matched or it did not, and a fabricated
        ``1.0`` would make this decoder look more certain than an LLM honestly reporting
        0.7 — confounding the comparison.

        **``rationale`` carries the words that fired, and it is there for the benchmark.**
        Measuring how well decoding works means asking not only whether a sentence scored
        correctly but *why* it did not, and the vector alone cannot say — "good grief"
        scoring as mild happiness looks identical to a sentence that really was mildly
        happy. Written as ``axis=word`` pairs so a row explains itself without the reader
        holding the table, and every firing word appears including one that lost the
        ``max``, since a word that fired and was overruled is exactly what an error
        analysis is looking for. Ordering follows the table, so the pairs come out in the
        same axis order as the vector beside them.

        That makes perception a producer of ``rationale``, which iteration 1 had assumed
        only deliberation would be. The field's purpose is unchanged — it is the audit
        trail for why a piece of evidence says what it does — and ``source`` remains what
        distinguishes perception's evidence from anything else's.

        **This never raises**, because there is no failure mode: absence of a keyword is an
        answer. The port's contract still says a decoder raises when it cannot do its job,
        and that clause is there for the LLM implementation, where a timeout and a genuinely
        neutral sentence must not produce the same record.
        """
        words = _words(utterance.text)
        values: dict[str, float] = {emotion: 0.0 for emotion in Emotion}
        matched: list[str] = []

        for emotion, table in KEYWORDS.items():
            for word, magnitude in table.items():
                if word in words:
                    values[emotion] = max(values[emotion], magnitude)
                    matched.append(f"{emotion}={word}")

        return AffectObservation(
            target=Target.OTHER,
            affect=AffectVector(space=SPACE, values=values),
            source=DECODER,
            rationale=("matched: " + ", ".join(matched)) if matched else NO_MATCH,
            of_input=utterance.id,
            at=utterance.at,       # what they felt when they spoke, not when we finished parsing
        )
