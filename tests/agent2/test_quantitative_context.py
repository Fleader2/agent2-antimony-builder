"""Tests for Quantitative Context Resolution and Derived Enzyme Concentration
(``app.agent2.quantitative_context``).

Every test builds a ``FullNetwork`` directly (via ``Agent1CuratedKnowledgeViewContract``
+ ``assemble_full_network``, matching every other Agent 2 test file's own convention)
and runs it through ``resolve_enzyme_concentrations`` -- the real pipeline, never a
hand-built ``EnzymeConcentration``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.model_specification import assemble_model_specification
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.quantitative_context import resolve_enzyme_concentrations
from app.agent2.quantitative_context.policy import DEFAULT_ASSUMED_CELL_VOLUME_PL
from app.agent2.quantitative_context.types import QuantitativeContextReasonCode
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedExperimentalContext,
    CuratedQuantitativeObservation,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    EnzymeConcentrationBasis,
    FullNetwork,
)
from app.agent2.version import QUANTITATIVE_CONTEXT_POLICY_VERSION

# --- Fixtures --------------------------------------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.4", "organism_id": "org-1"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _compartment(**overrides) -> CuratedCompartment:
    return CuratedCompartment(**({"id": "cyto", "name": "cytosol"} | overrides))


def _compound(**overrides) -> CuratedCompound:
    return CuratedCompound(**({"id": "a", "name": "A"} | overrides))


def _reaction(**overrides) -> CuratedReaction:
    return CuratedReaction(**({"id": "r1", "name": "reaction 1"} | overrides))


def _participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "a",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _enzyme_association(**overrides) -> CuratedReactionEnzymeAssociation:
    merged = {"reaction_id": "r1", "protein_id": "p1", "relationship": "CATALYZES"} | overrides
    return CuratedReactionEnzymeAssociation(**merged)


def _context(**overrides) -> CuratedExperimentalContext:
    merged = {
        "id": "ctx-1",
        "organism_id": "org-1",
        "strain": "BY4741",
        "classification": "REFERENCE",
        "source": "SGD",
    } | overrides
    return CuratedExperimentalContext(**merged)


def _abundance_observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-abundance-1",
        "observation_type": "PROTEIN_ABUNDANCE",
        "value": Decimal("6670"),
        "unit": "molecules/cell",
        "evidence_class": "REFERENCE_BASELINE",
        "normalized_value": Decimal("6670"),
        "normalized_unit": "molecules_per_cell",
        "uncertainty": Decimal("1539"),
        "protein_id": "p1",
        "organism_id": "org-1",
        "experimental_context_id": "ctx-1",
        "source": "SGD",
        "source_id": "sgd-protein-abundance:S1",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


def _concentration_observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-concentration-1",
        "observation_type": "PROTEIN_CONCENTRATION",
        "value": Decimal("250"),
        "unit": "nM",
        "evidence_class": "EXPERIMENT_SPECIFIC",
        "protein_id": "p1",
        "organism_id": "org-1",
        "experimental_context_id": "ctx-1",
        "source": "CUSTOM_DB",
        "source_id": "custom:conc-1",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


def _volume_observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-volume-1",
        "observation_type": "CELL_VOLUME",
        "value": Decimal("0.042"),
        "unit": "pL",
        "evidence_class": "REFERENCE_BASELINE",
        "organism_id": "org-1",
        "experimental_context_id": "ctx-1",
        "source": "CUSTOM_DB",
        "source_id": "custom:vol-1",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


def _one_protein_network(
    *, observations: tuple[CuratedQuantitativeObservation, ...], contexts=None
) -> FullNetwork:
    if contexts is None:
        contexts = (_context(),)
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
        experimental_contexts=contexts,
        quantitative_observations=observations,
    )
    return assemble_full_network(handoff)


# --- Tier 1: experiment-specific protein concentration --------------------------------------


def test_experiment_specific_concentration_wins_over_everything_else():
    network = _one_protein_network(
        observations=(
            _concentration_observation(),
            _abundance_observation(evidence_class="EXPERIMENT_SPECIFIC", id="obs-abundance-2"),
        )
    )
    result = resolve_enzyme_concentrations(network)
    (outcome,) = result.outcomes
    assert outcome.concentration.basis is EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_CONCENTRATION
    assert outcome.concentration.value == Decimal("250")
    assert outcome.concentration.unit == "nM"


def test_experiment_specific_concentration_dependency_names_source_observation():
    network = _one_protein_network(observations=(_concentration_observation(),))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    (dependency,) = outcome.concentration.dependencies
    assert dependency.role == "concentration_input"
    assert dependency.observation_id == "obs-concentration-1"


# --- Tier 2: experiment-specific abundance + experiment-specific cell volume -----------------


def test_experiment_specific_abundance_and_volume_derives_concentration():
    network = _one_protein_network(
        observations=(
            _abundance_observation(evidence_class="EXPERIMENT_SPECIFIC", id="obs-a"),
            _volume_observation(evidence_class="EXPERIMENT_SPECIFIC", id="obs-v"),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert (
        outcome.concentration.basis
        is EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME
    )
    dependency_roles = {d.role: d.observation_id for d in outcome.concentration.dependencies}
    assert dependency_roles == {"abundance_input": "obs-a", "cell_volume_input": "obs-v"}


def test_reference_concentration_wins_over_experiment_specific_abundance_plus_volume():
    """Tier 1 is checked first, tier 2 only when tier 1 is genuinely absent -- but a
    *reference* concentration (tier 3) must never override a genuinely present
    *experiment-specific* abundance+volume combination (tier 2), since tier 2 outranks
    tier 3."""
    network = _one_protein_network(
        observations=(
            _abundance_observation(evidence_class="EXPERIMENT_SPECIFIC", id="obs-a"),
            _volume_observation(evidence_class="EXPERIMENT_SPECIFIC", id="obs-v"),
            _concentration_observation(evidence_class="REFERENCE_BASELINE", id="obs-c"),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert (
        outcome.concentration.basis
        is EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME
    )


# --- Tier 3: reference protein concentration -------------------------------------------------


def test_reference_concentration_wins_over_reference_abundance_and_assumption():
    network = _one_protein_network(
        observations=(
            _concentration_observation(evidence_class="REFERENCE_BASELINE", id="obs-c"),
            _abundance_observation(),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration.basis is EnzymeConcentrationBasis.REFERENCE_CONCENTRATION
    assert outcome.concentration.value == Decimal("250")


# --- Tier 4: reference abundance + compatible reference cell volume -------------------------


def test_reference_abundance_and_reference_volume_derives_concentration():
    network = _one_protein_network(observations=(_abundance_observation(), _volume_observation()))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert (
        outcome.concentration.basis
        is EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_COMPATIBLE_VOLUME
    )
    from app.agent2.quantitative_context.policy import derive_concentration_nm

    expected = derive_concentration_nm(
        abundance_molecules_per_cell=Decimal("6670"), cell_volume_pl=Decimal("0.042")
    )
    assert outcome.concentration.value == expected


def test_compatible_reference_volume_never_carries_assumption_reason_code():
    network = _one_protein_network(observations=(_abundance_observation(), _volume_observation()))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration.assumption_reason_codes == ()


# --- Tier 5: reference abundance + explicit assumed 0.1 pL -----------------------------------


def test_missing_volume_falls_to_explicit_0_1_pl_assumption():
    network = _one_protein_network(observations=(_abundance_observation(),))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assumed_volume = EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME
    assert outcome.concentration.basis is assumed_volume
    assert outcome.concentration.assumption_reason_codes == (
        QuantitativeContextReasonCode.REFERENCE_CELL_VOLUME_ASSUMED.value,
    )
    assumption_dep = next(
        d for d in outcome.concentration.dependencies if d.role == "cell_volume_input"
    )
    assert assumption_dep.observation_id is None
    assert assumption_dep.assumption_notes is not None
    assert "0.1" in assumption_dep.assumption_notes


def test_assumed_volume_constant_is_the_task_specified_0_1_pl():
    assert Decimal("0.1") == DEFAULT_ASSUMED_CELL_VOLUME_PL


def test_correct_nm_conversion_for_real_confirmed_cdc28_shaped_figure():
    """Real, live-confirmed CDC28-shaped SGD figure: 6670 molecules/cell at the
    assumed 0.1 pL reference volume derives to ~110.76 nM."""
    network = _one_protein_network(observations=(_abundance_observation(),))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration.value.quantize(Decimal("0.01")) == Decimal("110.76")


# --- Incompatible contexts ---------------------------------------------------------------------


def test_incompatible_abundance_and_volume_contexts_are_never_combined():
    other_context = _context(id="ctx-2", strain="strain-B")
    network = _one_protein_network(
        observations=(
            _abundance_observation(experimental_context_id="ctx-1"),
            _volume_observation(experimental_context_id="ctx-2"),
        ),
        contexts=(_context(strain="strain-A"), other_context),
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    # Falls through to tier 5 (assumed volume) since tier 4's own pairing is incompatible --
    # never silently combines the mismatched pair.
    assumed_volume = EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME
    assert outcome.concentration.basis is assumed_volume


def test_unknown_context_compatibility_is_never_treated_as_combinable():
    """Neither observation names an experimental_context_id at all -- CONTEXT_UNKNOWN, not
    combinable (task Sec 5: an unconfirmable relationship is never treated as confirmed)."""
    network = _one_protein_network(
        observations=(
            _abundance_observation(experimental_context_id=None),
            _volume_observation(experimental_context_id=None),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assumed_volume = EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME
    assert outcome.concentration.basis is assumed_volume


# --- Missing data / unresolved -----------------------------------------------------------------


def test_missing_abundance_and_concentration_remains_unresolved():
    network = _one_protein_network(observations=())
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration is None
    assert (
        outcome.unresolved_reason_code
        == QuantitativeContextReasonCode.PROTEIN_CONCENTRATION_UNRESOLVED.value
    )


def test_unresolved_outcome_never_carries_a_concentration():
    network = _one_protein_network(observations=())
    result = resolve_enzyme_concentrations(network)
    assert result.enzyme_concentrations == ()
    assert result.unresolved_protein_ids == ("p1",)


# --- Ambiguity: disagreeing candidates never silently averaged/chosen -----------------------


def test_disagreeing_experiment_specific_concentrations_stay_unresolved_never_fall_through():
    network = _one_protein_network(
        observations=(
            _concentration_observation(id="obs-c1", value=Decimal("250")),
            _concentration_observation(id="obs-c2", value=Decimal("400")),
            _abundance_observation(),  # a usable reference abundance also exists
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration is None
    assert (
        outcome.unresolved_reason_code
        == QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS.value
    )


def test_agreeing_duplicate_concentration_observations_resolve_normally():
    network = _one_protein_network(
        observations=(
            _concentration_observation(id="obs-c1", value=Decimal("250")),
            _concentration_observation(id="obs-c2", value=Decimal("250")),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration is not None
    assert outcome.concentration.value == Decimal("250")


# --- Uncertainty / provenance preservation ----------------------------------------------------


def test_provenance_context_id_preserved_on_derived_concentration():
    network = _one_protein_network(observations=(_abundance_observation(), _volume_observation()))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration.experimental_context_id == "ctx-1"


def test_policy_version_recorded_on_every_concentration():
    network = _one_protein_network(observations=(_abundance_observation(),))
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration.policy_version == QUANTITATIVE_CONTEXT_POLICY_VERSION


# --- No enzyme-state splitting (task Sec 6) ---------------------------------------------------


def test_protein_with_multiple_enzyme_states_still_gets_exactly_one_concentration():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(enzyme_state_id="es-base"),
        ),
        enzyme_states=(
            CuratedEnzymeState(id="es-base", state_type="BASE", protein_id="p1"),
            CuratedEnzymeState(id="es-modified", state_type="MODIFIED", protein_id="p1"),
        ),
        experimental_contexts=(_context(),),
        quantitative_observations=(_abundance_observation(),),
    )
    network = assemble_full_network(handoff)
    result = resolve_enzyme_concentrations(network)
    assert len(result.outcomes) == 1
    assert result.outcomes[0].protein_id == "p1"


# --- Deterministic repeated resolution ---------------------------------------------------------


def test_resolution_is_deterministic():
    network = _one_protein_network(observations=(_abundance_observation(), _volume_observation()))
    first = resolve_enzyme_concentrations(network)
    second = resolve_enzyme_concentrations(network)
    assert first == second


# --- Multiple proteins --------------------------------------------------------------------------


def test_multiple_proteins_resolved_independently():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id="p2"),
        ),
        experimental_contexts=(_context(),),
        quantitative_observations=(
            _abundance_observation(protein_id="p1"),
            # p2 has no observation at all -- must not affect p1's own resolution.
        ),
    )
    network = assemble_full_network(handoff)
    result = resolve_enzyme_concentrations(network)
    assert set(result.resolved_protein_ids) == {"p1"}
    assert set(result.unresolved_protein_ids) == {"p2"}


def test_explicit_protein_ids_parameter_overrides_network_derived_set():
    network = _one_protein_network(observations=(_abundance_observation(),))
    result = resolve_enzyme_concentrations(network, protein_ids=("p1", "p-not-in-network"))
    assert {o.protein_id for o in result.outcomes} == {"p1", "p-not-in-network"}


# --- Never derives from an unrecognized unit --------------------------------------------------


def test_unrecognized_abundance_unit_never_reinterpreted():
    network = _one_protein_network(
        observations=(
            _abundance_observation(
                unit="mg/mL", normalized_value=None, normalized_unit=None, value=Decimal("3")
            ),
        )
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration is None


def test_unrecognized_concentration_unit_never_reinterpreted():
    network = _one_protein_network(
        observations=(_concentration_observation(unit="mg/mL", value=Decimal("3")),)
    )
    (outcome,) = resolve_enzyme_concentrations(network).outcomes
    assert outcome.concentration is None


# --- ModelSpecification exposure (task Sec 7) --------------------------------------------------


def _assemble_full_with_enzyme_concentrations(network: FullNetwork, enzyme_concentrations=None):
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    modules = decompose_network(network, assignments, parameters, boundaries)
    model = assemble_model_specification(
        network,
        assignments,
        parameters,
        boundaries,
        modules,
        enzyme_concentrations=enzyme_concentrations,
    )
    return model


def test_model_specification_exposes_enzyme_concentrations_when_supplied():
    network = _one_protein_network(observations=(_abundance_observation(),))
    resolution = resolve_enzyme_concentrations(network)
    model = _assemble_full_with_enzyme_concentrations(network, resolution)

    (concentration,) = model.enzyme_concentrations
    assert concentration.protein_id == "p1"
    assert concentration.unit == "nM"
    assert concentration.basis is EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME


def test_model_specification_defaults_to_no_enzyme_concentrations_when_omitted():
    """Full backward compatibility: an existing caller that never passes
    ``enzyme_concentrations`` gets an identical ``ModelSpecification`` (empty tuple, no new
    ``ModelAssumption`` records) -- no behavior change at all."""
    network = _one_protein_network(observations=(_abundance_observation(),))
    model = _assemble_full_with_enzyme_concentrations(network)
    assert model.enzyme_concentrations == ()


def test_model_specification_discloses_reference_cell_volume_assumed_as_model_assumption():
    """Task's own explicit requirement: a machine-readable assumption when 0.1 pL is used."""
    network = _one_protein_network(observations=(_abundance_observation(),))
    resolution = resolve_enzyme_concentrations(network)
    model = _assemble_full_with_enzyme_concentrations(network, resolution)

    assumption = next(
        a for a in model.model_assumptions if a.category == "quantitative_context"
    )
    expected_reason_code = QuantitativeContextReasonCode.REFERENCE_CELL_VOLUME_ASSUMED.value
    assert assumption.reason_code == expected_reason_code
    assert "p1" in assumption.related_entity_ids


def test_model_specification_never_discloses_assumption_for_a_real_compatible_volume():
    network = _one_protein_network(observations=(_abundance_observation(), _volume_observation()))
    resolution = resolve_enzyme_concentrations(network)
    model = _assemble_full_with_enzyme_concentrations(network, resolution)

    assert not any(a.category == "quantitative_context" for a in model.model_assumptions)


def test_assemble_model_specification_rejects_mismatched_network_id():
    from app.agent2.model_specification import IncompatibleArtifactVersionError
    from app.agent2.quantitative_context.types import QuantitativeContextResolutionSet

    network = _one_protein_network(observations=(_abundance_observation(),))
    mismatched = QuantitativeContextResolutionSet(
        network_id="network::some-other-network",
        policy_version=QUANTITATIVE_CONTEXT_POLICY_VERSION,
        outcomes=(),
    )
    with pytest.raises(IncompatibleArtifactVersionError):
        _assemble_full_with_enzyme_concentrations(network, mismatched)
