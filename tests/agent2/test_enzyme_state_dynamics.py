"""Tests for Enzyme-State Population Dynamics and Conservation (Multi-Context Catalytic
Rate Composition increment, Stage 2): ``app.agent2.enzyme_state_dynamics``.

Most tests build a ``FullNetwork`` directly (mirroring ``tests/agent2/
test_antimony_generation.py``'s own convention) so each pool/species/transition scenario
can be pinned exactly. The final test runs the real, full upstream pipeline (mirroring
``tests/agent2/test_model_specification.py``) to confirm genuine end-to-end behavior --
the "synthetic phosphorylation regression" the increment's own instructions require.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent2.antimony import generate_antimony
from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.enzyme_state_dynamics import (
    EnzymeStateDynamicsReferenceError,
    build_enzyme_state_dynamics,
    merge_transition_assignments,
)
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.kinetics.types import KineticLawAssignmentSet, KineticLawReasonCode
from app.agent2.model_specification import assemble_model_specification
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.quantitative_context import resolve_enzyme_concentrations
from app.agent2.quantitative_context.types import (
    QuantitativeContextResolutionOutcome,
    QuantitativeContextResolutionSet,
)
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    AntimonyArtifactReadiness,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
    CuratedQuantitativeObservation,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    EnzymeConcentration,
    EnzymeConcentrationBasis,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawType,
    ParameterSource,
)

# --- FullNetwork-direct fixtures (builder-level tests) -----------------------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "cyto",
        "name": "cytosol",
        "source_scope": CompartmentSourceScope.AGENT1_CURATED,
        "source_entity_id": "agent1-c1",
    } | overrides
    return CompartmentSpecification(**merged)


def _state(**overrides) -> CuratedEnzymeState:
    merged = {
        "id": "E",
        "state_type": "unmodified",
        "protein_id": "p1",
        "compartment_id": "cyto",
    } | overrides
    return CuratedEnzymeState(**merged)


def _transition(**overrides) -> CuratedEnzymeStateTransition:
    merged = {
        "id": "t1",
        "from_state_id": "E",
        "to_state_id": "E_P",
        "transition_type": "phosphorylation",
    } | overrides
    return CuratedEnzymeStateTransition(**merged)


def _network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "test network",
        "compartments": (_compartment(),),
        "enzyme_states": (_state(id="E"), _state(id="E_P")),
        "enzyme_state_transitions": (_transition(),),
    } | overrides
    return FullNetwork(**merged)


def _concentration_set(**outcomes_kwargs) -> QuantitativeContextResolutionSet:
    """One protein's own resolved total, as a minimal ``QuantitativeContextResolutionSet`` --
    never routed through the real observation-resolution machinery (that machinery is
    already covered by ``tests/agent2/test_quantitative_context.py``; here only the
    *consumption* of an already-resolved total matters)."""
    protein_id = outcomes_kwargs.pop("protein_id", "p1")
    value = outcomes_kwargs.pop("value", Decimal("100"))
    concentration = EnzymeConcentration(
        protein_id=protein_id,
        value=value,
        basis=EnzymeConcentrationBasis.REFERENCE_CONCENTRATION,
        policy_version="test-policy",
    )
    outcome = QuantitativeContextResolutionOutcome(
        protein_id=protein_id, concentration=concentration
    )
    return QuantitativeContextResolutionSet(
        network_id=outcomes_kwargs.pop("network_id", "n1"),
        policy_version="test-policy",
        outcomes=(outcome,),
    )


def _observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-state-1",
        "observation_type": "PROTEIN_CONCENTRATION",
        "value": Decimal("30"),
        "unit": "nM",
        "evidence_class": "REFERENCE_BASELINE",
        "enzyme_state_id": "E",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


# --- Pool/species/reaction formation -------------------------------------------------------


def _is_transition_reaction(reaction) -> bool:
    return reaction.reaction_id.startswith("enzyme-state-transition::")


def test_two_states_with_a_transition_form_one_pool_with_two_species():
    result = build_enzyme_state_dynamics(_network())
    assert len(result.pools) == 1
    pool = result.pools[0]
    assert pool.protein_id == "p1"
    assert pool.state_ids == ("E", "E_P")
    assert pool.transition_ids == ("t1",)
    new_species = [s for s in result.network.species if s.source_enzyme_state_id is not None]
    assert {s.source_enzyme_state_id for s in new_species} == {"E", "E_P"}
    new_reactions = [r for r in result.network.reactions if _is_transition_reaction(r)]
    assert len(new_reactions) == 1


def test_two_states_with_no_transition_produce_no_species_pool_or_reactions():
    """Preserves existing Stage 1 behavior unchanged: two curated states sharing a parent
    protein, with no curated transition connecting them, are never dynamically modeled."""
    network = _network(enzyme_state_transitions=())
    result = build_enzyme_state_dynamics(network)
    assert result.pools == ()
    assert result.state_concentrations == ()
    assert result.transition_assignments == ()
    assert result.network.species == ()
    assert result.network.reactions == ()


def test_state_missing_compartment_excludes_whole_protein_from_pooling():
    network = _network(
        enzyme_states=(_state(id="E", compartment_id="unknown-compartment"), _state(id="E_P"))
    )
    result = build_enzyme_state_dynamics(network)
    # Only one of the two states has a resolvable compartment -- below the two-state
    # minimum a conserved pool requires, so nothing is modeled for this protein at all.
    assert result.pools == ()
    assert result.network.species == ()
    assert result.network.reactions == ()


def test_transition_across_two_different_proteins_is_skipped():
    """A transition whose two endpoints resolve to different parent proteins is a real
    data inconsistency -- never a genuine modification-state transition -- and must never
    be fabricated into a cross-protein pool."""
    network = _network(
        enzyme_states=(
            _state(id="E", protein_id="p1"),
            _state(id="E_P", protein_id="p2"),
        )
    )
    result = build_enzyme_state_dynamics(network)
    assert result.pools == ()
    assert result.network.species == ()
    assert result.network.reactions == ()


def test_distinct_parent_proteins_produce_distinct_separate_pools():
    network = _network(
        enzyme_states=(
            _state(id="E", protein_id="p1"),
            _state(id="E_P", protein_id="p1"),
            _state(id="F", protein_id="p2"),
            _state(id="F_P", protein_id="p2"),
        ),
        enzyme_state_transitions=(
            _transition(id="t1", from_state_id="E", to_state_id="E_P"),
            _transition(id="t2", from_state_id="F", to_state_id="F_P"),
        ),
    )
    result = build_enzyme_state_dynamics(network)
    assert {p.protein_id for p in result.pools} == {"p1", "p2"}
    pool_by_protein = {p.protein_id: p for p in result.pools}
    assert pool_by_protein["p1"].state_ids == ("E", "E_P")
    assert pool_by_protein["p2"].state_ids == ("F", "F_P")


def test_one_way_transition_produces_exactly_one_reaction():
    result = build_enzyme_state_dynamics(_network())
    transition_reactions = [r for r in result.network.reactions if _is_transition_reaction(r)]
    assert len(transition_reactions) == 1
    (reaction,) = transition_reactions
    assert reaction.reversible is False
    roles = {
        p.species_id.split("::")[1].split("::in::")[0]: p.role.value
        for p in reaction.participants
    }
    assert roles == {"E": "REACTANT", "E_P": "PRODUCT"}


def test_two_opposite_one_way_transitions_produce_two_reactions():
    """A curated reversible interconversion is represented as two separate one-way
    reactions (E -> E_P, E_P -> E), each first-order mass action -- never a single
    ``reversible=True`` reaction, and never a fabricated symmetry."""
    network = _network(
        enzyme_state_transitions=(
            _transition(
                id="t1", from_state_id="E", to_state_id="E_P", transition_type="phosphorylation"
            ),
            _transition(
                id="t2", from_state_id="E_P", to_state_id="E", transition_type="dephosphorylation"
            ),
        )
    )
    result = build_enzyme_state_dynamics(network)
    transition_reactions = sorted(
        (r for r in result.network.reactions if _is_transition_reaction(r)),
        key=lambda r: r.reaction_id,
    )
    assert len(transition_reactions) == 2
    assert all(r.reversible is False for r in transition_reactions)
    (pool,) = result.pools
    assert pool.transition_ids == ("t1", "t2")


def test_transition_assignment_is_deterministic_structural_mass_action():
    result = build_enzyme_state_dynamics(_network())
    (assignment,) = result.transition_assignments
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL
    assert (
        KineticLawReasonCode.ENZYME_STATE_TRANSITION_STRUCTURAL_MASS_ACTION
        in assignment.reason_codes
    )
    assert assignment.enzyme_state_id is None
    assert assignment.protein_id is None
    assert assignment.complex_id is None
    assert assignment.unresolved_reasons == ()


# --- State-level concentration resolution --------------------------------------------------


def test_parent_concentration_not_duplicated_across_states_when_neither_is_measured():
    result = build_enzyme_state_dynamics(_network(), _concentration_set(value=Decimal("100")))
    # Two unknown siblings -- conservation cannot uniquely determine either one, so
    # neither is assigned the full (or any) parent concentration.
    assert result.state_concentrations == ()
    for species in result.network.species:
        if species.source_enzyme_state_id is not None:
            assert species.initial_concentration is None
            assert species.initialization_source is None


def test_measured_state_specific_concentration_takes_precedence():
    network = _network(quantitative_observations=(_observation(value=Decimal("42")),))
    result = build_enzyme_state_dynamics(network, _concentration_set(value=Decimal("100")))
    e_concentration = next(ec for ec in result.state_concentrations if ec.enzyme_state_id == "E")
    assert e_concentration.value == Decimal("42")
    assert (
        e_concentration.basis is EnzymeConcentrationBasis.MEASURED_STATE_SPECIFIC_CONCENTRATION
    )
    e_species = next(s for s in result.network.species if s.source_enzyme_state_id == "E")
    assert e_species.initial_concentration == Decimal("42")
    assert e_species.initialization_source is ParameterSource.LITERATURE_DERIVED


def test_conservation_derived_remainder_for_the_one_unknown_sibling():
    network = _network(quantitative_observations=(_observation(value=Decimal("30")),))
    result = build_enzyme_state_dynamics(network, _concentration_set(value=Decimal("100")))
    ep_concentration = next(ec for ec in result.state_concentrations if ec.enzyme_state_id == "E_P")
    assert ep_concentration.value == Decimal("70")
    assert ep_concentration.basis is EnzymeConcentrationBasis.POOL_CONSERVATION_DERIVED
    ep_species = next(s for s in result.network.species if s.source_enzyme_state_id == "E_P")
    assert ep_species.initial_concentration == Decimal("70")
    assert ep_species.initialization_source is ParameterSource.DERIVED_FROM_POOL_CONSERVATION
    assert ep_species.assumptions == ()


def test_conservation_not_applied_when_parent_total_unresolved():
    network = _network(quantitative_observations=(_observation(value=Decimal("30")),))
    result = build_enzyme_state_dynamics(network, enzyme_concentrations=None)
    assert not any(ec.enzyme_state_id == "E_P" for ec in result.state_concentrations)
    ep_species = next(s for s in result.network.species if s.source_enzyme_state_id == "E_P")
    assert ep_species.initial_concentration is None
    assert "unresolved" in ep_species.assumptions[0].lower()


def test_negative_remainder_is_never_fabricated_into_a_concentration():
    """A measured state value exceeding the parent's own resolved total is a real data
    inconsistency -- the arithmetic remainder would be negative, so the sibling stays
    unresolved rather than emitting an impossible negative concentration."""
    network = _network(quantitative_observations=(_observation(value=Decimal("150")),))
    result = build_enzyme_state_dynamics(network, _concentration_set(value=Decimal("100")))
    assert not any(ec.enzyme_state_id == "E_P" for ec in result.state_concentrations)


def test_two_or_more_unknown_states_never_split_the_parent_total():
    network = _network(
        enzyme_states=(_state(id="E"), _state(id="E_P"), _state(id="E_Ac")),
        enzyme_state_transitions=(
            _transition(id="t1", from_state_id="E", to_state_id="E_P"),
            _transition(id="t2", from_state_id="E", to_state_id="E_Ac"),
        ),
    )
    result = build_enzyme_state_dynamics(network, _concentration_set(value=Decimal("100")))
    # All three states are unknown (no measurement for any) -- conservation requires
    # exactly one unknown sibling, never a three-way (or any multi-way) split.
    assert result.state_concentrations == ()


# --- Reference/type errors and determinism -------------------------------------------------


def test_build_enzyme_state_dynamics_rejects_non_full_network():
    with pytest.raises(EnzymeStateDynamicsReferenceError):
        build_enzyme_state_dynamics("not a network")  # type: ignore[arg-type]


def test_build_enzyme_state_dynamics_rejects_mismatched_network_id():
    mismatched = _concentration_set(network_id="different-network")
    with pytest.raises(EnzymeStateDynamicsReferenceError):
        build_enzyme_state_dynamics(_network(), mismatched)


def test_build_enzyme_state_dynamics_is_deterministic():
    first = build_enzyme_state_dynamics(_network(), _concentration_set())
    second = build_enzyme_state_dynamics(_network(), _concentration_set())
    assert first.network.species == second.network.species
    assert first.network.reactions == second.network.reactions
    assert first.pools == second.pools
    assert first.state_concentrations == second.state_concentrations
    assert first.transition_assignments == second.transition_assignments


def test_merge_transition_assignments_appends_without_reordering_originals():
    original = KineticLawAssignmentSet(
        network_id="n1",
        characterization_policy_version="v1",
        kinetic_law_policy_version="v1",
        assignments=(),
    )
    result = build_enzyme_state_dynamics(_network())
    merged = merge_transition_assignments(original, result.transition_assignments)
    assert merged.network_id == original.network_id
    assert merged.assignments == result.transition_assignments


# --- Parameter declaration integration ------------------------------------------------------


def test_transition_rate_constant_is_heuristic_when_no_evidence_exists():
    result = build_enzyme_state_dynamics(_network())
    merged = merge_transition_assignments(
        KineticLawAssignmentSet(
            network_id="n1",
            characterization_policy_version="v1",
            kinetic_law_policy_version="v1",
            assignments=(),
        ),
        result.transition_assignments,
    )
    declared = declare_parameters(merged, result.network)
    (k_param,) = declared.parameter_specifications
    assert k_param.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert "heuristic" in (k_param.uncertainty_text or "").lower() or k_param.source is (
        ParameterSource.HEURISTIC_INITIALIZATION
    )


# --- Full real-pipeline integration: the synthetic phosphorylation regression ---------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.2"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _curated_compartment(**overrides) -> CuratedCompartment:
    merged = {"id": "cyto", "name": "cytosol"} | overrides
    return CuratedCompartment(**merged)


def _compound(**overrides) -> CuratedCompound:
    merged = {"id": "a", "name": "A"} | overrides
    return CuratedCompound(**merged)


def _curated_reaction(**overrides) -> CuratedReaction:
    merged = {"id": "r1", "name": "reaction 1"} | overrides
    return CuratedReaction(**merged)


def _curated_participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "a",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _curated_association(**overrides) -> CuratedReactionEnzymeAssociation:
    merged = {"reaction_id": "r1", "relationship": "CATALYZES"} | overrides
    return CuratedReactionEnzymeAssociation(**merged)


def _curated_measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "m1",
        "parameter_type": "K",
        "value": Decimal("1"),
        "unit": "per_nMs",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _phosphorylation_regression_handoff() -> Agent1CuratedKnowledgeViewContract:
    """The task's own required synthetic regression: two states (``E``/``E_P``) of one
    protein (``p1``) both catalyze the same reaction ``r1`` (with independent evidence),
    connected by a curated, explicit phosphorylation/dephosphorylation transition pair."""
    return _handoff(
        compartments=(_curated_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_curated_reaction(id="r1"),),
        reaction_participants=(
            _curated_participant(compound_id="a", role="REACTANT"),
            _curated_participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            # Protein-general association: required for resolve_enzyme_concentrations's
            # own protein-level scoping (it never infers a protein from an enzyme state
            # alone) -- the state-specific associations below still exclusively target
            # each state's own kinetic-law context.
            _curated_association(protein_id="p1"),
            _curated_association(enzyme_state_id="E"),
            _curated_association(enzyme_state_id="E_P"),
        ),
        kinetic_measurements=(
            _curated_measurement(
                id="m-e", enzyme_state_id="E", reported_rate_law="k1 * a", parameter_type="K"
            ),
        ),
        enzyme_states=(
            CuratedEnzymeState(
                id="E", state_type="unmodified", protein_id="p1", compartment_id="cyto"
            ),
            CuratedEnzymeState(
                id="E_P", state_type="phosphorylated", protein_id="p1", compartment_id="cyto"
            ),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t-phos",
                from_state_id="E",
                to_state_id="E_P",
                transition_type="phosphorylation",
            ),
            CuratedEnzymeStateTransition(
                id="t-dephos",
                from_state_id="E_P",
                to_state_id="E",
                transition_type="dephosphorylation",
            ),
        ),
        quantitative_observations=(
            CuratedQuantitativeObservation(
                id="obs-p1-total",
                observation_type="PROTEIN_CONCENTRATION",
                value=Decimal("100"),
                unit="nM",
                evidence_class="REFERENCE_BASELINE",
                protein_id="p1",
            ),
            CuratedQuantitativeObservation(
                id="obs-e-specific",
                observation_type="PROTEIN_CONCENTRATION",
                value=Decimal("30"),
                unit="nM",
                evidence_class="REFERENCE_BASELINE",
                enzyme_state_id="E",
            ),
        ),
    )


def test_phosphorylation_regression_end_to_end():
    handoff = _phosphorylation_regression_handoff()
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    kinetic_laws = assign_kinetic_laws(characterization, network)
    enzyme_concentrations = resolve_enzyme_concentrations(network)

    dynamics = build_enzyme_state_dynamics(network, enzyme_concentrations)
    assert len(dynamics.pools) == 1
    (pool,) = dynamics.pools
    assert pool.protein_id == "p1"
    assert pool.state_ids == ("E", "E_P")
    assert pool.transition_ids == ("t-dephos", "t-phos")

    # E's own concentration is directly measured (30 nM); E_P's is the pool-conservation
    # remainder (100 - 30 = 70 nM) -- never a fabricated even split.
    concentrations_by_state = {ec.enzyme_state_id: ec for ec in dynamics.state_concentrations}
    assert concentrations_by_state["E"].value == Decimal("30")
    assert (
        concentrations_by_state["E"].basis
        is EnzymeConcentrationBasis.MEASURED_STATE_SPECIFIC_CONCENTRATION
    )
    assert concentrations_by_state["E_P"].value == Decimal("70")
    assert (
        concentrations_by_state["E_P"].basis is EnzymeConcentrationBasis.POOL_CONSERVATION_DERIVED
    )

    # Parameters computed twice, once against the original network/assignments (for
    # boundaries/modules -- unaffected by this increment), once against the merged/
    # augmented pair (for the final model) -- mirrors this package's own documented
    # two-pass wiring (see app.agent2.enzyme_state_dynamics.builder's module docstring).
    parameters_for_boundaries = declare_parameters(kinetic_laws, network, enzyme_concentrations)
    boundaries = assess_boundaries(
        network, characterization, kinetic_laws, parameters_for_boundaries
    )
    modules = decompose_network(network, kinetic_laws, parameters_for_boundaries, boundaries)

    merged_kinetic_laws = merge_transition_assignments(
        kinetic_laws, dynamics.transition_assignments
    )
    parameters = declare_parameters(
        merged_kinetic_laws,
        dynamics.network,
        enzyme_concentrations,
        enzyme_state_concentrations=dynamics.state_concentrations,
    )

    model = assemble_model_specification(
        dynamics.network,
        merged_kinetic_laws,
        parameters,
        boundaries,
        modules,
        enzyme_concentrations=enzyme_concentrations,
        enzyme_state_pools=dynamics.pools,
        enzyme_state_concentrations=dynamics.state_concentrations,
    )
    assert model.enzyme_state_pools == dynamics.pools
    assert model.enzyme_state_concentrations == dynamics.state_concentrations
    assert any(
        a.category == "enzyme_state_dynamics"
        and a.reason_code == "ENZYME_STATE_POOL_CONSERVATION_APPLIED"
        for a in model.model_assumptions
    )

    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    text = package.full_antimony.antimony_text
    reaction_r1_line = next(line for line in text.splitlines() if line.startswith("J_r1:"))
    assert " + (" in reaction_r1_line
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY" in reaction_r1_line
    transition_reaction_lines = [
        line for line in text.splitlines() if line.startswith("J_enzyme_state_transition")
    ]
    assert len(transition_reaction_lines) == 2
