"""Pre-assembly validation of an ``Agent1CuratedKnowledgeViewContract`` (Increment 2).

Runs entirely against the raw handoff, before any
``app.agent2.types`` structural object is constructed -- so a violation is
reported in terms of Agent 1's own curated ids, not an Agent 2 internal id
a caller has never seen. ``FullNetwork``'s own ``__post_init__``
(``app.agent2.types._validate_full_network_references``) still runs too,
as defense in depth over the objects this package actually builds; nothing
here replaces it.

Every check is deterministic and pure: no database, no filesystem, no
network access. Raises on the first violation found, in the fixed order
below -- never collects and reports multiple violations at once (kept
simple; Increment 2 has no requirement for a multi-error report).
"""

from __future__ import annotations

from app.agent2.network.errors import (
    DanglingReferenceError,
    DuplicateCuratedIdentifierError,
    MissingCompartmentReferenceError,
    UnknownParticipantRoleError,
)
from app.agent2.types import Agent1CuratedKnowledgeViewContract, ParticipantRole

_KNOWN_PARTICIPANT_ROLES = frozenset(role.value for role in ParticipantRole)


def _require_unique_curated_ids(ids: list[str], *, category: str) -> set[str]:
    seen: set[str] = set()
    for entity_id in ids:
        if entity_id in seen:
            raise DuplicateCuratedIdentifierError(
                f"handoff contains two {category} records sharing id {entity_id!r}"
            )
        seen.add(entity_id)
    return seen


def validate_handoff(handoff: Agent1CuratedKnowledgeViewContract) -> None:
    """Run every pre-assembly validation check against ``handoff``. Raises on the first violation.

    Never mutates ``handoff`` -- read-only throughout.
    """
    compartment_ids = _require_unique_curated_ids(
        [c.id for c in handoff.compartments], category="compartment"
    )
    compound_ids = _require_unique_curated_ids(
        [c.id for c in handoff.compounds], category="compound"
    )
    reaction_ids = _require_unique_curated_ids(
        [r.id for r in handoff.reactions], category="reaction"
    )
    _require_unique_curated_ids(
        [r.id for r in handoff.regulatory_interactions], category="regulatory interaction"
    )
    _require_unique_curated_ids(
        [k.id for k in handoff.kinetic_measurements], category="kinetic measurement"
    )

    _validate_participants(
        handoff,
        reaction_ids=reaction_ids,
        compound_ids=compound_ids,
        compartment_ids=compartment_ids,
    )
    _validate_enzyme_associations(handoff, reaction_ids=reaction_ids)


def _validate_participants(
    handoff: Agent1CuratedKnowledgeViewContract,
    *,
    reaction_ids: set[str],
    compound_ids: set[str],
    compartment_ids: set[str],
) -> None:
    for participant in handoff.reaction_participants:
        if participant.reaction_id not in reaction_ids:
            raise DanglingReferenceError(
                f"reaction participant references undefined reaction "
                f"{participant.reaction_id!r}"
            )
        if participant.compound_id not in compound_ids:
            raise DanglingReferenceError(
                f"reaction participant (reaction {participant.reaction_id!r}) references "
                f"undefined compound {participant.compound_id!r}"
            )
        if participant.role not in _KNOWN_PARTICIPANT_ROLES:
            raise UnknownParticipantRoleError(
                f"reaction participant (reaction {participant.reaction_id!r}, compound "
                f"{participant.compound_id!r}) has unrecognized role {participant.role!r}; "
                f"expected one of {sorted(_KNOWN_PARTICIPANT_ROLES)}"
            )
        if participant.compartment_id is None:
            raise MissingCompartmentReferenceError(
                f"reaction participant (reaction {participant.reaction_id!r}, compound "
                f"{participant.compound_id!r}) has no compartment_id -- species identity "
                "requires compound and compartment together"
            )
        if participant.compartment_id not in compartment_ids:
            raise DanglingReferenceError(
                f"reaction participant (reaction {participant.reaction_id!r}, compound "
                f"{participant.compound_id!r}) references undefined compartment "
                f"{participant.compartment_id!r}"
            )


def _validate_enzyme_associations(
    handoff: Agent1CuratedKnowledgeViewContract, *, reaction_ids: set[str]
) -> None:
    for association in handoff.reaction_enzyme_associations:
        if association.reaction_id not in reaction_ids:
            raise DanglingReferenceError(
                f"reaction-enzyme association references undefined reaction "
                f"{association.reaction_id!r}"
            )


__all__ = ["validate_handoff"]
