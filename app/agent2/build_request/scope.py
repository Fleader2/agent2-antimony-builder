"""Scoped-Build Support increment: restrict an assembled ``FullNetwork`` to one
``ModelBuildRequest``.

``apply_build_request_scope`` is this module's one public entry point. It never discovers,
infers, or curates any new biological fact -- it only subsets a ``FullNetwork`` that
``app.agent2.network.assemble_full_network`` already assembled in full, exactly the "assemble,
not reinterpret" discipline every other Agent 2 stage already follows
(``app.agent2.model_specification.assembler`` module docstring). A reference this module cannot
safely resolve is reported as a structured warning, never guessed -- the same disclosed-gap
policy ``app.agent2.network`` already uses for an Agent-1-handoff gap it cannot repair.

**Scoping policy, in order:**

1. ``REQUIRED``/``EXCLUDED`` reactions naming the same reaction id is a contradiction, rejected
   deterministically (``BuildRequestContradictionError``) before anything else runs.
2. If the request supplies no inclusion constraint at all (no seed/required reaction, no
   seed/start/end/boundary species, no seed/important gene-protein, no compartment-to-include),
   the network is returned unscoped except for ``EXCLUDED`` reactions, which are always honored.
3. Otherwise, the retained reaction set is exactly: every ``REQUIRED``/``SEED`` reaction, plus
   every reaction touching a seed/start/end/boundary species (by curated compound id) or a
   seed/important gene/protein (by curated protein/complex id), minus every ``EXCLUDED``
   reaction. A compartment-to-include constraint further restricts this set to reactions whose
   every participant species lies in an included compartment -- except a ``REQUIRED``/``SEED``
   reaction, which is never pruned by this step (Scope increment instructions: "include required
   entities even when they would otherwise be pruned").
4. Species, compartments, and enzyme associations are re-derived from the retained reaction set
   (plus any explicitly-referenced boundary/seed species, even when it ends up unused by any
   retained reaction). Every other "supporting data" tuple on ``FullNetwork``
   (``regulatory_interactions``/``kinetic_measurements``/``enzyme_states``/...) is left
   untouched -- it was never cross-validated against the structural graph even in the unscoped
   case (``FullNetwork``'s own module docstring: "supporting data... never used to infer
   structure").
5. A retained reaction set of zero is rejected (``BuildRequestEmptyScopeError``), never passed
   through to later stages that assume a non-empty network.

**Disclosed, not implemented:** pathway include/exclude scope, and subcellular localization
constraints on a gene/protein reference. Agent 2's ``FullNetwork`` carries no pathway-membership
field on any reaction (confirmed by inspection: neither ``CuratedReaction`` nor
``ReactionSpecification`` has one), so enforcing it would require either inventing a mapping
Agent 1 does not curate, or new pathway-discovery logic -- both explicitly out of scope for this
increment. Likewise, no curated entity anywhere in ``FullNetwork`` carries a subcellular
localization attribute to filter against. A non-empty ``pathways`` list, or any
``gene_proteins`` reference naming a ``localization_entity_id``/``localization_raw_identifier``,
always produces a disclosed warning instead of a silent no-op or a silently dropped field.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.agent2.build_request.errors import (
    BuildRequestContradictionError,
    BuildRequestEmptyScopeError,
)
from app.agent2.build_request.types import (
    BuildRequestGeneProteinRole,
    BuildRequestReactionRole,
    BuildRequestSpeciesRole,
    EntityReference,
    ModelBuildRequest,
)
from app.agent2.types import FullNetwork

_SPECIES_SCOPE_EXPANDING_ROLES = frozenset(
    {
        BuildRequestSpeciesRole.INPUT.value,
        BuildRequestSpeciesRole.OUTPUT.value,
        BuildRequestSpeciesRole.BOUNDARY.value,
        BuildRequestSpeciesRole.SEED.value,
    }
)


@dataclass(frozen=True, slots=True)
class ScopedNetworkResult:
    """The outcome of applying one ``ModelBuildRequest`` to one ``FullNetwork``."""

    network: FullNetwork
    warnings: tuple[str, ...]


def _resolved_ids_by_role(
    refs: tuple[EntityReference, ...], *, known_ids: set[str], warnings: list[str], label: str
) -> dict[str, set[str]]:
    """Group resolved ``agent1_entity_id`` values by role, warning on anything unresolved.

    A reference naming an ``agent1_entity_id`` absent from ``known_ids`` is reported as
    unresolved (it may legitimately belong to a different organism/network, or to an entity
    category this network does not carry at all) -- never silently dropped without a trace.
    A reference carrying only a ``raw_identifier`` (no ``agent1_entity_id`` at all) is always
    unresolved -- Agent 2 never guesses a biological mapping for raw user text.
    """
    by_role: dict[str, set[str]] = {}
    for ref in refs:
        if ref.agent1_entity_id is not None:
            if ref.agent1_entity_id in known_ids:
                by_role.setdefault(ref.role, set()).add(ref.agent1_entity_id)
            else:
                warnings.append(
                    f"UNRESOLVED_{label}_REFERENCE: role={ref.role} "
                    f"agent1_entity_id={ref.agent1_entity_id!r} does not match any {label.lower()} "
                    "in this network -- not used to scope the build."
                )
        elif ref.raw_identifier is not None:
            warnings.append(
                f"UNRESOLVED_RAW_IDENTIFIER: role={ref.role} {label.lower()} "
                f"raw_identifier={ref.raw_identifier!r} has no resolved agent1_entity_id -- "
                "Agent 2 never guesses a biological mapping from raw text; not used to scope "
                "the build. A later Agent 1 resolution pass may be able to resolve it."
            )
    return by_role


def apply_build_request_scope(
    network: FullNetwork, build_request: ModelBuildRequest
) -> ScopedNetworkResult:
    """Restrict ``network`` to ``build_request``'s own scope. See module docstring for policy.

    Raises ``BuildRequestContradictionError`` if the same reaction is named both ``REQUIRED``
    and ``EXCLUDED``. Never mutates ``network`` -- always returns a new ``FullNetwork``.
    """
    warnings: list[str] = []

    reaction_ids = {r.reaction_id for r in network.reactions}
    reactions_by_role = _resolved_ids_by_role(
        build_request.reactions, known_ids=reaction_ids, warnings=warnings, label="REACTION"
    )
    required_reaction_ids = reactions_by_role.get(BuildRequestReactionRole.REQUIRED.value, set())
    excluded_reaction_ids = reactions_by_role.get(BuildRequestReactionRole.EXCLUDED.value, set())
    seed_reaction_ids = reactions_by_role.get(BuildRequestReactionRole.SEED.value, set())

    contradiction = required_reaction_ids & excluded_reaction_ids
    if contradiction:
        raise BuildRequestContradictionError(
            "ModelBuildRequest names the same reaction as both REQUIRED and EXCLUDED: "
            f"{sorted(contradiction)}"
        )

    compound_ids = {s.source_compound_id for s in network.species if s.source_compound_id}
    species_by_role = _resolved_ids_by_role(
        build_request.species, known_ids=compound_ids, warnings=warnings, label="SPECIES"
    )
    scoping_compound_ids: set[str] = set()
    for role in _SPECIES_SCOPE_EXPANDING_ROLES:
        scoping_compound_ids |= species_by_role.get(role, set())

    protein_ids = set()
    for assoc in network.enzyme_associations:
        if assoc.protein_id:
            protein_ids.add(assoc.protein_id)
        if assoc.complex_id:
            protein_ids.add(assoc.complex_id)
    gene_protein_by_role = _resolved_ids_by_role(
        build_request.gene_proteins, known_ids=protein_ids, warnings=warnings, label="GENE_PROTEIN"
    )
    scoping_protein_ids: set[str] = set()
    for role in (
        BuildRequestGeneProteinRole.SEED.value,
        BuildRequestGeneProteinRole.IMPORTANT.value,
    ):
        scoping_protein_ids |= gene_protein_by_role.get(role, set())

    compartment_ids = {c.compartment_id for c in network.compartments}
    compartment_refs_resolved: set[str] = set()
    for ref in build_request.compartments:
        if ref.agent1_entity_id is not None:
            if ref.agent1_entity_id in compartment_ids:
                compartment_refs_resolved.add(ref.agent1_entity_id)
            else:
                warnings.append(
                    "UNRESOLVED_COMPARTMENT_REFERENCE: agent1_entity_id="
                    f"{ref.agent1_entity_id!r} does not match any compartment in this network."
                )
        elif ref.raw_identifier is not None:
            warnings.append(
                "UNRESOLVED_RAW_IDENTIFIER: compartment raw_identifier="
                f"{ref.raw_identifier!r} has no resolved agent1_entity_id -- not used to scope "
                "the build."
            )

    enzyme_state_ids = {e.id for e in network.enzyme_states}
    for ref in build_request.enzyme_states:
        if ref.agent1_entity_id is not None and ref.agent1_entity_id not in enzyme_state_ids:
            warnings.append(
                "UNRESOLVED_ENZYME_STATE_REFERENCE: agent1_entity_id="
                f"{ref.agent1_entity_id!r} does not match any curated enzyme state in this "
                "network."
            )

    regulatory_interaction_ids = {r.id for r in network.regulatory_interactions}
    for ref in build_request.regulatory_interactions:
        if (
            ref.agent1_entity_id is not None
            and ref.agent1_entity_id not in regulatory_interaction_ids
        ):
            warnings.append(
                "UNRESOLVED_REGULATORY_INTERACTION_REFERENCE: agent1_entity_id="
                f"{ref.agent1_entity_id!r} does not match any curated regulatory interaction in "
                "this network."
            )

    localization_constrained = [
        ref
        for ref in build_request.gene_proteins
        if ref.localization_entity_id is not None or ref.localization_raw_identifier is not None
    ]
    if localization_constrained:
        warnings.append(
            "UNSUPPORTED_LOCALIZATION_CONSTRAINT: this ModelBuildRequest named "
            f"{len(localization_constrained)} gene/protein reference(s) with a subcellular "
            "localization constraint, but Agent 2's scoping engine does not act on it -- "
            "localization scope is not enforced. Disclosed, not silently dropped; see "
            "app.agent2.build_request.scope's own module docstring."
        )

    if build_request.pathways:
        warnings.append(
            "UNSUPPORTED_PATHWAY_SCOPE: this ModelBuildRequest named "
            f"{len(build_request.pathways)} pathway include/exclude constraint(s), but Agent "
            "2's FullNetwork carries no pathway-membership field on any reaction -- pathway "
            "scope is not enforced. Disclosed, not silently ignored; see "
            "app.agent2.build_request.scope's own module docstring."
        )

    has_inclusion_constraint = bool(
        required_reaction_ids
        or seed_reaction_ids
        or scoping_compound_ids
        or scoping_protein_ids
        or compartment_refs_resolved
    )

    if not has_inclusion_constraint:
        allowed_reaction_ids = reaction_ids - excluded_reaction_ids
    else:
        species_by_id = {s.species_id: s for s in network.species}
        assoc_by_reaction: dict[str, list] = {}
        for assoc in network.enzyme_associations:
            assoc_by_reaction.setdefault(assoc.reaction_id, []).append(assoc)

        allowed_reaction_ids = set(required_reaction_ids) | set(seed_reaction_ids)
        for reaction in network.reactions:
            participant_compound_ids = {
                species_by_id[p.species_id].source_compound_id
                for p in reaction.participants
                if p.species_id in species_by_id
                and species_by_id[p.species_id].source_compound_id is not None
            }
            if participant_compound_ids & scoping_compound_ids:
                allowed_reaction_ids.add(reaction.reaction_id)
                continue
            reaction_assocs = assoc_by_reaction.get(reaction.reaction_id, ())
            assoc_ids = {a.protein_id for a in reaction_assocs if a.protein_id} | {
                a.complex_id for a in reaction_assocs if a.complex_id
            }
            if assoc_ids & scoping_protein_ids:
                allowed_reaction_ids.add(reaction.reaction_id)

        if compartment_refs_resolved:
            exempt = required_reaction_ids | seed_reaction_ids
            compartment_filtered: set[str] = set()
            for reaction_id in allowed_reaction_ids:
                if reaction_id in exempt:
                    compartment_filtered.add(reaction_id)
                    continue
                reaction = next(r for r in network.reactions if r.reaction_id == reaction_id)
                participant_compartment_ids = {
                    species_by_id[p.species_id].compartment_id
                    for p in reaction.participants
                    if p.species_id in species_by_id
                }
                if participant_compartment_ids and participant_compartment_ids <= (
                    compartment_refs_resolved
                ):
                    compartment_filtered.add(reaction_id)
            allowed_reaction_ids = compartment_filtered

        allowed_reaction_ids = (
            allowed_reaction_ids - excluded_reaction_ids
        ) | required_reaction_ids

    if not allowed_reaction_ids:
        raise BuildRequestEmptyScopeError(
            "ModelBuildRequest's own constraints resolved to zero retained reactions -- "
            "rejected rather than falling back to the unscoped network, guessing a scope, or "
            "proceeding with an empty network no later Agent 2 stage is designed for."
        )

    filtered_reactions = tuple(
        r for r in network.reactions if r.reaction_id in allowed_reaction_ids
    )
    retained_species_ids = {p.species_id for r in filtered_reactions for p in r.participants}
    for species in network.species:
        if species.source_compound_id in scoping_compound_ids:
            retained_species_ids.add(species.species_id)

    filtered_species = tuple(s for s in network.species if s.species_id in retained_species_ids)
    retained_compartment_ids = {
        s.compartment_id for s in filtered_species
    } | compartment_refs_resolved
    filtered_compartments = tuple(
        c for c in network.compartments if c.compartment_id in retained_compartment_ids
    )
    filtered_enzyme_associations = tuple(
        a for a in network.enzyme_associations if a.reaction_id in allowed_reaction_ids
    )

    scoped_network = replace(
        network,
        compartments=filtered_compartments,
        species=filtered_species,
        reactions=filtered_reactions,
        enzyme_associations=filtered_enzyme_associations,
    )
    return ScopedNetworkResult(network=scoped_network, warnings=tuple(warnings))


__all__ = ["ScopedNetworkResult", "apply_build_request_scope"]
