"""Pure mapping from a validated ``Agent1CuratedKnowledgeViewContract`` to structural objects.

Every function here assumes ``app.agent2.network.validation.validate_handoff``
already ran successfully against the same ``handoff`` -- none of these
functions re-validates referential integrity (that would duplicate
``validation.py``); they only map already-known-consistent curated records
onto ``app.agent2.types`` domain objects. Pure, deterministic, no I/O.

Agent 1's own ids are reused directly as Agent 2's internal
``compartment_id``/``reaction_id`` (Increment 2 instructions: "preserve
every Agent 1 identifier") -- ``source_entity_id``/``source_reaction_id``
record the identical value again, for explicit traceability, not because
the two ever differ. ``species_id`` cannot reuse a single Agent 1 id
(species identity is compound+compartment, not compound alone) and is
instead computed by ``app.agent2.network.types.build_species_id``.
"""

from __future__ import annotations

from collections import OrderedDict

from app.agent2.network.errors import UnknownParticipantRoleError
from app.agent2.network.types import SpeciesKey, build_enzyme_association_id, build_species_id
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedCompound,
    ParticipantRole,
    ReactionEnzymeAssociation,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

_ROLE_BY_VALUE = {role.value: role for role in ParticipantRole}


def build_compartments(
    handoff: Agent1CuratedKnowledgeViewContract,
) -> tuple[CompartmentSpecification, ...]:
    """One ``CompartmentSpecification`` per curated compartment, in handoff order.

    Never invented, merged, or renamed (Increment 2 instructions,
    "COMPARTMENTS") -- exactly one output row per input row.
    """
    return tuple(
        CompartmentSpecification(
            compartment_id=curated.id,
            name=curated.name,
            source_scope=CompartmentSourceScope.AGENT1_CURATED,
            source_entity_id=curated.id,
        )
        for curated in handoff.compartments
    )


def build_species(
    handoff: Agent1CuratedKnowledgeViewContract,
) -> tuple[SpeciesSpecification, ...]:
    """One ``SpeciesSpecification`` per distinct (compound, compartment) pair actually used.

    A compound referenced by participants in two different compartments
    becomes two species; the same (compound, compartment) pair referenced
    by many participants (or many reactions) becomes exactly one species,
    never duplicated (Increment 2 instructions, "SPECIES"). A compound
    never referenced by any participant gets no species at all (mirrors
    ``docs/04_core_domain_contracts.md`` §2: species are "derived from a
    curated compound's participation in at least one reaction").
    """
    compounds_by_id: dict[str, CuratedCompound] = {c.id: c for c in handoff.compounds}
    species_by_key: OrderedDict[SpeciesKey, SpeciesSpecification] = OrderedDict()

    for participant in handoff.reaction_participants:
        assert participant.compartment_id is not None  # validate_handoff already enforced this
        key = SpeciesKey(
            compound_id=participant.compound_id, compartment_id=participant.compartment_id
        )
        if key in species_by_key:
            continue
        compound = compounds_by_id[participant.compound_id]
        species_by_key[key] = SpeciesSpecification(
            species_id=build_species_id(key.compound_id, key.compartment_id),
            name=compound.name,
            compartment_id=key.compartment_id,
            source_compound_id=compound.id,
        )

    return tuple(species_by_key.values())


def _map_participant_role(role: str) -> ParticipantRole:
    """Map a curated participant's free-string role onto ``ParticipantRole``.

    ``validate_handoff`` already confirmed every participant's ``role`` is
    one of the known values before this function is ever called; this
    raises the identical error class defensively rather than assuming that
    invariant silently.
    """
    mapped = _ROLE_BY_VALUE.get(role)
    if mapped is None:
        raise UnknownParticipantRoleError(
            f"unrecognized reaction participant role {role!r}; expected one of "
            f"{sorted(_ROLE_BY_VALUE)}"
        )
    return mapped


def build_reaction_participants(
    handoff: Agent1CuratedKnowledgeViewContract, *, reaction_id: str
) -> tuple[ReactionParticipantSpecification, ...]:
    """Every participant of one curated reaction, in handoff order.

    Never deduplicated, never coefficient-normalized, never a fabricated
    cofactor -- ``stoichiometry`` is copied verbatim from the curated
    record (Increment 2 instructions, "REACTION PARTICIPANTS").
    """
    return tuple(
        ReactionParticipantSpecification(
            species_id=build_species_id(participant.compound_id, participant.compartment_id),
            role=_map_participant_role(participant.role),
            stoichiometry=participant.stoichiometry,
        )
        for participant in handoff.reaction_participants
        if participant.reaction_id == reaction_id
    )


