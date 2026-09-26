"""Tests for ModelSpecification Assembly (Increment 8): ``app.agent2.model_specification``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, runs it
through the full real pipeline (assemble_full_network ->
characterize_full_network -> assign_kinetic_laws -> declare_parameters ->
assess_boundaries -> decompose_network -> assemble_model_specification),
matching every other Agent 2 test file's own convention. Each fixture
that targets a specific `KineticLawType`/`KineticLawAssignmentSource` is
confirmed empirically against the actual, already-implemented Increment
4/5 rule catalog -- never assumed.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.model_specification import (
    IncompatibleArtifactVersionError,
    ModelSpecificationReferenceError,
    UnsupportedModelSpecificationInputError,
    assemble_model_specification,
)
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    KineticLawAssignmentSource,
    KineticLawType,
    ModelSpecification,
)
from app.agent2.version import AGENT2_CONTRACT_VERSION

# --- Fixtures --------------------------------------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.2"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _compartment(**overrides) -> CuratedCompartment:
    merged = {"id": "cyto", "name": "cytosol"} | overrides
    return CuratedCompartment(**merged)


def _compound(**overrides) -> CuratedCompound:
    merged = {"id": "a", "name": "A"} | overrides
    return CuratedCompound(**merged)


def _reaction(**overrides) -> CuratedReaction:
    merged = {"id": "r1", "name": "reaction 1"} | overrides
    return CuratedReaction(**merged)


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


def _measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km1",
        "parameter_type": "rate",
        "value": Decimal("1"),
        "unit": "1/s",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _assemble_full(handoff: Agent1CuratedKnowledgeViewContract):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    modules = decompose_network(network, assignments, parameters, boundaries)
    model = assemble_model_specification(network, assignments, parameters, boundaries, modules)
    return network, assignments, parameters, boundaries, modules, model


def _assemble(handoff: Agent1CuratedKnowledgeViewContract) -> ModelSpecification:
    return _assemble_full(handoff)[-1]


def _simple_two_reaction_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b"), _compound(id="c")),
        "reactions": (_reaction(id="r1"), _reaction(id="r2")),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
    } | overrides
    return _handoff(**merged)


def _one_reaction_no_evidence_handoff() -> Agent1CuratedKnowledgeViewContract:
    """A single reaction with no catalyst, no reported law, unknown reversibility --
    confirmed UNASSIGNED."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
    )


def _reported_law_handoff(reported_rate_law: str) -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        kinetic_measurements=(_measurement(reported_rate_law=reported_rate_law),),
    )


def _michaelis_menten_handoff() -> Agent1CuratedKnowledgeViewContract:
    """Catalyzed, no reported law, reversibility unknown -- confirmed the conservative
    Michaelis-Menten heuristic (HEURISTIC, non-tentative)."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r1", protein_id="p1"),),
    )


def _multi_substrate_michaelis_menten_handoff() -> Agent1CuratedKnowledgeViewContract:
    """Two reactants, one product, curated reported law text explicitly naming
    "Michaelis-Menten" -- confirmed CURATED_REPORTED/MICHAELIS_MENTEN even though the
    heuristic (single-reactant-only) path could never reach this reaction on its own."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
        ),
        kinetic_measurements=(_measurement(reported_rate_law="Michaelis-Menten kinetics"),),
    )


def _tentative_mass_action_handoff() -> Agent1CuratedKnowledgeViewContract:
    """Catalyzed and explicitly reversible -- confirmed TENTATIVE_MASS_ACTION_DEFAULT
    (HEURISTIC, is_tentative=True), which disqualifies the Michaelis-Menten heuristic."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1", reversible=True),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r1", protein_id="p1"),),
    )


def _enzyme_state_specific_handoff() -> Agent1CuratedKnowledgeViewContract:
    """One reaction, two distinct enzyme-state catalytic contexts (E, E_P) -- confirmed two
    separate assignments, never collapsed."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        enzyme_states=(
            CuratedEnzymeState(id="E", state_type="unmodified"),
            CuratedEnzymeState(id="E_P", state_type="phosphorylated"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id=None, enzyme_state_id="E"),
            _enzyme_association(reaction_id="r1", protein_id=None, enzyme_state_id="E_P"),
        ),
    )


