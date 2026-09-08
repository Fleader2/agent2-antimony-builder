"""Assembly-internal types (Increment 2).

Nothing here is a core domain contract -- those all live in
``app.agent2.types`` (``FullNetwork``, ``CompartmentSpecification``,
``SpeciesSpecification``, ``ReactionSpecification``,
``ReactionEnzymeAssociation``, ...), which this increment extends in
place rather than duplicating (Increment 2 instructions: "Do NOT redesign
any previously approved contracts"). ``SpeciesKey`` and the two
deterministic id-construction functions below exist only to give
``app.agent2.network.builder`` a single, pure, testable place to compute
an assembled id from curated source fields -- they are never part of the
public contract surface a downstream increment or repository consumes.
"""

from __future__ import annotations

from typing import NamedTuple


class SpeciesKey(NamedTuple):
    """Species identity: compound + compartment, never compound alone.

    ``glucose`` in the cytosol and ``glucose`` in the mitochondrion are two
    distinct keys and therefore two distinct
    ``app.agent2.types.SpeciesSpecification`` instances -- never collapsed
    (Increment 2 instructions, "SPECIES"). A plain, hashable
    ``NamedTuple`` so it can key a dict during assembly without any
    supporting machinery.
    """

    compound_id: str
    compartment_id: str


#: Separator used by ``build_species_id`` -- chosen to be visually
#: unambiguous in test failure messages and documentation; Agent 1 ids are
#: opaque strings (``docs/02_agent1_handoff_contract.md`` §5) with no
#: documented guarantee against containing this exact substring, but a
#: collision would only affect this assembly run's own internal id
#: uniqueness, not cross-run or cross-repository identity.
_SPECIES_ID_SEPARATOR = "::in::"

#: Separator used by ``build_enzyme_association_id``.
_ENZYME_ASSOCIATION_ID_SEPARATOR = "::enzyme::"


def build_species_id(compound_id: str, compartment_id: str) -> str:
    """Deterministic ``SpeciesSpecification.species_id`` for one ``SpeciesKey``.

    A pure function of its two inputs: calling this twice with the same
    arguments (in this run or a future one) always returns the identical
    id -- required for ``assemble_full_network`` to be a deterministic,
    pure function (Increment 2 instructions).
    """
    return f"{compound_id}{_SPECIES_ID_SEPARATOR}{compartment_id}"


def build_enzyme_association_id(reaction_id: str, index_within_reaction: int) -> str:
    """Deterministic ``ReactionEnzymeAssociation.association_id`` for one curated association.

    Scoped to one reaction (``index_within_reaction`` counts only that
    reaction's own curated associations, in the handoff's own order) --
    never a global index, so association ids stay stable even if unrelated
    associations for other reactions are added to or removed from the
    handoff. See ``app.agent2.types.ReactionEnzymeAssociation`` for why
    this increment synthesizes an id at all (the curated handoff record
    carries none).
    """
    return f"{reaction_id}{_ENZYME_ASSOCIATION_ID_SEPARATOR}{index_within_reaction}"


__all__ = [
    "SpeciesKey",
    "build_enzyme_association_id",
    "build_species_id",
]
