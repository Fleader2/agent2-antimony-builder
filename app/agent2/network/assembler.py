"""Whole-Network Assembly (Increment 2): the first executable stage of Agent 2.

``assemble_full_network`` is the package's one public entry point. It is a
deterministic, pure function: no database, no filesystem, no network
access, no connector, no simulation, and no randomness or wall-clock time
anywhere in its call graph. Calling it twice with the identical (or an
equal-by-value) ``Agent1CuratedKnowledgeViewContract`` always returns an
equal ``FullNetwork``.

Produces exactly one type: ``app.agent2.types.FullNetwork``. Never a
``ModelSpecification``, ``BoundaryAssessment``, ``ModuleSpecification``,
Antimony, SBML, a simulation result, or a validation report -- see
``docs/05_whole_network_assembly.md`` and Increment 2's own scope
exclusions.
"""

from __future__ import annotations

from app.agent2.network import builder
from app.agent2.network.validation import validate_handoff
from app.agent2.types import Agent1CuratedKnowledgeViewContract, FullNetwork

_UNSCOPED_NETWORK_ID = "network::unscoped"
_UNSCOPED_NETWORK_NAME = "Full network (unscoped)"


def _network_id_for(handoff: Agent1CuratedKnowledgeViewContract) -> str:
    """Deterministic ``FullNetwork.network_id`` -- a pure function of ``handoff.organism_id``.

    Never a random or time-based id (``assemble_full_network`` must be
    deterministic). A whole-database (unscoped) handoff always yields the
    identical network id, which is intentional: assembling the same
    unscoped handoff twice must produce equal ``FullNetwork`` instances.
    """
    if handoff.organism_id is None:
        return _UNSCOPED_NETWORK_ID
    return f"network::{handoff.organism_id}"


def _network_name_for(handoff: Agent1CuratedKnowledgeViewContract) -> str:
    if handoff.organism_id is None:
        return _UNSCOPED_NETWORK_NAME
    return f"Full network for organism {handoff.organism_id}"


def assemble_full_network(handoff: Agent1CuratedKnowledgeViewContract) -> FullNetwork:
    """Assemble a complete, internally consistent ``FullNetwork`` from an Agent 1 handoff.

    Raises an ``app.agent2.network.errors.NetworkAssemblyError`` subclass
    for a violation this package's own pre-assembly validation catches, or
    a plain ``ValueError`` raised by an ``app.agent2.types`` contract's own
    ``__post_init__`` for a violation only visible once construction is
    attempted -- for example, a curated reaction with zero participants
    fails ``ReactionSpecification``'s own "at least one participant" rule.
    Either way, this function never silently repairs, drops, or
    reinterprets inconsistent data (Increment 2 instructions,
    "VALIDATION").

    Never assigns a kinetic law, never declares or initializes a
    parameter, never assesses a module boundary, never generates Antimony
    or SBML, and never infers a cofactor, transport step, enzyme complex,
    isozyme, missing reaction, or regulation -- those all remain later
    increments' responsibility.
    """
    if not isinstance(handoff, Agent1CuratedKnowledgeViewContract):
        raise TypeError(
            "assemble_full_network requires an Agent1CuratedKnowledgeViewContract, "
            f"got {handoff!r}"
        )

    validate_handoff(handoff)

    compartments = builder.build_compartments(handoff)
    species = builder.build_species(handoff)
    enzyme_associations = builder.build_enzyme_associations(handoff)
    enzyme_association_ids_by_reaction = builder.build_enzyme_association_ids_by_reaction(
        enzyme_associations
    )
    regulatory_interaction_ids_by_reaction = builder.build_regulatory_interaction_ids_by_reaction(
        handoff
    )
    reactions = builder.build_reactions(
        handoff,
        enzyme_association_ids_by_reaction=enzyme_association_ids_by_reaction,
        regulatory_interaction_ids_by_reaction=regulatory_interaction_ids_by_reaction,
    )

    return FullNetwork(
        network_id=_network_id_for(handoff),
        name=_network_name_for(handoff),
        compartments=compartments,
        species=species,
        reactions=reactions,
        enzyme_associations=enzyme_associations,
        regulatory_interactions=handoff.regulatory_interactions,
        kinetic_measurements=handoff.kinetic_measurements,
        enzyme_states=handoff.enzyme_states,
        enzyme_modifications=handoff.enzyme_modifications,
        allosteric_interactions=handoff.allosteric_interactions,
        enzyme_state_transitions=handoff.enzyme_state_transitions,
        experimental_contexts=handoff.experimental_contexts,
        quantitative_observations=handoff.quantitative_observations,
        publications=handoff.publications,
        organism_id=handoff.organism_id,
    )


__all__ = ["assemble_full_network"]
