#
# Test - perception
#

"""Tests for the producer side: the two ports, the text console adapter, the decoder and
the driver that runs them.

The adapter is a loop around a call, so what is worth testing is not that it reads. It is
the four things other components rely on: that it satisfies the port at all, that it tags
its records with its own name, that end of input *ends* rather than raises — since that is
what tells the evidence loop it may drain — and that reading does not freeze the event
loop, which is the one decision in this module that could be "simplified" away with
nothing failing.

The decoder is tested for its **guards and the shape of what it emits**, never for accuracy.
Whether a table scores well against labelled sentences is a research measure with its own
instrument, and a suite that failed when a lexicon scored 62% would be reporting a finding
as a defect and would be muted within a fortnight. Two other things are deliberately absent:
any assertion that the two representations agree on the axes they share, since their tables
are independent by design and such a test would pin data rather than behaviour; and any test
that ``decode`` needs to be ``async``, since this implementation never awaits and the port's
asynchrony exists for the LLM decoder — the annotation in the port test is what holds it.

The driver is tested for the four things the rest of the agent reads from it: that one
utterance produces exactly one published record, that publishing precedes submission, that a
decoder failure is contained, and that returning means the work is finished.
"""

import asyncio
import time
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from asa.core.affect import AffectEvidence, AffectObservation, Target, Utterance, utc_now
from asa.core.observers import Event, Observers
from asa.core.representations import BASIC4, EKMAN6, PLUTCHIK8
from asa.perception.base import AffectDecoder, InputSource
from asa.perception.decode_keyword import (
    BASIC4_KEYWORDS,
    DECODER,
    EKMAN6_KEYWORDS,
    NO_MATCH,
    KeywordDecoder,
    restrict,
)
from asa.perception.drive import run_perception
from asa.perception.text_console import SOURCE, TextConsole


def _scripted(*lines: str):
    """A reader returning each line in turn, then signalling end of input.

    Stands in for ``input``: same signature, same ``EOFError`` at the end, no keyboard.
    """
    remaining = list(lines)

    def read(prompt: str) -> str:
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    return read


async def _collect(source: InputSource) -> list[Utterance]:
    """Drain an adapter to a list — the ``async for`` a driver will run for real."""
    return [utterance async for utterance in source.events()]


def test_text_console_satisfies_the_input_source_port():
    """A protocol claim is a STATIC claim, so this is checked by pyright, not at runtime.

    The annotation is the test. ``isinstance`` against a protocol would only confirm that
    an ``events`` attribute exists — it cannot see the signature or the return type, and
    at step 3b that difference hid a real bug for an afternoon. ``test_types.py`` runs
    pyright over this file, so a signature drifting from the port fails the suite here.
    """
    source: InputSource = TextConsole()

    assert source is not None       # the annotation above is what actually asserts


def test_each_line_becomes_one_utterance_tagged_with_this_adapter():
    """Text through unchanged, and `source` set from the module constant.

    ``source`` is provenance: nothing branches on it, so a wrong value does not change
    behaviour — it mislabels every row this adapter writes, and is found at analysis.
    """
    console = TextConsole(read=_scripted("I just got the job!", "though I am nervous"))
    seen = asyncio.run(_collect(console))

    assert [utterance.text for utterance in seen] == [
        "I just got the job!",
        "though I am nervous",
    ]
    assert {utterance.source for utterance in seen} == {SOURCE}
    assert all(utterance.intended is None for utterance in seen)


def test_end_of_input_ends_the_stream_rather_than_raising():
    """``EOFError`` — Ctrl-D — must terminate the iterator cleanly.

    This is the shutdown signal, not an error condition: the driver's ``async for`` ends,
    perception's task finishes, and only then is the evidence loop allowed to drain. If
    this raised instead, a normal end of session would look identical to a crash and would
    take the drain with it.
    """
    console = TextConsole(read=_scripted())      # end of input immediately
    seen = asyncio.run(_collect(console))

    assert seen == []