def _group_by_reaction_id(reaction_id_getter, items) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(reaction_id_getter(item), []).append(item)
    return grouped


def build_enzyme_associations(
    handoff: Agent1CuratedKnowledgeViewContract,
) -> tuple[ReactionEnzymeAssociation, ...]:
    """One ``ReactionEnzymeAssociation`` per curated reaction-enzyme association.

    ``association_id`` is synthesized (the curated record has none, see
    ``app.agent2.types.ReactionEnzymeAssociation``); every other field is
    copied verbatim. No enzyme is chosen as preferred, no complex/isozyme
    relationship is inferred (Increment 2 instructions, "ENZYME
    ASSOCIATIONS").
    """
    grouped = _group_by_reaction_id(
        lambda a: a.reaction_id, handoff.reaction_enzyme_associations
    )
    associations: list[ReactionEnzymeAssociation] = []
    for reaction_id, group in grouped.items():
        for index, curated in enumerate(group):
            associations.append(
                ReactionEnzymeAssociation(
                    association_id=build_enzyme_association_id(reaction_id, index),
                    reaction_id=curated.reaction_id,
                    protein_id=curated.protein_id,
                    complex_id=curated.complex_id,
                    relationship=curated.relationship,
                )
            )
    return tuple(associations)


def build_enzyme_association_ids_by_reaction(
    enzyme_associations: tuple[ReactionEnzymeAssociation, ...],
) -> dict[str, tuple[str, ...]]:
    """Which ``ReactionEnzymeAssociation.association_id``\\ s belong to each reaction."""
    grouped = _group_by_reaction_id(lambda a: a.reaction_id, enzyme_associations)
    return {
        reaction_id: tuple(association.association_id for association in group)
        for reaction_id, group in grouped.items()
    }


def build_regulatory_interaction_ids_by_reaction(
    handoff: Agent1CuratedKnowledgeViewContract,
) -> dict[str, tuple[str, ...]]:
    """Which curated regulatory interaction ids involve each reaction, as regulator or target.

    A regulation record is attached to *every* reaction it names in either
    role whose type is ``"reaction"`` -- so a reaction that regulates
    another reaction is indexed under both, and nothing here decides which
    role is "the" relevant one (Increment 2 instructions, "REGULATION":
    carry regulation through exactly as received, never interpreted).
    """
    ids_by_reaction: dict[str, list[str]] = {}
    for regulation in handoff.regulatory_interactions:
        for entity_type, entity_id in (
            (regulation.target_type, regulation.target_id),
            (regulation.regulator_type, regulation.regulator_id),
        ):
            if entity_id is None:
                continue
            if entity_type and entity_type.strip().lower() == "reaction":
                ids_by_reaction.setdefault(entity_id, [])
                if regulation.id not in ids_by_reaction[entity_id]:
                    ids_by_reaction[entity_id].append(regulation.id)
    return {reaction_id: tuple(ids) for reaction_id, ids in ids_by_reaction.items()}


def build_reactions(
    handoff: Agent1CuratedKnowledgeViewContract,
    *,
    enzyme_association_ids_by_reaction: dict[str, tuple[str, ...]],
    regulatory_interaction_ids_by_reaction: dict[str, tuple[str, ...]],
) -> tuple[ReactionSpecification, ...]:
    """One ``ReactionSpecification`` per curated reaction, in handoff order.

    ``reversible`` is copied verbatim, including ``None`` -- never
    inferred (Increment 2 instructions, "REACTIONS"). ``kinetic_law_id``
    is always ``None``: kinetic-law assignment is out of this increment's
    scope entirely.
    """
    return tuple(
        ReactionSpecification(
            reaction_id=curated.id,
            name=curated.name,
            participants=build_reaction_participants(handoff, reaction_id=curated.id),
            source_reaction_id=curated.id,
            reversible=curated.reversible,
            enzyme_association_ids=enzyme_association_ids_by_reaction.get(curated.id, ()),
            regulatory_interaction_ids=regulatory_interaction_ids_by_reaction.get(
                curated.id, ()
            ),
        )
        for curated in handoff.reactions
    )


__all__ = [
    "build_compartments",
    "build_enzyme_association_ids_by_reaction",
    "build_enzyme_associations",
    "build_reaction_participants",
    "build_reactions",
    "build_regulatory_interaction_ids_by_reaction",
    "build_species",
]
