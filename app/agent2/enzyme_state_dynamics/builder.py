"""Enzyme-State Population Dynamics and Conservation (Multi-Context Catalytic Rate
Composition increment, Stage 2).

``build_enzyme_state_dynamics`` is this package's one public entry point: given a
``FullNetwork`` (already characterized and kinetic-law-assigned by the existing,
unmodified pipeline -- Stage 1's own network, untouched) and, optionally, the
protein-level ``QuantitativeContextResolutionSet`` Stage 1's own
``resolve_enzyme_concentrations`` already produced, deterministically:

1. Identifies every protein whose curated ``enzyme_states`` are actually
   **dynamically modeled** -- at least two curated states, connected by at least one
   curated ``CuratedEnzymeStateTransition`` whose two endpoints share that same
   parent protein. A protein with two or more curated states but **no** curated
   transition between any of them is left completely untouched (Stage 1's own
   "withhold the shared concentration" behavior for ambiguous sibling states
   continues to apply unchanged) -- this package never infers a transition merely
   because two states share a parent protein.
2. Materializes one dynamic ``SpeciesSpecification`` per such state (skipping any
   state with no resolvable ``compartment_id`` -- a disclosed data gap, never a
   fabricated compartment), and one ``ReactionSpecification`` + ``KineticLawAssignment``
   per curated transition between two such species -- always a first-order
   mass-action law (the simplest structurally supported transition law), never a
   guessed mechanism. Returns an augmented ``FullNetwork`` (original species/
   reactions preserved verbatim, new ones appended) -- ``network_id`` is never
   changed.
3. Resolves each modeled state's own initial concentration with two precedence
   tiers, never a third: a real, unambiguous, directly-curated state-specific
   concentration observation (``MEASURED_STATE_SPECIFIC_CONCENTRATION``), or --
   only when the parent's own total concentration is resolved and exactly one
   sibling state in the modeled group is otherwise unknown -- the deterministic
   remainder (``POOL_CONSERVATION_DERIVED``). Every other case is left explicitly
   unresolved (disclosed on the species' own ``assumptions``) -- never an invented
   fraction of the parent pool, never an even split.
4. Records one ``EnzymeStatePool`` per dynamically-modeled protein -- the disclosed
   conservation relationship itself (which states, which transitions).

**Never touches** ``app.agent2.characterization``/``app.agent2.kinetics.selector``/
``app.agent2.boundaries``/``app.agent2.modules`` -- those packages continue to run,
completely unmodified, against the *original*, pre-augmentation network (see this
package's own module-level usage note below and
``docs/18_enzyme_state_population_dynamics.md`` §2 for the full pipeline wiring). A
caller merges this function's own ``transition_assignments`` into the *original*
``KineticLawAssignmentSet`` (see ``merge_transition_assignments``) and passes the
*augmented* ``network`` only to ``app.agent2.parameters.declare_parameters`` and
``app.agent2.model_specification.assemble_model_specification`` onward.

Pure and deterministic: no database, no filesystem, no network access, no
simulation, no fitting, no random numbers anywhere in its call graph.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from decimal import Decimal

from app.agent2.enzyme_state_dynamics.errors import EnzymeStateDynamicsReferenceError
from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSet,
    KineticLawReasonCode,
)
from app.agent2.quantitative_context import policy as qc_policy
from app.agent2.quantitative_context.types import QuantitativeContextResolutionSet
from app.agent2.types import (
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedQuantitativeObservation,
    EnzymeConcentration,
    EnzymeConcentrationBasis,
    EnzymeConcentrationDependency,
    EnzymeStatePool,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawType,
    ParameterSource,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)
from app.agent2.version import ENZYME_STATE_DYNAMICS_POLICY_VERSION

_SPECIES_ID_PREFIX = "enzyme-state::"
_SPECIES_ID_SEPARATOR = "::in::"
_REACTION_ID_PREFIX = "enzyme-state-transition::"

_UNRESOLVED_INITIAL_STATE_ASSUMPTION = (
    "Initial abundance of this enzyme state is unresolved: no unambiguous "
    "state-specific concentration observation is available, and pool conservation "
    "could not uniquely determine it (the parent total concentration is itself "
    "unresolved, or more than one sibling state's own abundance is unknown). Never "
    "assigned an arbitrary fraction of the parent pool."
)


@dataclasses.dataclass(frozen=True)
class EnzymeStateDynamicsResult:
    """Everything ``build_enzyme_state_dynamics`` produces for one ``FullNetwork``.

    ``network`` is the augmented network (original species/reactions plus every
    dynamically-modeled enzyme-state species/transition reaction) -- pass this,
    never the original, to ``declare_parameters``/``assemble_model_specification``/
    ``generate_antimony``. ``pools``/``state_concentrations`` attach verbatim to
    ``ModelSpecification.enzyme_state_pools``/``.enzyme_state_concentrations``.
    ``transition_assignments`` must be merged into the *original* pipeline's own
    ``KineticLawAssignmentSet`` via ``merge_transition_assignments`` before
    ``declare_parameters`` is called against the augmented network.
    """

    network: FullNetwork
    pools: tuple[EnzymeStatePool, ...] = ()
    state_concentrations: tuple[EnzymeConcentration, ...] = ()
    transition_assignments: tuple[KineticLawAssignment, ...] = ()


def merge_transition_assignments(
    assignments: KineticLawAssignmentSet,
    transition_assignments: tuple[KineticLawAssignment, ...],
) -> KineticLawAssignmentSet:
    """Append ``transition_assignments`` (from ``EnzymeStateDynamicsResult``) to an
    already-decided ``KineticLawAssignmentSet`` -- never reinterprets or reorders the
    original assignments, and ``network_id``/policy-version fields are preserved
    verbatim (augmentation never changes a network's own id)."""
    if not isinstance(assignments, KineticLawAssignmentSet):
        raise EnzymeStateDynamicsReferenceError(
            f"merge_transition_assignments requires a KineticLawAssignmentSet, got {assignments!r}"
        )
    return dataclasses.replace(
        assignments,
        assignments=assignments.assignments
        + tuple(sorted(transition_assignments, key=lambda a: a.assignment_id)),
    )


def _require_full_network(network: FullNetwork) -> FullNetwork:
    if not isinstance(network, FullNetwork):
        raise EnzymeStateDynamicsReferenceError(
            f"build_enzyme_state_dynamics requires a FullNetwork, got {network!r}"
        )
    return network


def _protein_state_groups(network: FullNetwork) -> dict[str, tuple[CuratedEnzymeState, ...]]:
    """Every protein-based ``CuratedEnzymeState`` grouped by ``protein_id`` (complex-based
    states -- ``protein_id is None`` -- are never grouped or dynamically modeled here; this
    increment's scope is protein-based enzyme states only, disclosed as a limitation)."""
    groups: dict[str, list[CuratedEnzymeState]] = defaultdict(list)
    for state in network.enzyme_states:
        if state.protein_id is not None:
            groups[state.protein_id].append(state)
    return {pid: tuple(sorted(states, key=lambda s: s.id)) for pid, states in groups.items()}


def _transitions_by_protein(
    network: FullNetwork, groups: dict[str, tuple[CuratedEnzymeState, ...]]
) -> dict[str, tuple[CuratedEnzymeStateTransition, ...]]:
    """Every curated transition whose two endpoint states resolve to the identical parent
    protein, which itself has two or more curated states -- grouped by that protein_id. A
    transition whose endpoints resolve to two *different* proteins is a real data
    inconsistency (never a genuine modification-state transition) and is silently excluded
    here, never fabricated across proteins -- see ``docs/18_enzyme_state_population_
    dynamics.md`` §4."""
    state_protein_by_id = {s.id: s.protein_id for s in network.enzyme_states}
    result: dict[str, list[CuratedEnzymeStateTransition]] = defaultdict(list)
    for transition in network.enzyme_state_transitions:
        protein_from = state_protein_by_id.get(transition.from_state_id)
        protein_to = state_protein_by_id.get(transition.to_state_id)
        if protein_from is None or protein_to is None or protein_from != protein_to:
            continue
        if len(groups.get(protein_from, ())) < 2:
            continue
        result[protein_from].append(transition)
    return {pid: tuple(sorted(ts, key=lambda t: t.id)) for pid, ts in result.items()}


def _species_id_for_state(state: CuratedEnzymeState) -> str:
    return f"{_SPECIES_ID_PREFIX}{state.id}{_SPECIES_ID_SEPARATOR}{state.compartment_id}"


def _reaction_id_for_transition(transition: CuratedEnzymeStateTransition) -> str:
    return f"{_REACTION_ID_PREFIX}{transition.id}"


def _measured_state_observations(
    network: FullNetwork,
) -> dict[str, CuratedQuantitativeObservation]:
    """Tier A: a real, directly-curated ``PROTEIN_CONCENTRATION`` observation naming one
    enzyme state directly (``enzyme_state_id`` set -- currently never populated by any real
    Agent 1 handoff, see ``CuratedQuantitativeObservation.enzyme_state_id``'s own docstring,
    but a real, forward-compatible resolution path, not dead code). Two or more disagreeing
    observations for the same state leave that state unresolved at this tier -- never
    averaged, never arbitrarily chosen (mirrors ``app.agent2.quantitative_context.resolver``'s
    own identical disagreement policy)."""
    candidates_by_state: dict[str, list[CuratedQuantitativeObservation]] = defaultdict(list)
    for observation in network.quantitative_observations:
        if observation.enzyme_state_id is None:
            continue
        if qc_policy.usable_concentration_nm(observation) is None:
            continue
        candidates_by_state[observation.enzyme_state_id].append(observation)
    resolved: dict[str, CuratedQuantitativeObservation] = {}
    for state_id, candidates in candidates_by_state.items():
        values = {qc_policy.usable_concentration_nm(o) for o in candidates}
        if len(values) == 1:
            resolved[state_id] = sorted(candidates, key=lambda o: o.id)[0]
    return resolved


def build_enzyme_state_dynamics(
    network: FullNetwork,
    enzyme_concentrations: QuantitativeContextResolutionSet | None = None,
    *,
    policy_version: str = ENZYME_STATE_DYNAMICS_POLICY_VERSION,
) -> EnzymeStateDynamicsResult:
    """Deterministically build every dynamically-modeled enzyme-state pool for ``network``.

    ``enzyme_concentrations`` (optional, defaults to ``None``) is the *same*
    protein-level ``QuantitativeContextResolutionSet``
    ``app.agent2.quantitative_context.resolve_enzyme_concentrations`` already
    produced for this network -- supplies the parent-pool total each group's
    conservation-derived tier needs. When omitted, every group's conservation tier
    is simply never reached (no total to derive from), never a fabricated total.
    """
    _require_full_network(network)
    if enzyme_concentrations is not None and not isinstance(
        enzyme_concentrations, QuantitativeContextResolutionSet
    ):
        raise EnzymeStateDynamicsReferenceError(
            "build_enzyme_state_dynamics requires enzyme_concentrations to be a "
            f"QuantitativeContextResolutionSet or None, got {enzyme_concentrations!r}"
        )
    if (
        enzyme_concentrations is not None
        and enzyme_concentrations.network_id != network.network_id
    ):
        raise EnzymeStateDynamicsReferenceError(
            f"enzyme_concentrations.network_id ({enzyme_concentrations.network_id!r}) does "
            f"not match network.network_id ({network.network_id!r})"
        )

    parent_totals = (
        {ec.protein_id: ec for ec in enzyme_concentrations.enzyme_concentrations}
        if enzyme_concentrations is not None
        else {}
    )
    compartment_ids = {c.compartment_id for c in network.compartments}
    states_by_id = {s.id: s for s in network.enzyme_states}
    groups = _protein_state_groups(network)
    transitions_by_protein = _transitions_by_protein(network, groups)
    measured_observations_by_state = _measured_state_observations(network)

    new_species: list[SpeciesSpecification] = []
    new_reactions: list[ReactionSpecification] = []
    pools: list[EnzymeStatePool] = []
    state_concentrations: list[EnzymeConcentration] = []
    transition_assignments: list[KineticLawAssignment] = []

    for protein_id in sorted(transitions_by_protein):
        group_states = groups[protein_id]
        modeled_states = tuple(s for s in group_states if s.compartment_id in compartment_ids)
        if len(modeled_states) < 2:
            # A curated compartment gap knocked this protein's own modeled group below the
            # two-state minimum a conserved pool requires -- disclosed by simple omission
            # (never a fabricated compartment), no species/reactions/pool at all.
            continue
        modeled_state_ids = {s.id for s in modeled_states}
        modeled_transitions = tuple(
            t
            for t in transitions_by_protein[protein_id]
            if t.from_state_id in modeled_state_ids and t.to_state_id in modeled_state_ids
        )
        if not modeled_transitions:
            continue

        known_values: dict[str, Decimal] = {}
        known_basis: dict[str, EnzymeConcentrationBasis] = {}
        known_observation_by_state: dict[str, CuratedQuantitativeObservation] = {}
        for state in modeled_states:
            observation = measured_observations_by_state.get(state.id)
            if observation is not None:
                value = qc_policy.usable_concentration_nm(observation)
                assert value is not None
                known_values[state.id] = value
                known_basis[state.id] = (
                    EnzymeConcentrationBasis.MEASURED_STATE_SPECIFIC_CONCENTRATION
                )
                known_observation_by_state[state.id] = observation

        parent_total = parent_totals.get(protein_id)
        unknown_states = tuple(s for s in modeled_states if s.id not in known_values)
        if parent_total is not None and len(unknown_states) == 1:
            (only_unknown,) = unknown_states
            remainder = parent_total.value - sum(known_values.values(), Decimal(0))
            if remainder >= 0:
                known_values[only_unknown.id] = remainder
                known_basis[only_unknown.id] = EnzymeConcentrationBasis.POOL_CONSERVATION_DERIVED

        for state in modeled_states:
            species_id = _species_id_for_state(state)
            value = known_values.get(state.id)
            basis = known_basis.get(state.id)
            if basis is EnzymeConcentrationBasis.MEASURED_STATE_SPECIFIC_CONCENTRATION:
                observation = known_observation_by_state[state.id]
                dependencies = (
                    EnzymeConcentrationDependency(
                        role="concentration_input", observation_id=observation.id
                    ),
                )
                initialization_source = ParameterSource.LITERATURE_DERIVED
                species_assumptions: tuple[str, ...] = ()
                notes = (
                    f"Direct state-specific concentration from observation {observation.id!r} "
                    f"(evidence_class={observation.evidence_class})."
                )
            elif basis is EnzymeConcentrationBasis.POOL_CONSERVATION_DERIVED:
                sibling_ids = tuple(sorted(known_values.keys() - {state.id}))
                dependencies = (
                    EnzymeConcentrationDependency(
                        role="parent_total_input",
                        assumption_notes=(
                            f"Derived as protein {protein_id!r}'s resolved total concentration "
                            f"minus every other sibling state's own already-known value "
                            f"({', '.join(sibling_ids)}); never a fabricated split of an "
                            "unresolved total."
                        ),
                    ),
                )
                initialization_source = ParameterSource.DERIVED_FROM_POOL_CONSERVATION
                species_assumptions = ()
                notes = (
                    f"Pool-conservation-derived remainder: protein {protein_id!r}'s resolved "
                    f"total concentration minus sibling state(s) {', '.join(sibling_ids)}."
                )
            else:
                dependencies = ()
                initialization_source = None
                species_assumptions = (_UNRESOLVED_INITIAL_STATE_ASSUMPTION,)
                notes = None

            if value is not None:
                assert basis is not None
                state_concentrations.append(
                    EnzymeConcentration(
                        protein_id=protein_id,
                        enzyme_state_id=state.id,
                        value=value,
                        basis=basis,
                        policy_version=policy_version,
                        dependencies=dependencies,
                        notes=notes,
                    )
                )

            new_species.append(
                SpeciesSpecification(
                    species_id=species_id,
                    name=state.state_label or state.id,
                    compartment_id=state.compartment_id,
                    source_enzyme_state_id=state.id,
                    initial_concentration=value,
                    initialization_source=initialization_source,
                    assumptions=species_assumptions,
                    provenance_refs=(f"enzyme-state::{state.id}",),
                )
            )

        species_id_by_state_id = {s.id: _species_id_for_state(s) for s in modeled_states}
        for transition in modeled_transitions:
            reaction_id = _reaction_id_for_transition(transition)
            from_state = states_by_id[transition.from_state_id]
            to_state = states_by_id[transition.to_state_id]
            new_reactions.append(
                ReactionSpecification(
                    reaction_id=reaction_id,
                    name=(
                        f"{from_state.id} -> {to_state.id} ({transition.transition_type})"
                    ),
                    participants=(
                        ReactionParticipantSpecification(
                            species_id=species_id_by_state_id[from_state.id],
                            role=ParticipantRole.REACTANT,
                            stoichiometry=Decimal(1),
                        ),
                        ReactionParticipantSpecification(
                            species_id=species_id_by_state_id[to_state.id],
                            role=ParticipantRole.PRODUCT,
                            stoichiometry=Decimal(1),
                        ),
                    ),
                    reversible=False,
                    source_reaction_id=transition.reaction_id,
                    provenance_refs=(f"enzyme-state-transition::{transition.id}",),
                    assumptions=(
                        "First-order mass-action transition: the simplest structurally "
                        "supported law for this curated modification-state interconversion. "
                        "The true catalytic/enzymatic mechanism, if any, is not modeled.",
                    ),
                )
            )
            transition_assignments.append(
                KineticLawAssignment(
                    assignment_id=f"assignment::{reaction_id}",
                    reaction_id=reaction_id,
                    kinetic_law_type=KineticLawType.MASS_ACTION,
                    assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
                    policy_version=policy_version,
                    reason_codes=(
                        KineticLawReasonCode.ENZYME_STATE_TRANSITION_STRUCTURAL_MASS_ACTION,
                    ),
                    provenance_refs=(f"enzyme-state-transition::{transition.id}",),
                    explanation=(
                        f"Deterministic first-order mass-action transition "
                        f"{from_state.id} -> {to_state.id} ({transition.transition_type}), "
                        f"curated by Agent 1 as enzyme-state transition {transition.id!r}."
                    ),
                )
            )

        pools.append(
            EnzymeStatePool(
                protein_id=protein_id,
                state_ids=tuple(s.id for s in modeled_states),
                transition_ids=tuple(t.id for t in modeled_transitions),
                policy_version=policy_version,
                assumptions=(
                    f"Total enzyme conservation modeled for protein {protein_id!r} across "
                    f"states ({', '.join(s.id for s in modeled_states)}), interconverting only "
                    "through curated transition(s) "
                    f"({', '.join(t.id for t in modeled_transitions)})."
                    + (
                        " Parent total concentration is unresolved -- individual state initial "
                        "concentrations remain unresolved except where directly measured."
                        if parent_total is None
                        else ""
                    ),
                ),
                provenance_refs=tuple(f"enzyme-state::{s.id}" for s in modeled_states),
            )
        )

    augmented_network = dataclasses.replace(
        network,
        species=network.species
        + tuple(sorted(new_species, key=lambda s: s.species_id)),
        reactions=network.reactions
        + tuple(sorted(new_reactions, key=lambda r: r.reaction_id)),
    )

    return EnzymeStateDynamicsResult(
        network=augmented_network,
        pools=tuple(sorted(pools, key=lambda p: p.protein_id)),
        state_concentrations=tuple(
            sorted(state_concentrations, key=lambda ec: (ec.protein_id, ec.enzyme_state_id or ""))
        ),
        transition_assignments=tuple(
            sorted(transition_assignments, key=lambda a: a.assignment_id)
        ),
    )


__all__ = [
    "EnzymeStateDynamicsResult",
    "build_enzyme_state_dynamics",
    "merge_transition_assignments",
]