def test_blank_lines_are_skipped():
    """Whitespace-only input yields nothing, and surrounding whitespace is trimmed.

    An empty utterance decodes to nothing, so a row for it would sit in
    ``utterances.jsonl`` with no evidence ever pointing at it, meaning only that somebody
    pressed Enter.
    """
    console = TextConsole(read=_scripted("", "   ", "  I just got the job!  ", "\t"))
    seen = asyncio.run(_collect(console))

    assert [utterance.text for utterance in seen] == ["I just got the job!"]


def test_the_blocking_read_does_not_freeze_the_event_loop():
    """The reason for ``asyncio.to_thread``, tested because nothing else would catch it.

    ``input`` blocks the thread it runs on, and the agent has one thread. Called directly,
    it would stop the intention planner, the evidence loop and the render loop for as long
    as a person sat thinking — with no error anywhere, just a robot that goes still
    whenever it is someone's turn to type.

    A concurrent task is the instrument: it can only advance if the event loop is still
    running during the read. Asserted as "more than zero" rather than a count, because the
    number depends on the machine while the property does not — without the thread the
    counter cannot advance at all.
    """
    async def scenario() -> tuple[int, list[Utterance]]:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.005)

        remaining = ["I just got the job!"]

        def slow_read(prompt: str) -> str:
            time.sleep(0.05)            # a person deciding what to say
            if not remaining:
                raise EOFError
            return remaining.pop(0)

        tick = asyncio.create_task(ticker())
        try:
            seen = await _collect(TextConsole(read=slow_read))
        finally:
            tick.cancel()

        return ticks, seen

    ticks, seen = asyncio.run(scenario())

    assert ticks > 0, "the event loop was frozen for the whole read"
    assert [utterance.text for utterance in seen] == ["I just got the job!"]


#
# ── Decode & Infer ──────────────────────────────────────────────────────────────────────
#


def _decode(decoder: KeywordDecoder, text: str,
            at: datetime | None = None) -> tuple[AffectObservation, Utterance]:
    """Run one sentence through a decoder, returning what it produced and what it was given.

    ``at`` is resolved here rather than passed through as conditional keyword arguments.
    ``Utterance(..., **({"at": at} if at else {}))`` reads neatly and cannot be type-checked:
    the checker cannot tell which parameter a dynamically built mapping lands in, so it tries
    the value against every one of them and reports three errors for one line.
    """
    utterance = Utterance(text=text, source=SOURCE,
                          at=at if at is not None else utc_now())
    return asyncio.run(decoder.decode(utterance)), utterance


def _basic4() -> KeywordDecoder:
    return KeywordDecoder(BASIC4, BASIC4_KEYWORDS)


def _ekman6() -> KeywordDecoder:
    return KeywordDecoder(EKMAN6, EKMAN6_KEYWORDS)


def test_keyword_decoder_satisfies_the_affect_decoder_port():
    """A static claim again, so the annotation is the test and pyright is the checker.

    It carries more than it looks. ``decode`` is declared ``async`` on the port for the
    benefit of an LLM implementation, and a maintainer who noticed this decoder never awaits
    anything could reasonably drop the keyword — at which point every caller would have to
    change with the implementation, which is the one thing a port exists to prevent. This
    line fails if that happens, and nothing at runtime would.
    """
    decoder: AffectDecoder = _basic4()

    assert decoder is not None      # the annotation above is what actually asserts


def test_a_table_naming_axes_the_representation_lacks_is_rejected():
    """The pairing guard, in both directions, and the type system cannot do this.

    ``StrEnum`` keys interoperate across representations and a table is annotated
    ``Mapping[str, ...]`` because the port must accept any of them, so pyright sees two
    compatible arguments. Paired wrongly and unchecked, the decoder would emit vectors
    claiming one representation and carrying another's axes — malformed records that nothing
    downstream validates, because nothing downstream can.
    """
    with pytest.raises(ValueError, match="ekman6/1 does not have"):
        KeywordDecoder(EKMAN6, BASIC4_KEYWORDS)

    with pytest.raises(ValueError, match="basic4/1 does not have"):
        KeywordDecoder(BASIC4, EKMAN6_KEYWORDS)


