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
    enzyme_state_ids = _require_unique_curated_ids(
        [s.id for s in handoff.enzyme_states], category="enzyme state"
    )
    _require_unique_curated_ids(
        [m.id for m in handoff.enzyme_modifications], category="enzyme modification"
    )
    _require_unique_curated_ids(
        [a.id for a in handoff.allosteric_interactions], category="allosteric interaction"
    )
    _require_unique_curated_ids(
        [t.id for t in handoff.enzyme_state_transitions], category="enzyme state transition"
    )

    _validate_participants(
        handoff,
        reaction_ids=reaction_ids,
        compound_ids=compound_ids,
        compartment_ids=compartment_ids,
    )
    _validate_enzyme_associations(
        handoff, reaction_ids=reaction_ids, enzyme_state_ids=enzyme_state_ids
    )
    _validate_enzyme_state_family(
        handoff, reaction_ids=reaction_ids, enzyme_state_ids=enzyme_state_ids
    )


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
    handoff: Agent1CuratedKnowledgeViewContract,
    *,
    reaction_ids: set[str],
    enzyme_state_ids: set[str],
) -> None:
    for association in handoff.reaction_enzyme_associations:
        if association.reaction_id not in reaction_ids:
            raise DanglingReferenceError(
                f"reaction-enzyme association references undefined reaction "
                f"{association.reaction_id!r}"
            )
        if (
            association.enzyme_state_id is not None
            and association.enzyme_state_id not in enzyme_state_ids
        ):
            raise DanglingReferenceError(
                f"reaction-enzyme association (reaction {association.reaction_id!r}) "
                f"references undefined enzyme state {association.enzyme_state_id!r}"
            )


def _validate_enzyme_state_family(
    handoff: Agent1CuratedKnowledgeViewContract,
    *,
    reaction_ids: set[str],
    enzyme_state_ids: set[str],
) -> None:
    """Increment 3: dangling-reference checks for the enzyme-state family.

    Mirrors ``app.agent2.types._validate_full_network_references``'s
    identical checks -- run here too, against the raw handoff, so a
    violation is reported in terms of Agent 1's own curated ids before any
    ``app.agent2.types`` object is constructed (see module docstring).
    """
    for modification in handoff.enzyme_modifications:
        if modification.enzyme_state_id not in enzyme_state_ids:
            raise DanglingReferenceError(
                f"enzyme modification {modification.id!r} references undefined enzyme "
                f"state {modification.enzyme_state_id!r}"
            )

    for interaction in handoff.allosteric_interactions:
        if interaction.enzyme_state_id not in enzyme_state_ids:
            raise DanglingReferenceError(
                f"allosteric interaction {interaction.id!r} references undefined enzyme "
                f"state {interaction.enzyme_state_id!r}"
            )

    for transition in handoff.enzyme_state_transitions:
        if transition.from_state_id not in enzyme_state_ids:
            raise DanglingReferenceError(
                f"enzyme state transition {transition.id!r} references undefined "
                f"from_state_id {transition.from_state_id!r}"
            )
        if transition.to_state_id not in enzyme_state_ids:
            raise DanglingReferenceError(
                f"enzyme state transition {transition.id!r} references undefined "
                f"to_state_id {transition.to_state_id!r}"
            )
        if transition.reaction_id is not None and transition.reaction_id not in reaction_ids:
            raise DanglingReferenceError(
                f"enzyme state transition {transition.id!r} references undefined reaction "
                f"{transition.reaction_id!r}"
            )

    for measurement in handoff.kinetic_measurements:
        if (
            measurement.enzyme_state_id is not None
            and measurement.enzyme_state_id not in enzyme_state_ids
        ):
            raise DanglingReferenceError(
                f"kinetic measurement {measurement.id!r} references undefined enzyme state "
                f"{measurement.enzyme_state_id!r}"
            )


__all__ = ["validate_handoff"]
