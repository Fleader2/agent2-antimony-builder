"""Explicit Enzyme Concentration Representation increment.

``build_enzyme_concentration_species`` is this package's one public entry point: given a
``FullNetwork`` (already characterized and kinetic-law-assigned by the existing, unmodified
pipeline) and, optionally, the protein-level ``QuantitativeContextResolutionSet``
``app.agent2.quantitative_context.resolve_enzyme_concentrations`` already produced,
deterministically materializes one explicit catalytic-enzyme ``SpeciesSpecification`` per
distinct (``protein_id``, ``compartment_id``) catalytic context actually curated --
``source_protein_id`` set, never ``source_compound_id``/``source_enzyme_state_id``.

**Why explicit species, not a lumped effective rate constant**: before this increment, a
reaction's own catalytic enzyme abundance was never represented at all -- a Michaelis-Menten
law's own ``kcat`` (or, when reconstructed via ``DERIVED_FROM_MACRO_KINETICS``, ``Vmax /
[E]_total``) was multiplied only by substrate concentration, never by enzyme concentration,
so enzyme abundance and catalytic rate were structurally inseparable even when Agent 1's own
curated data (protein abundance, already resolved into a canonical-nM ``EnzymeConcentration``
by the Quantitative Context Resolution and Derived Enzyme Concentration increment) made the
decomposition possible. This package closes that gap: an explicit enzyme species lets
``app.agent2.model_specification.mapping.build_expression_and_species`` render
``kcat * E * S / (Km + S)`` instead of ``kcat * S / (Km + S)``, so enzyme abundance,
catalytic rate, and substrate affinity can vary independently (task's own explicit goal).

**Enzyme identity without a resolved compartment, or without a resolved concentration, is
still represented explicitly** -- this package never *requires* a resolved concentration to
create a species (task instructions, §5): an unresolved protein still gets an explicit
species, with ``initial_concentration=None`` and a disclosed ``assumptions`` entry, never a
fabricated numeric placeholder.

**Compartment is currently derived from the uniform compartment of the catalyzed reaction's
own participants -- a stand-in for the enzyme's own localization, not that localization
itself.** Agent 1 does not yet curate protein-level localization data for Agent 2 to read;
this is a known simplification, not the intended long-term rule, and the two happen to
coincide for an ordinary single-compartment metabolic reaction. They diverge for a
**transporter or membrane-associated enzyme**, whose own catalyst is localized to a specific
membrane/compartment distinct from, and not deducible from, its substrate's and product's own
compartments on either side. A reaction whose own participants span more than one compartment
(e.g. transport) has no single such stand-in compartment to place its catalyst in under
today's rule -- that one catalytic context is skipped (disclosed by omission, never guessed),
a real future localization problem this package does not solve, not a permanent exclusion.

**Never duplicates a species** (task instructions, §2): deduplicated by
(``protein_id``, ``compartment_id``) exactly like
``app.agent2.network.builder.build_species`` dedupes (``compound_id``, ``compartment_id``) --
the same enzyme catalyzing several reactions in the same compartment gets exactly one species,
reused by every one of those reactions' own kinetic-law expressions.

Pure and deterministic: no database, no filesystem, no network access, no simulation, no
fitting, no random numbers anywhere in its call graph. Mirrors
``app.agent2.enzyme_state_dynamics.build_enzyme_state_dynamics``'s own network-augmentation
contract: a caller passes this function's own ``.network`` (never the original) onward to
``app.agent2.parameters.declare_parameters``/
``app.agent2.model_specification.assemble_model_specification``/``generate_antimony``.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from app.agent2.enzyme_concentration_species.errors import (
    EnzymeConcentrationSpeciesReferenceError,
)
from app.agent2.network.types import build_enzyme_concentration_species_id
from app.agent2.quantitative_context.types import QuantitativeContextResolutionSet
from app.agent2.types import (
    EnzymeConcentrationBasis,
    FullNetwork,
    ParameterSource,
    ReactionSpecification,
    SpeciesSpecification,
)
from app.agent2.version import ENZYME_CONCENTRATION_SPECIES_POLICY_VERSION

#: Every tier ``app.agent2.quantitative_context.resolve_enzyme_concentrations`` can produce
#: traces back to a real, curated Agent 1 abundance/concentration observation -- only the
#: cell-volume side of a needed unit conversion is ever an explicit modeling assumption
#: (``REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME``). Every protein-level tier is therefore
#: ``LITERATURE_DERIVED`` in the same sense every other curated-observation-backed value in
#: this codebase already is -- never a value this package invented itself.
_BASIS_TO_INITIALIZATION_SOURCE: dict[EnzymeConcentrationBasis, ParameterSource] = (
    dict.fromkeys(
        (
            EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_CONCENTRATION,
            EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME,
            EnzymeConcentrationBasis.REFERENCE_CONCENTRATION,
            EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_COMPATIBLE_VOLUME,
            EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME,
        ),
        ParameterSource.LITERATURE_DERIVED,
    )
)

_UNRESOLVED_ENZYME_CONCENTRATION_ASSUMPTION = (
    "This enzyme's own identity (protein_id) is known and it is a curated catalyst of at "
    "least one reaction, but its concentration could not be resolved (no usable curated "
    "abundance/concentration observation, directly or via amount + cell volume) -- "
    "represented explicitly regardless, with no numeric initial value, rather than "
    "fabricating a biologically meaningful concentration."
)


@dataclasses.dataclass(frozen=True)
class EnzymeConcentrationSpeciesResult:
    """Everything ``build_enzyme_concentration_species`` produces for one ``FullNetwork``.

    ``network`` is the augmented network (original species/reactions preserved verbatim, one
    new species per resolvable catalytic context appended) -- pass this, never the original,
    onward. ``species_by_protein_and_compartment`` is the ``{(protein_id, compartment_id):
    species_id}`` lookup ``app.agent2.model_specification.mapping
    .build_expression_and_species`` uses to inject ``[E]`` into a Michaelis-Menten rate
    expression.
    """

    network: FullNetwork
    species_by_protein_and_compartment: dict[tuple[str, str], str] = dataclasses.field(
        default_factory=dict
    )


def _require_full_network(network: FullNetwork) -> FullNetwork:
    if not isinstance(network, FullNetwork):
        raise EnzymeConcentrationSpeciesReferenceError(
            f"build_enzyme_concentration_species requires a FullNetwork, got {network!r}"
        )
    return network


def _reaction_compartment_id(
    reaction: ReactionSpecification, species_by_id: dict[str, SpeciesSpecification]
) -> str | None:
    """The one compartment every one of ``reaction``'s own participants shares, or ``None``
    when the reaction spans more than one compartment (e.g. transport) -- never a guessed or
    preferred compartment for that ambiguous case. A participant names only its own
    ``species_id`` (``ReactionParticipantSpecification`` has no ``compartment_id`` of its
    own), so the compartment is resolved through ``species_by_id`` -- the same pattern
    ``app.agent2.boundaries.assessor._reaction_compartments``/
    ``app.agent2.modules.decomposer``/``app.agent2.build_request.scope`` already use. Mirrored,
    deliberately duplicated (never imported), in ``app.agent2.model_specification.mapping`` --
    see that module's own identical helper for why: a tiny, pure, single-purpose function, not
    worth a new cross-package dependency between two already-independent packages.
    """
    compartment_ids = {species_by_id[p.species_id].compartment_id for p in reaction.participants}
    if len(compartment_ids) != 1:
        return None
    (compartment_id,) = compartment_ids
    return compartment_id


def build_enzyme_concentration_species(
    network: FullNetwork,
    enzyme_concentrations: QuantitativeContextResolutionSet | None = None,
    *,
    policy_version: str = ENZYME_CONCENTRATION_SPECIES_POLICY_VERSION,
) -> EnzymeConcentrationSpeciesResult:
    """Deterministically build one explicit enzyme-concentration species per distinct,
    resolvable (``protein_id``, ``compartment_id``) catalytic context in ``network``.

    ``enzyme_concentrations`` (optional, defaults to ``None``) is the *same* protein-level
    ``QuantitativeContextResolutionSet`` ``app.agent2.quantitative_context
    .resolve_enzyme_concentrations`` already produced for this network -- supplies each
    species' own initial concentration. When omitted, or when a given protein's own outcome
    is unresolved, that species is still created (identity is known), just with
    ``initial_concentration=None`` and a disclosed ``assumptions`` entry.
    """
    _require_full_network(network)
    if enzyme_concentrations is not None and not isinstance(
        enzyme_concentrations, QuantitativeContextResolutionSet
    ):
        raise EnzymeConcentrationSpeciesReferenceError(
            "build_enzyme_concentration_species requires enzyme_concentrations to be a "
            f"QuantitativeContextResolutionSet or None, got {enzyme_concentrations!r}"
        )
    if (
        enzyme_concentrations is not None
        and enzyme_concentrations.network_id != network.network_id
    ):
        raise EnzymeConcentrationSpeciesReferenceError(
            f"enzyme_concentrations.network_id ({enzyme_concentrations.network_id!r}) does "
            f"not match network.network_id ({network.network_id!r})"
        )

    outcomes_by_protein = (
        {o.protein_id: o for o in enzyme_concentrations.outcomes}
        if enzyme_concentrations is not None
        else {}
    )
    proteins_by_id = {p.id: p for p in network.proteins}
    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    species_by_id = {s.species_id: s for s in network.species}

    # One (protein_id, compartment_id) pair per distinct catalytic context actually curated
    # -- deduplicated exactly like app.agent2.network.builder.build_species dedupes
    # (compound_id, compartment_id): the same enzyme catalyzing several reactions in the same
    # compartment gets exactly one species, never one per reaction (task instructions, "do
    # not duplicate enzyme species unnecessarily").
    pairs: set[tuple[str, str]] = set()
    for association in network.enzyme_associations:
        if association.protein_id is None:
            continue
        if association.protein_id not in proteins_by_id:
            # Agent 1 names this protein as a catalyst but Agent 2's handoff never exposed
            # the protein record itself -- a disclosed data gap, never a fabricated identity.
            continue
        reaction = reactions_by_id.get(association.reaction_id)
        if reaction is None:
            continue
        compartment_id = _reaction_compartment_id(reaction, species_by_id)
        if compartment_id is None:
            continue
        pairs.add((association.protein_id, compartment_id))

    new_species: list[SpeciesSpecification] = []
    lookup: dict[tuple[str, str], str] = {}
    for protein_id, compartment_id in sorted(pairs):
        protein = proteins_by_id[protein_id]
        species_id = build_enzyme_concentration_species_id(protein_id, compartment_id)
        outcome = outcomes_by_protein.get(protein_id)
        value: Decimal | None = None
        initialization_source: ParameterSource | None = None
        provenance_refs: tuple[str, ...] = (f"protein::{protein_id}",)
        if outcome is not None and outcome.concentration is not None:
            concentration = outcome.concentration
            value = concentration.value
            initialization_source = _BASIS_TO_INITIALIZATION_SOURCE.get(concentration.basis)
            assumptions: tuple[str, ...] = (
                f"Enzyme concentration resolved via {concentration.basis.value} "
                "(app.agent2.quantitative_context.resolve_enzyme_concentrations) -- see "
                "that record's own dependencies/notes for the exact curated observation(s) "
                "and any explicit cell-volume assumption this derivation relied on.",
            )
            provenance_refs = provenance_refs + tuple(
                f"quantitative-observation::{dep.observation_id}"
                for dep in concentration.dependencies
                if dep.observation_id is not None
            )
        else:
            assumptions = (_UNRESOLVED_ENZYME_CONCENTRATION_ASSUMPTION,)

        new_species.append(
            SpeciesSpecification(
                species_id=species_id,
                name=protein.name,
                compartment_id=compartment_id,
                source_protein_id=protein_id,
                initial_concentration=value,
                initialization_source=initialization_source,
                assumptions=assumptions,
                provenance_refs=provenance_refs,
            )
        )
        lookup[(protein_id, compartment_id)] = species_id

    augmented_network = dataclasses.replace(
        network,
        species=network.species + tuple(sorted(new_species, key=lambda s: s.species_id)),
    )
    return EnzymeConcentrationSpeciesResult(
        network=augmented_network, species_by_protein_and_compartment=lookup
    )


__all__ = ["EnzymeConcentrationSpeciesResult", "build_enzyme_concentration_species"]