#
# ── restrict ────────────────────────────────────────────────────────────────────────────
#

PLUTCHIK8_SAMPLE: Mapping[str, Mapping[str, float]] = {
    "anger": {"furious": 0.9},
    "anticipation": {"eager": 0.7},         # no ekman6 axis to land on
    "disgust": {"revolted": 0.9},
    "fear": {"terrified": 0.9},
    "happiness": {"delighted": 0.9},
    "sadness": {"devastated": 0.9},
    "surprise": {"astonished": 0.9},
    "trust": {"reliable": 0.8},             # no ekman6 axis to land on
}
"""A minimal ``plutchik8/1`` table — one word per axis, and the two Ekman cannot name.

Deliberately not the real lexicon. What these tests check is the *operation*, and a fixture
small enough to read entirely makes a failure legible; a ten-thousand-word table would test
the same three lines while making every assertion a matter of trust.
"""


def test_restricting_to_a_subset_representation_keeps_exactly_its_axes():
    """The permitted derivation, and the one the lexicon depends on."""
    got = restrict(PLUTCHIK8_SAMPLE, PLUTCHIK8, EKMAN6)

    assert tuple(got) == EKMAN6.axes                    # declared order, not the table's
    assert got["anger"] == {"furious": 0.9}             # values carried across untouched
    assert "anticipation" not in got
    assert "trust" not in got


def test_restricting_a_representation_to_itself_is_the_identity():
    """No special case in the loader, which is why this is worth pinning.

    ``load_tables`` will put every requested representation through this function, including
    the lexicon's own. If identity did not work, that would need a branch — and a branch is
    a path along which a table could reach a caller unchecked.
    """
    got = restrict(PLUTCHIK8_SAMPLE, PLUTCHIK8, PLUTCHIK8)

    assert tuple(got) == PLUTCHIK8.axes
    assert got == PLUTCHIK8_SAMPLE


def test_restricting_onto_merged_axes_is_refused():
    """The collapse refusal, enforced rather than documented.

    ``basic4/1`` is coarser than ``plutchik8/1`` in the ordinary sense, and that is exactly why
    the check cannot be "is the target coarser". Its merged axes exist in neither of the other
    representations, so filling them would mean combining two that do — asserting that fear and
    surprise are one thing. Both are named, because a message naming one would leave a reader
    thinking a single edit would fix it.
    """
    with pytest.raises(ValueError, match="anger_disgust, fear_surprise"):
        restrict(PLUTCHIK8_SAMPLE, PLUTCHIK8, BASIC4)


def test_restricting_cannot_widen():
    """The same rule read backwards, and it guards a case the constructor cannot see.

    ``KeywordDecoder``'s guard is the table's axes *minus* the representation's, so it catches
    extras and structurally cannot catch omissions — an empty axis is legal by design. So an
    ``ekman6/1`` table paired with ``plutchik8/1`` constructs silently, and since ``StrEnum``
    members hash as their values, six of eight axes populate: the result looks plausible rather
    than broken. Refusing to widen is what closes that door on the derived path.
    """
    with pytest.raises(ValueError, match="anticipation, trust"):
        restrict(EKMAN6_KEYWORDS, EKMAN6, PLUTCHIK8)


def test_a_restricted_table_does_not_alias_the_one_it_came_from():
    """A dict comprehension copies the outer mapping and shares the inner ones.

    Without the copy, a write through a derived table reaches the module constant it was
    derived from and changes what every decoder built afterwards in that process matches on.
    The annotation does not stop it: ``Mapping`` has no ``__setitem__``, but the object is a
    ``dict`` and the write succeeds at runtime. Same lesson as ``decay.py``'s — ``frozen`` and
    read-only annotations protect the binding, never the container.
    """
    got = restrict(PLUTCHIK8_SAMPLE, PLUTCHIK8, EKMAN6)

    assert got["anger"] is not PLUTCHIK8_SAMPLE["anger"]

    got["anger"]["incandescent"] = 0.95                 # type: ignore[index]
    assert "incandescent" not in PLUTCHIK8_SAMPLE["anger"]


