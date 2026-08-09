#
# Test - the reconstruction guarantee
#

"""§9.5's guarantee, tested rather than promised.

    **The evidence together with the run's parameters must be sufficient to recompute the
    agent's state at any instant within the run.**

That is the claim a researcher actually depends on. The affect model computes a belief only
when someone looks (§9.5), so there is no continuous record of how the belief moved — the
model *is* the temporal record, and the way to inspect a past run is to rebuild a model from
what was recorded and ask it. If the recorded stream turns out to be insufficient, nothing
raises: the run simply cannot be reconstructed, and it is discovered after the pilot.

**In memory, and that is a sequencing decision rather than a shortcut** *(§15, v0.6)*.
`evidence.jsonl` does not exist until build step 12, so a test written only against the file
would leave the guarantee undefended through steps 6, 8 and 10 — every one of which can break
it. This runs against an in-memory evidence sequence, which is what the observer registry
already yields, and step 12 extends it to read the same assertions from disk.

**The evidence comes from the observer registry, not from the list this file submitted**, and
that is the whole design of the test. Reconstructing from the script would prove only that the
model is deterministic. Reconstructing from what was *published* is what pins the claim that
the record is sufficient — if the model ever came to depend on something the stream does not
carry, this fails.

`fresh_since` is exactly such a thing, and it is why this test earns its place at step 6 rather
than step 12. Currency appears in no record and is derivable only by replaying the evidence in
order through the same policies (§9.3, v0.6).

**And a reconstruction that cannot fail proves nothing**, so two tests vary a single recorded
parameter and require the rebuild to diverge — §15 asks for exactly that check.
"""

import asyncio
import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from asa.affect_model.belief import AffectModel
from asa.affect_model.folding import Assign, ConfidenceWeighted
from asa.core.affect import AffectEvidence, AffectState, AffectVector, Target
from asa.core.loops import EvidenceLoop
from asa.core.observers import Event, Observers
from asa.core.representations import EKMAN6

T0 = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
HALF_LIFE = 45.0
UNSTATED = 0.5

TIMEOUT = 2.0
"""The live run drives the real evidence loop, so it inherits that loop's failure mode.

Found by teeth-checking this file rather than by reading it: a break that makes the model raise
does **not** fail this test, it *hangs* it — `drain` waits for one acknowledgement per item
taken off the queue, and a consumer that has died takes no more. The first attempt at verifying
these tests had teeth had to be killed after two minutes. Same reasoning and same value as
`test_runtime.py`, which is the other file that drives the loop for real.
"""

SCRIPT: tuple[tuple[str, float, Target | None, float, float | None], ...] = (
    ("fold", 0, Target.OTHER, 0.9, 0.9),        # confident — moves the belief and renews it
    ("fold", 15, Target.OTHER, 0.6, None),      # confidence UNSTATED — the rule decoder's shape
    ("probe", 20, None, 0.0, None),             # mid-decay, with nothing having happened
    ("fold", 30, Target.OTHER, 0.4, 0.2),       # hesitant — informs without renewing
    ("probe", 45, None, 0.0, None),
    ("fold", 60, Target.SELF, 0.7, None),       # a different target, a different policy
    ("probe", 75, None, 0.0, None),
    ("fold", 90, Target.EXPRESSED, 0.7, None),  # a fact, assigned, never ageing
    ("probe", 200, None, 0.0, None),            # long after everything, well into the tail
)
"""A run with something of everything the model does, because a guarantee about *any* instant
is only tested by asking about instants of different kinds: immediately after a fold, part-way
through a decay, across a change of target, and long into the tail.

**The unstated-confidence fold at 15s was missing from the first version of this script**, and
the divergence test below is what found it: with every `OTHER` reading carrying a stated
confidence, `unstated_confidence` was never consulted, so varying it changed nothing and the
rebuild matched when it should not have. The omission was also the *unrealistic* case — §8.2
has the rule decoder leave `confidence` as `None` on every observation it makes, so this line is
the ordinary shape of iteration-1 evidence rather than an edge case added for coverage."""