def _collapsed_isozymes_handoff() -> Agent1CuratedKnowledgeViewContract:
    """One reaction, two isozymes (p1/p2) with identical (empty) evidence -- confirmed
    collapsed by Increment 4 into one shared, context-free assignment."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r1", protein_id="p2"),
        ),
    )


def _branch_point_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1: a -> x; R2: x -> y; R3: x -> z -- confirmed MEDIUM (BRANCH_POINT) on both
    boundaries, never cut."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="x"), _compound(id="y"), _compound(id="z")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="x", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="x", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="x", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="z", role="PRODUCT"),
        ),
    )


def _irreversible_two_module_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1 (reversible=False, catalyzed) -> R2 -- confirmed VERY_HIGH, cut into two modules
    with exactly one interface."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=False), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r1", protein_id="p1"),),
    )


# --- Basic assembly (Step 33) --------------------------------------------------------------


def test_empty_network_assembles_to_a_valid_model_with_no_reactions():
    model = _assemble(_handoff())
    assert model.full_network.reactions == ()
    assert model.kinetic_laws == ()
    assert model.parameters == ()
    assert model.module_specifications == ()
    assert model.module_decomposition is not None
    assert model.module_decomposition.module_ids == ()


def test_one_reaction_one_kinetic_law_one_parameter_one_module():
    model = _assemble(_michaelis_menten_handoff())
    assert len(model.full_network.reactions) == 1
    assert len(model.kinetic_laws) == 1
    assert model.kinetic_laws[0].law_type is KineticLawType.MICHAELIS_MENTEN
    assert len(model.parameters) >= 1
    assert len(model.module_specifications) == 1


def test_model_id_is_deterministic_and_stable():
    handoff = _michaelis_menten_handoff()
    first = _assemble(handoff)
    second = _assemble(handoff)
    assert first.model_id == second.model_id
    assert first.model_id.startswith("model::")


def test_repeated_assembly_is_fully_deterministic():
    handoff = _michaelis_menten_handoff()
    first = _assemble(handoff)
    second = _assemble(handoff)
    assert first == second


def test_contract_version_matches_current_agent2_contract_version():
    model = _assemble(_michaelis_menten_handoff())
    assert model.contract_version == AGENT2_CONTRACT_VERSION


# --- Kinetic-law materialization (Step 34) ------------------------------------------------


def test_mass_action_expression_uses_species_and_parameter_ids():
    model = _assemble(_reported_law_handoff("k1 * A"))
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MASS_ACTION
    assert law.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    (param_id,) = law.parameter_ids
    (species_id,) = law.species_ids
    assert law.expression == f"{param_id} * {species_id}"


def test_reversible_mass_action_expression_has_forward_minus_reverse():
    model = _assemble(_reported_law_handoff("kf * A - kr * B"))
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.REVERSIBLE_MASS_ACTION
    assert " - " in law.expression
    assert len(law.parameter_ids) == 2
    assert len(law.species_ids) == 2


def test_michaelis_menten_expression_matches_canonical_form():
    model = _assemble(_michaelis_menten_handoff())
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MICHAELIS_MENTEN
    kcat_id, km_id = law.parameter_ids
    (species_id,) = law.species_ids
    assert law.expression == f"{kcat_id} * {species_id} / ({km_id} + {species_id})"


def test_multi_substrate_michaelis_menten_does_not_assert_unjustified_algebra():
    """Case A (final pre-commit revision): a genuinely multi-substrate MM law must never
    receive a simplified, scientifically-unjustified combining expression, nor a non-
    expression status marker in `expression` -- the law family is preserved
    (`law_type=MICHAELIS_MENTEN`), `expression` is `None` (the law family is known, the exact
    algebra is not), and the unresolved state is disclosed only through assumptions/reason
    codes."""
    model = _assemble(_multi_substrate_michaelis_menten_handoff())
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MICHAELIS_MENTEN
    assert law.expression is None
    assert law.has_expression is False
    # Parameter declarations are preserved -- the unresolved expression does not erase them.
    assert len(law.parameter_ids) == 3  # kcat + one Km per substrate, still preserved
    assert len(law.species_ids) == 2  # both substrates still preserved
    # Catalytic context and assignment source are preserved exactly as decided upstream.
    assert law.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert law.enzyme_state_id is None
    assert law.protein_id is None
    assert law.complex_id is None
    assert any("no single combining algebra is asserted" in a for a in law.assumptions)
    unresolved_assumptions = [
        a
        for a in model.model_assumptions
        if a.assumption_id.startswith("assumption::unresolved-multi-substrate::")
    ]
    assert len(unresolved_assumptions) == 1
    assumption = unresolved_assumptions[0]
    assert assumption.reason_code == "MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED"
    # The assumption statement names all four required facts (Increment 8 revision, Step 2).
    assert "Michaelis-Menten" in assumption.statement
    assert "multiple substrates" in assumption.statement.lower()
    assert "no justified canonical multi-substrate algebra" in assumption.statement
    assert "serialization must be withheld" in assumption.statement.lower()


def test_no_expression_sentinel_leakage_anywhere():
    """Case E: the removed string sentinel must never be importable/exported as a live symbol,
    and must never appear in any real assembled model output. (Its name legitimately still
    appears in this increment's own docstrings/comments documenting that it was removed --
    exactly like this repository's other scope-safety tests, that historical prose is not
    what this check is about; see `app.agent2.model_specification.mapping`'s own module
    docstring.)"""
    from app.agent2.model_specification import mapping

    assert not hasattr(mapping, "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM")
    assert "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM" not in mapping.__all__

    model = _assemble(_multi_substrate_michaelis_menten_handoff())
    for law in model.kinetic_laws:
        assert law.expression != "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"
        for assumption_text in law.assumptions:
            assert "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM" not in assumption_text
    for assumption in model.model_assumptions:
        assert assumption.reason_code != "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"
        assert "UNRESOLVED_MULTI_SUBSTRATE_MECHANISM" not in assumption.statement


def test_hill_expression_matches_canonical_form():
    model = _assemble(_reported_law_handoff("Hill kinetics"))
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.HILL
    vmax_id, km_id, n_id = law.parameter_ids
    (species_id,) = law.species_ids
    expected = f"{vmax_id} * {species_id}^{n_id} / ({km_id}^{n_id} + {species_id}^{n_id})"
    assert law.expression == expected


def test_custom_law_preserves_reported_text_verbatim():
    text = "some_proprietary_fn(A, B)"
    model = _assemble(_reported_law_handoff(text))
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.CUSTOM
    assert law.expression == text


def test_unassigned_law_has_no_expression_and_is_preserved():
    model = _assemble(_one_reaction_no_evidence_handoff())
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.UNASSIGNED
    assert law.expression is None
    assert law.parameter_ids == ()


def test_no_kinetic_law_decision_is_recomputed():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _michaelis_menten_handoff()
    )
    (assignment,) = assignments.assignments
    (law,) = model.kinetic_laws
    assert law.law_type is assignment.kinetic_law_type
    assert law.reaction_id == assignment.reaction_id


# --- Parameter linkage (Step 35) -----------------------------------------------------------


def test_parameter_linked_to_correct_assignment_and_kinetic_law():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _michaelis_menten_handoff()
    )
    (assignment,) = assignments.assignments
    (law,) = model.kinetic_laws
    for spec in model.parameters:
        assert spec.kinetic_law_assignment_id == assignment.assignment_id
        assert spec.parameter_id in law.parameter_ids


def test_missing_assignment_reference_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_spec = dataclasses.replace(
        parameters.parameter_specifications[0], kinetic_law_assignment_id="does-not-exist"
    )
    bad_parameters = dataclasses.replace(parameters, parameter_specifications=(bad_spec,))
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(network, assignments, bad_parameters, boundaries, modules)


def test_duplicate_parameter_not_created():
    model = _assemble(_michaelis_menten_handoff())
    ids = [p.parameter_id for p in model.parameters]
    assert len(ids) == len(set(ids))


def test_value_unit_source_preserved_byte_for_byte():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _reported_law_handoff("k1 * A")
    )
    original = {p.parameter_id: p for p in parameters.parameter_specifications}
    for spec in model.parameters:
        source = original[spec.parameter_id]
        assert spec.value == source.value
        assert spec.unit == source.unit
        assert spec.source == source.source


# --- Tentative law preservation (Step 36) --------------------------------------------------


def test_tentative_mass_action_remains_machine_identifiable():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _tentative_mass_action_handoff()
    )
    (assignment,) = assignments.assignments
    assert assignment.is_tentative
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MASS_ACTION
    # assignment_source is now the real, verbatim KineticLawAssignmentSource -- HEURISTIC alone
    # does not distinguish tentative from non-tentative, so tentative-ness is confirmed via the
    # disclosed assumption text (mirroring assignment.is_tentative, never re-derived from a
    # lossy bridge on assignment_source itself).
    assert law.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert any("Tentative" in a for a in law.assumptions)
    tentative_assumptions = [
        a
        for a in model.model_assumptions
        if a.assumption_id.startswith("assumption::tentative-law::")
    ]
    assert len(tentative_assumptions) == 1
    assert tentative_assumptions[0].reason_code == "TENTATIVE_MASS_ACTION_DEFAULT"


def test_tentative_law_never_upgraded_to_deterministic_or_curated():
    model = _assemble(_tentative_mass_action_handoff())
    (law,) = model.kinetic_laws
    assert law.assignment_source is not KineticLawAssignmentSource.CURATED_REPORTED
    assert law.assignment_source is not KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL


# --- Enzyme-state specificity (Step 37) -----------------------------------------------------


def test_enzyme_states_remain_separate_catalytic_contexts():
    """Increment 8 pre-commit revision: catalytic context is a first-class field, not
    provenance text -- Increment 9 can resolve it directly, never by parsing a string."""
    model = _assemble(_enzyme_state_specific_handoff())
    assert len(model.kinetic_laws) == 2
    enzyme_state_ids = {law.enzyme_state_id for law in model.kinetic_laws}
    assert enzyme_state_ids == {"E", "E_P"}
    for law in model.kinetic_laws:
        assert law.protein_id is None
        assert law.complex_id is None


def test_enzyme_states_have_separate_parameters_never_collapsed():
    model = _assemble(_enzyme_state_specific_handoff())
    law_e, law_e_p = sorted(model.kinetic_laws, key=lambda law: law.kinetic_law_id)
    assert set(law_e.parameter_ids).isdisjoint(law_e_p.parameter_ids)
    assert law_e.parameter_ids
    assert law_e_p.parameter_ids


# --- Multiple catalysts (Step 38) -----------------------------------------------------------


def test_collapsed_isozymes_stay_collapsed_as_upstream_decided():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _collapsed_isozymes_handoff()
    )
    assert len(assignments.assignments) == 1
    assert len(model.kinetic_laws) == 1


def test_divergent_catalytic_contexts_remain_separate():
    model = _assemble(_enzyme_state_specific_handoff())
    reaction_ids = {law.reaction_id for law in model.kinetic_laws}
    assert reaction_ids == {"r1"}
    assert len({law.kinetic_law_id for law in model.kinetic_laws}) == 2


# --- Module integration (Step 39) -----------------------------------------------------------


def test_exactly_one_decomposition_required():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    # Constructing a ModuleDecompositionSet with duplicate decomposition ids is itself
    # rejected at the type level -- build a second, distinctly-id'd decomposition to actually
    # reach assembly's own "exactly one" check.
    second = dataclasses.replace(modules.decompositions[0], decomposition_id="decomposition-2")
    two_decompositions = dataclasses.replace(
        modules, decompositions=(modules.decompositions[0], second)
    )
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(
            network, assignments, parameters, boundaries, two_decompositions
        )


def test_module_ids_and_references_preserved_verbatim():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _simple_two_reaction_handoff()
    )
    assert model.module_specifications == modules.module_specifications
    assert model.module_decomposition == modules.decompositions[0]


def test_candidate_boundaries_preserved_in_assembled_model():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _branch_point_handoff()
    )
    decomposition = modules.decompositions[0]
    assert decomposition.candidate_boundary_ids
    assert model.module_decomposition.candidate_boundary_ids == decomposition.candidate_boundary_ids
    candidate_assumptions = {
        a.assumption_id for a in model.model_assumptions if "candidate-boundary" in a.assumption_id
    }
    assert len(candidate_assumptions) == len(decomposition.candidate_boundary_ids)


def test_selected_boundaries_and_interfaces_preserved():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _irreversible_two_module_handoff()
    )
    decomposition = modules.decompositions[0]
    assert decomposition.boundary_assessment_ids
    assert len(decomposition.interfaces) == 1
    assert (
        model.module_decomposition.boundary_assessment_ids
        == decomposition.boundary_assessment_ids
    )
    assert model.module_decomposition.interfaces == decomposition.interfaces


# --- Assumptions (Step 40) -------------------------------------------------------------------


def test_placeholder_parameter_assumption_present():
    model = _assemble(_michaelis_menten_handoff())
    placeholder_ids = {p.parameter_id for p in model.parameters if p.is_placeholder}
    assumption_ids = {
        a.assumption_id.removeprefix("assumption::placeholder-parameter::")
        for a in model.model_assumptions
        if a.assumption_id.startswith("assumption::placeholder-parameter::")
    }
    assert assumption_ids == placeholder_ids


def test_unassigned_law_assumption_present():
    model = _assemble(_one_reaction_no_evidence_handoff())
    unassigned = [
        a
        for a in model.model_assumptions
        if a.assumption_id.startswith("assumption::unassigned-law::")
    ]
    assert len(unassigned) == 1


def test_assumptions_are_deterministically_ordered_and_never_duplicated():
    handoff = _branch_point_handoff()
    first = _assemble(handoff)
    second = _assemble(handoff)
    assert first.model_assumptions == second.model_assumptions
    ids = [a.assumption_id for a in first.model_assumptions]
    assert len(ids) == len(set(ids))


# --- Version compatibility (Step 41) ---------------------------------------------------------


def test_matching_artifact_versions_accepted():
    # Every fixture already exercises the successful path; this is an explicit positive check.
    model = _assemble(_simple_two_reaction_handoff())
    assert model.model_id


def test_mismatched_kinetic_law_policy_version_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    bad_parameters = dataclasses.replace(parameters, kinetic_law_policy_version="bogus")
    with pytest.raises(IncompatibleArtifactVersionError):
        assemble_model_specification(network, assignments, bad_parameters, boundaries, modules)


def test_mismatched_parameter_policy_version_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    bad_parameters = dataclasses.replace(parameters, parameter_policy_version="bogus")
    with pytest.raises(IncompatibleArtifactVersionError):
        assemble_model_specification(network, assignments, bad_parameters, boundaries, modules)


def test_mismatched_boundary_policy_version_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    bad_modules = dataclasses.replace(modules, boundary_policy_version="bogus")
    with pytest.raises(IncompatibleArtifactVersionError):
        assemble_model_specification(network, assignments, parameters, boundaries, bad_modules)


def test_mismatched_network_id_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    bad_boundaries = dataclasses.replace(boundaries, network_id="other-network")
    with pytest.raises(IncompatibleArtifactVersionError):
        assemble_model_specification(network, assignments, parameters, bad_boundaries, modules)


def test_no_compatibility_shim_invented():
    """Mismatched versions are rejected outright -- never silently reconciled."""
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _simple_two_reaction_handoff()
    )
    bad_boundaries = dataclasses.replace(boundaries, kinetic_law_policy_version="kinetic-law-v999")
    with pytest.raises(IncompatibleArtifactVersionError):
        assemble_model_specification(network, assignments, parameters, bad_boundaries, modules)


# --- Structural validation (Step 42) ---------------------------------------------------------


def test_unsupported_input_type_rejected():
    with pytest.raises(UnsupportedModelSpecificationInputError):
        assemble_model_specification("not-a-network", None, None, None, None)


def test_dangling_parameter_kinetic_law_assignment_reference_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_spec = dataclasses.replace(
        parameters.parameter_specifications[0], kinetic_law_assignment_id="missing-assignment"
    )
    bad_parameters = dataclasses.replace(parameters, parameter_specifications=(bad_spec,))
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(network, assignments, bad_parameters, boundaries, modules)


def test_dangling_module_kinetic_law_assignment_reference_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_module = dataclasses.replace(
        modules.module_specifications[0], kinetic_law_assignment_ids=("missing-assignment",)
    )
    bad_modules = dataclasses.replace(modules, module_specifications=(bad_module,))
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(network, assignments, parameters, boundaries, bad_modules)


def test_dangling_reaction_reference_in_kinetic_law_assignment_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_assignment = dataclasses.replace(
        assignments.assignments[0], reaction_id="missing-reaction"
    )
    bad_assignments = dataclasses.replace(assignments, assignments=(bad_assignment,))
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(network, bad_assignments, parameters, boundaries, modules)


def test_dangling_module_species_reference_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_module = dataclasses.replace(modules.module_specifications[0], species_ids=("missing",))
    bad_modules = dataclasses.replace(modules, module_specifications=(bad_module,))
    with pytest.raises(ValueError):
        assemble_model_specification(network, assignments, parameters, boundaries, bad_modules)


def test_dangling_kinetic_law_enzyme_state_reference_rejected():
    """Increment 8 pre-commit revision: enzyme_state_id is now first-class and cross-checked
    against FullNetwork.enzyme_states (a real, complete registry)."""
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _enzyme_state_specific_handoff()
    )
    bad_assignment = dataclasses.replace(assignments.assignments[0], enzyme_state_id="missing")
    bad_assignments = dataclasses.replace(
        assignments, assignments=(bad_assignment, *assignments.assignments[1:])
    )
    with pytest.raises(ValueError):
        assemble_model_specification(network, bad_assignments, parameters, boundaries, modules)


def test_zero_decompositions_rejected():
    network, assignments, parameters, boundaries, modules, _ = _assemble_full(
        _michaelis_menten_handoff()
    )
    bad_modules = dataclasses.replace(modules, decompositions=())
    with pytest.raises(ModelSpecificationReferenceError):
        assemble_model_specification(network, assignments, parameters, boundaries, bad_modules)


# --- No numeric/probabilistic assembly, no anonymous provenance ------------------------------


def test_model_specification_carries_full_provenance():
    network, assignments, parameters, boundaries, modules, model = _assemble_full(
        _michaelis_menten_handoff()
    )
    assert model.full_network is network
    assert model.boundary_assessments == boundaries.assessments
    for law in model.kinetic_laws:
        assert any(ref.startswith("kinetic-law-assignment::") for ref in law.provenance_refs)


# --- "Unresolved Kinetic Evidence Disclosure" increment ---------------------------------------
#
# Real Integration Pilot 2 Run 2: 14 real SABIO-RK kinetic measurements survived the Agent 1
# handoff and assembly untouched, correctly excluded from reaction-specific kinetic-law
# assignment (none has a resolved reaction_id), but that exclusion was invisible in the final
# ModelSpecification -- indistinguishable from "no kinetic evidence exists at all." These
# tests use a regression fixture modeled directly on the real situation: a normal, working
# reaction (its own reported-rate-law catalyst, unaffected) plus a separate measurement
# shared by two proteins (FAS1/FAS2-shaped) with unresolved reaction attribution.


def _shared_protein_unresolved_reaction_handoff() -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="r1", protein_id="fas2", relationship="CATALYZES"
            ),
        ),
        kinetic_measurements=(
            _measurement(
                id="km-r1-reported",
                reaction_id="r1",
                protein_id="fas2",
                reported_rate_law="k1*a",
            ),
            _measurement(
                id="km-fas-shared",
                reaction_id=None,
                protein_id=None,
                protein_ids=("fas2", "fas1"),
                parameter_type="VMAX",
                value=Decimal("3340.0"),
                unit="nmol/(min*mg)",
                source="SABIORK",
                source_id="18229:Vmax",
            ),
        ),
    )


def test_deferred_measurement_excluded_from_reaction_specific_kinetic_assignment():
    _network, assignments, _parameters, _boundaries, _modules, _model = _assemble_full(
        _shared_protein_unresolved_reaction_handoff()
    )
    referenced_measurement_ids = {
        mid for a in assignments.assignments for mid in a.source_measurement_ids
    }
    assert "km-fas-shared" not in referenced_measurement_ids
    assert "km-r1-reported" in referenced_measurement_ids  # regression: normal case unaffected


def test_deferred_measurement_produces_explicit_disclosure():
    model = _assemble(_shared_protein_unresolved_reaction_handoff())
    disclosures = [
        a
        for a in model.model_assumptions
        if a.reason_code == "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"
    ]
    assert len(disclosures) == 1
    assert disclosures[0].assumption_id == (
        "assumption::kinetic-measurement-reaction-unresolved::km-fas-shared"
    )


def test_disclosure_references_correct_measurement_and_protein_provenance():
    model = _assemble(_shared_protein_unresolved_reaction_handoff())
    disclosure = next(
        a
        for a in model.model_assumptions
        if a.reason_code == "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"
    )
    assert "km-fas-shared" in disclosure.related_entity_ids
    assert "fas1" in disclosure.related_entity_ids
    assert "fas2" in disclosure.related_entity_ids
    assert "km-fas-shared" in disclosure.statement
    assert "fas1" in disclosure.statement and "fas2" in disclosure.statement
    assert disclosure.category == "kinetics"
    assert disclosure.source == "app.agent2.model_specification"


def test_reaction_attributed_measurement_produces_no_such_disclosure():
    """Regression: a normal, reaction-attributed measurement (km-r1-reported) must not
    itself trigger the new disclosure -- only the genuinely unresolved one does."""
    model = _assemble(_shared_protein_unresolved_reaction_handoff())
    disclosure_targets = {
        a.assumption_id.removeprefix("assumption::kinetic-measurement-reaction-unresolved::")
        for a in model.model_assumptions
        if a.reason_code == "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"
    }
    assert "km-r1-reported" not in disclosure_targets


def test_absent_kinetic_evidence_produces_no_disclosure_of_this_kind():
    """'No kinetic evidence exists' must remain distinguishable from 'kinetic evidence
    exists but is deferred' -- the former produces zero disclosures of this reason code,
    never a false-positive placeholder disclosure."""
    model = _assemble(_one_reaction_no_evidence_handoff())
    disclosures = [
        a
        for a in model.model_assumptions
        if a.reason_code == "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"
    ]
    assert disclosures == []


def test_no_real_parameter_generated_from_deferred_measurement():
    model = _assemble(_shared_protein_unresolved_reaction_handoff())
    # The deferred measurement's own real value (3340.0) must never appear as any
    # parameter's value -- zero fabrication from unresolved-reaction-context evidence.
    real_valued = [p for p in model.parameters if p.value is not None]
    assert all(p.value != Decimal("3340.0") for p in real_valued)


def test_deferred_measurement_repeated_assembly_is_deterministic():
    handoff = _shared_protein_unresolved_reaction_handoff()
    first = _assemble(handoff)
    second = _assemble(handoff)
    assert first.model_assumptions == second.model_assumptions


def test_kinetic_law_selection_and_placeholder_behavior_unchanged_by_deferred_measurement():
    """The core selector rule and placeholder behavior are completely unaffected by the
    presence of a deferred measurement: r1's own catalyzed, reported-rate-law kinetic law
    is still correctly assigned CURATED_REPORTED with its verbatim expression, exactly as
    it would be with no deferred measurement present at all."""
    model = _assemble(_shared_protein_unresolved_reaction_handoff())
    assert len(model.kinetic_laws) == 1
    law = model.kinetic_laws[0]
    assert law.assignment_source == KineticLawAssignmentSource.CURATED_REPORTED
    assert law.has_expression
    # And the reaction's own declared parameters remain PLACEHOLDER, exactly as
    # every other reported-rate-law fixture in this file produces -- untouched by
    # the separate, deferred measurement's own presence.
    reaction_parameter_values = {p.value for p in model.parameters}
    assert Decimal("3340.0") not in reaction_parameter_values