def test_every_axis_of_the_representation_is_present_at_rest():
    """Full-width output, and the affect model depends on it silently.

    The representation names a basis, so a vector in it carries every axis of that basis.
    Emitting only the axes that fired would hand the fold an ambiguity — an absent axis
    meaning either "no claim, leave it alone" or "claimed nothing", which are opposite
    behaviours — and it would put missing values into the analysis.
    """
    got, _ = _decode(_basic4(), "I am happy")

    assert set(got.affect.values) == set(BASIC4.axes)
    assert got.affect.values["sadness"] == BASIC4.rest


def test_each_representation_yields_its_own_axes():
    """The plumbing test that survives the tables being independent.

    It asserts nothing about *which* magnitudes either produces — that would pin the
    lexicons rather than the mechanism. What it pins is that one sentence through two
    decoders comes back in two different bases, each stamped with its own identifier.
    """
    from_basic4, _ = _decode(_basic4(), "I was terrified")
    from_ekman6, _ = _decode(_ekman6(), "I was terrified")

    assert from_basic4.affect.representation == BASIC4.id
    assert from_ekman6.affect.representation == EKMAN6.id
    assert set(from_basic4.affect.values) == set(BASIC4.axes)
    assert set(from_ekman6.affect.values) == set(EKMAN6.axes)


def test_a_sentence_with_no_emotion_word_decodes_at_rest():
    """Absence is an answer, and it is reported rather than withheld.

    The sentence is the design's own baseline scenario, which iteration 1 fails: getting a
    job is a fact from which happiness must be *inferred*, and this decoder only decodes
    affect that was stated. Pinned so that the failure stays visible and deliberate rather
    than being quietly patched with a phrase entry one afternoon.
    """
    got, _ = _decode(_basic4(), "I just got the job!")

    assert set(got.affect.values.values()) == {BASIC4.rest}
    assert got.rationale == NO_MATCH


def test_only_whole_words_match():
    """"good" must not fire inside "goodbye", and substring matching is the obvious wrong turn.

    A false positive here is invisible: it produces a plausible mild reading that looks
    exactly like a real one, and it would shift every benchmark score by an unknown amount.
    """
    got, _ = _decode(_basic4(), "goodbye everyone")

    assert got.rationale == NO_MATCH


def test_matches_on_one_axis_combine_by_max_not_sum():
    """Two happiness words give the stronger one, not their total.

    Summing would leave the representation's range — 0.7 and 0.9 make 1.6 — and would make a
    word repeated for emphasis read as a stronger feeling than it is.
    """
    got, _ = _decode(_basic4(), "I was happy, then delighted")

    assert got.affect.values["happiness"] == 0.9


def test_separate_axes_rise_independently():
    """Magnitudes are independent intensities, not a distribution, so both axes hold."""
    got, _ = _decode(_basic4(), "I'm delighted but astonished")

    assert got.affect.values["happiness"] == 0.9
    assert got.affect.values["fear_surprise"] == 0.9


def test_the_estimate_carries_the_utterance_timestamp_not_the_decode_time():
    """The estimate is a claim about what the human felt *when they spoke*.

    Written with a timestamp months in the past, so a decoder that read a clock instead
    fails by an unmistakable margin rather than by microseconds. It matters most for the
    decoder this one is standing in for: an LLM taking most of a second would otherwise
    shift the whole recorded timeline by its own latency.
    """
    long_ago = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    got, utterance = _decode(_basic4(), "I am happy", at=long_ago)

    assert got.at == long_ago
    assert got.at == utterance.at


def test_the_record_names_its_producer_and_its_input_and_claims_no_confidence():
    """Provenance, and the one field the decoder must leave empty.

    ``confidence`` stays ``None`` because a keyword matched or it did not. A fabricated
    ``1.0`` would make this decoder look more certain than an LLM honestly reporting 0.7,
    confounding the comparison the decoder exists to be one half of.
    """
    got, utterance = _decode(_basic4(), "I am happy")

    assert got.source == DECODER
    assert got.target is Target.OTHER
    assert got.of_input == utterance.id
    assert got.confidence is None