def _t(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _evidence(target: Target, happiness: float, confidence: float | None,
              seconds: float) -> AffectEvidence:
    values = dict(EKMAN6.rest_vector().values)
    values["happiness"] = happiness
    return AffectEvidence(target=target,
                          affect=AffectVector(representation=EKMAN6.id, values=values),
                          confidence=confidence, at=_t(seconds), source="test:decoder")


def _model(half_life: float = HALF_LIFE, unstated: float = UNSTATED) -> AffectModel:
    """A model built from what a manifest would record. The two parameters are the ones the
    divergence tests vary, one at a time."""
    return AffectModel(representation=EKMAN6,
                       policies={Target.OTHER: ConfidenceWeighted(unstated_confidence=unstated,
                                                                  max_weight=1.0,
                                                                  refresh_above=0.5),
                                 Target.SELF: Assign(),
                                 Target.EXPRESSED: Assign(),
                                 },
                       half_lives={Target.OTHER: half_life, Target.SELF: half_life},
                       started_at=T0)


def _live_run() -> tuple[list[AffectState], list[AffectEvidence]]:
    """Run the script through the real evidence loop, returning the probes and what was
    published. The loop is what a session actually uses, so the evidence collected here is the
    evidence a recorder would have written."""
    async def scenario() -> tuple[list[AffectState], list[AffectEvidence]]:
        published: list[AffectEvidence] = []
        observers = Observers()

        def record(event: Event) -> None:
            if isinstance(event, AffectEvidence):
                published.append(event)

        observers.register(record)
        model = _model()
        loop = EvidenceLoop(model.observe, observers)
        task = asyncio.create_task(loop.run())

        probes: list[AffectState] = []
        for kind, seconds, target, happiness, confidence in SCRIPT:
            if kind == "fold":
                assert target is not None
                loop.submit(_evidence(target, happiness, confidence, seconds))
                await loop.drain()
            else:
                probes.append(model.state_at(_t(seconds)))

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return probes, published

    return asyncio.run(asyncio.wait_for(scenario(), timeout=TIMEOUT))


def _reconstruct(evidence: Sequence[AffectEvidence], probe_seconds: Sequence[float],
                 half_life: float = HALF_LIFE,
                 unstated: float = UNSTATED) -> list[AffectState]:
    """Rebuild a model from evidence alone and ask it the same questions.

    This *is* the reconstruction algorithm, and it is worth reading as one: sort the evidence
    by time, fold it in order, and answer each probe at the point in the sequence where it
    falls. Nothing else is consulted — no state rows, no live model, only the evidence and the
    parameters a manifest carries.

    Merged rather than replayed-then-queried, because §9.5 makes `state_at` answer *now or
    later* and never earlier: a rebuild that folded everything first could not then ask about
    an instant in the middle. That is not an awkwardness to work around — it is the same rule
    that stops a live model inventing its own past.
    """
    model = _model(half_life=half_life, unstated=unstated)
    pending = list(probe_seconds)
    probes: list[AffectState] = []

    for piece in sorted(evidence, key=lambda item: item.at):
        while pending and _t(pending[0]) <= piece.at:
            probes.append(model.state_at(_t(pending.pop(0))))
        model.observe(piece)

    probes.extend(model.state_at(_t(seconds)) for seconds in pending)
    return probes


PROBE_SECONDS = [seconds for kind, seconds, *_ in SCRIPT if kind == "probe"]


def test_a_run_is_reconstructable_from_the_evidence_it_published():
    """The guarantee itself: same evidence, same parameters, identical beliefs at every probe.

    Exact equality rather than approximate. The rebuild performs the same arithmetic in the
    same order, so anything less than exact would be hiding a difference rather than tolerating
    floating-point noise.
    """
    live, published = _live_run()

    rebuilt = _reconstruct(published, PROBE_SECONDS)

    assert rebuilt == live


def test_the_run_actually_moved_so_the_comparison_has_something_to_compare():
    """Guards the test above against passing vacuously.

    Four identical rest states would compare equal under any reconstruction at all, including a
    broken one — so the trajectory has to be shown to vary before equality means anything.
    """
    live, _ = _live_run()

    happiness = [state.other.values["happiness"] for state in live]

    assert len(set(happiness)) == len(happiness)        # every probe saw a different belief
    assert live[-1].expressed.values["happiness"] == 0.7
    assert live[-1].self_.values["happiness"] > 0.0


def test_reconstruction_diverges_under_a_different_half_life():
    """§15's own check that the test can fail. The decay constant is part of what must be
    recorded, so a manifest that omitted it would leave a rebuild silently wrong rather than
    obviously broken — 45 seconds and 30 give different trajectories from identical evidence."""
    live, published = _live_run()

    rebuilt = _reconstruct(published, PROBE_SECONDS, half_life=30.0)

    assert rebuilt != live


def test_reconstruction_diverges_under_a_different_unstated_confidence():
    """The same check for a fold-policy parameter, which §11 had no home for until v0.6.

    It is the sharper of the two: a wrong half-life is visible as a belief decaying at the
    wrong rate, whereas a wrong `unstated_confidence` only shows up on evidence that declined
    to state one — so it is exactly the parameter a manifest could omit unnoticed.
    """
    live, published = _live_run()

    rebuilt = _reconstruct(published, PROBE_SECONDS, unstated=0.1)

    assert rebuilt != live
