#
# Affect model — decay
#
# How a belief ages in the absence of evidence


"""Per-axis exponential decay, toward the representation's ``rest`` rather than zero.

A strategy module beside ``belief.py`` (§14.1's ordinary rule — this one has real
alternatives, unlike the model itself). ``belief.py`` calls this when it needs an aged
value; nothing here knows about targets, evidence or folding, and nothing here runs on a
schedule — see ``§9.5``'s *time is a parameter, never a clock read*.

**Whole-vector, not scalar, and the representation is passed rather than a bare ``rest``
float.** Three reasons, found by writing the scalar version first and seeing what it let a
caller do:

1. A scalar signature puts the loop over axes in every caller, which is exactly where the
   deep-immutability rule (§4, ``AffectHistory``) gets broken — a caller can update
   ``vector.values[axis]`` in place, and ``frozen=True`` does not stop it, because it
   protects the binding and not the dict's contents. Returning a whole new ``AffectVector``
   makes that mistake structurally unavailable rather than merely discouraged.
2. Passing the representation rather than its ``rest`` lets this function catch a vector
   aged against the wrong one — a ``ValueError`` naming both ids, rather than a silent wrong
   number. This is decision 4's rule (validate at the seams) applied at one more seam.
3. It is where decision 8's per-axis ``rest`` question would land if ``AffectRepresentation``
   ever grows one: the signature would not change, only what ``rep.rest`` means.

**Two guards beyond the type checker, because floats do not stop a caller from swapping
them.** ``elapsed_s`` and ``half_life_s`` are both bare numbers, and a checker cannot tell
one from the other — verified while writing this: swapping them with ``rest=0.0`` raises
``ZeroDivisionError``, which is at least loud, but with any other ``rest`` it returns a
silently wrong number instead. So both are keyword-only, and a negative ``elapsed_s`` — which
is not hypothetical, since evidence can arrive out of order and ``computed_from`` exists for
exactly that — raises rather than ageing a belief *backwards* past its own starting value.
"""

from asa.core.affect import AffectVector
from asa.core.representations import AffectRepresentation


def decayed(vector: AffectVector, *, elapsed_s: float,
           rep: AffectRepresentation, half_life_s: float) -> AffectVector:
    """*vector*, aged by *elapsed_s* toward ``rep.rest``, one exponential per axis.

    Returns a **new** ``AffectVector``; *vector* is untouched. Composes exactly — ageing by
    30s in one call equals ageing by 7s then 3s then 20s — because each axis only ever
    depends on its own last value and the elapsed time since it, never on how that time was
    divided. This is what lets §9.5's reconstruction replay evidence in whatever chunks a
    conversation happened to produce.

    Raises if *vector* does not name *rep* (§4's validate-at-the-seams rule), if
    ``elapsed_s`` is negative (ageing backwards would push a value past where it started,
    outside the representation's declared range), or if ``half_life_s`` is not positive (a
    zero or negative half-life is not a decay).
    """
    if vector.representation != rep.id:
        raise ValueError(
            f"vector names {vector.representation!r}, but decay was asked against "
            f"{rep.id!r}'s rest"
        )
    if elapsed_s < 0:
        raise ValueError(f"elapsed_s must not be negative, got {elapsed_s}")
    if half_life_s <= 0:
        raise ValueError(f"half_life_s must be positive, got {half_life_s}")

    factor = 0.5 ** (elapsed_s / half_life_s)
    return AffectVector(
        representation=vector.representation,
        values={axis: rep.rest + (magnitude - rep.rest) * factor
               for axis, magnitude in vector.values.items()},
    )