def test_the_rationale_records_every_word_that_fired():
    """The benchmark's dependency: a row must explain itself without a re-run.

    Both words appear even though only one survived the ``max``, because a word that fired
    and was overruled is exactly what an error analysis is looking for. Without this, a
    mild reading produced by a false positive is indistinguishable from a genuinely mild one.
    """
    got, _ = _decode(_basic4(), "I was happy, then delighted")

    assert got.rationale == "matched: happiness=happy, happiness=delighted"


#
# ── The producer task ───────────────────────────────────────────────────────────────────
#


class _BrokenDecoder:
    """A decoder that always raises, standing in for an LLM call that timed out."""

    async def decode(self, utterance: Utterance) -> AffectObservation:
        raise RuntimeError("the model provider timed out")


def _drive(source: InputSource, decoder: AffectDecoder) -> tuple[list[Event], list[AffectEvidence]]:
    """Run the driver over a source, returning what it published and what it submitted."""
    published: list[Event] = []
    submitted: list[AffectEvidence] = []

    observers = Observers()
    observers.register(published.append)

    asyncio.run(run_perception(source, decoder, submitted.append, observers))
    return published, submitted


def test_the_driver_publishes_the_utterance_and_submits_only_the_evidence():
    """Each utterance is recorded once, and the evidence links back to it.

    The count is the interesting half. Evidence is published by the evidence loop on behalf
    of every producer, so a driver that published it here as well would double every row in
    ``evidence.jsonl`` with nothing failing anywhere — an error that surfaces much later as
    an analysis that quietly counts each observation twice.
    """
    console = TextConsole(read=_scripted("I am happy", "I am sad"))
    published, submitted = _drive(console, _basic4())

    utterances = [event for event in published if isinstance(event, Utterance)]
    assert len(utterances) == len(published) == 2
    assert [evidence.of_input for evidence in submitted] == [utterance.id for utterance in utterances]
    assert [evidence.at for evidence in submitted] == [utterance.at for utterance in utterances]


def test_the_utterance_is_published_before_its_evidence_is_submitted():
    """Ordering is the claim, so it is asserted on one interleaved trace, not on two lists.

    Two separate lists would pass whatever the order was. What this pins is the failure
    signature the design reads at analysis time: an utterance row with no evidence row after
    it means the decode failed. Publish after decoding instead and a failed decode leaves no
    trace of the utterance at all, so the participant's turn vanishes from the record.
    """
    trace: list[str] = []

    observers = Observers()
    observers.register(lambda event: trace.append("published"))

    console = TextConsole(read=_scripted("I am happy", "I am sad"))
    asyncio.run(run_perception(console, _basic4(),
                               lambda evidence: trace.append("submitted"), observers))

    assert trace == ["published", "submitted", "published", "submitted"]


def test_a_failing_decoder_costs_one_utterance_and_not_the_session():
    """Containment, and it is the opposite of the evidence loop's policy on purpose.

    The decoder becomes an LLM call, so a failure is a transient and the useful response is
    to lose that observation and carry on. A raise from the affect model is a bug and is
    fatal. Both utterances still appear in the record, which is what makes the gap readable.
    """
    console = TextConsole(read=_scripted("I am happy", "I am sad"))
    published, submitted = _drive(console, _BrokenDecoder())

    assert len(published) == 2
    assert submitted == []


def test_the_driver_returns_only_once_the_last_utterance_has_been_submitted():
    """Returning is the "producers have stopped" signal, and the runtime acts on it.

    On that signal the runtime drains the queue and cancels the consumer. If this returned
    with work still outstanding, the drain would run before the last observation had been
    submitted and the final turn of a session would be lost — with the recording looking
    complete, because a drained queue is exactly what a clean shutdown produces.
    """
    console = TextConsole(read=_scripted("I am happy", "I am sad", "I am angry"))
    _, submitted = _drive(console, _basic4())

    assert len(submitted) == 3
