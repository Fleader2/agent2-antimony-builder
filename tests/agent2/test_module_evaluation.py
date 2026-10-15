"""Tests for the Module Boundary Evaluation Framework: ``app.agent2.module_evaluation``.

Builds ``ModelSpecification``/``ModelModularization``/``ModelModule``/``ModuleMembership``/
``ModulePort`` directly (mirroring ``tests/agent2/test_modularization.py``'s own convention)
so each criterion's own scenario can be pinned exactly with a hand-computed expected score.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony_import import import_antimony
from app.agent2.module_evaluation import (
    CriteriaWeights,
    CriterionWeight,
    ModularizationCriterion,
    ModuleEvaluationReferenceError,
    TopologyFilteringPolicy,
    TopologyRole,
    TopologyRoleOverride,
    compare_modularizations,
    evaluate_modularization,
    evaluate_modularization_under_weights,
)
from app.agent2.module_evaluation.criteria import IMPLEMENTED_CRITERIA
from app.agent2.types import (
    CompartmentSourceScope,
    CompartmentSpecification,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ModulePort,
    ModulePortDirection,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures ------------------------------------------------------------------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "c1",
        "name": "c1",
        "source_scope": CompartmentSourceScope.MODELING_CONSTRUCT,
        "assumptions": ("test fixture",),
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "A", "name": "A", "compartment_id": "c1"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "A",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "r1",
        "participants": (
            _participant(species_id="A", role=ParticipantRole.REACTANT),
            _participant(species_id="B", role=ParticipantRole.PRODUCT),
        ),
    } | overrides
    return ReactionSpecification(**merged)


def _linear_network(**overrides) -> FullNetwork:
    """A -> B -> C, a minimal two-reaction chain, both species in compartment "c1"."""
    merged = {
        "network_id": "n1",
        "name": "n1",
        "compartments": (_compartment(),),
        "species": (_species(species_id="A"), _species(species_id="B"), _species(species_id="C")),
        "reactions": (
            _reaction(
                reaction_id="r1",
                participants=(
                    _participant(species_id="A", role=ParticipantRole.REACTANT),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2",
                participants=(
                    _participant(species_id="B", role=ParticipantRole.REACTANT),
                    _participant(species_id="C", role=ParticipantRole.PRODUCT),
                ),
            ),
        ),
    } | overrides
    return FullNetwork(**merged)


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "kl1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": "k1 * A",
        "parameter_ids": ("k1",),
        "species_ids": ("A",),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    merged = {
        "parameter_id": "k1",
        "name": "k1",
        "source": ParameterSource.CURATED,
        "value": Decimal("0.5"),
    } | overrides
    return ParameterSpecification(**merged)


def _model(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _linear_network(),
        "kinetic_laws": (
            _kinetic_law(
                kinetic_law_id="kl1",
                reaction_id="r1",
                expression="k1 * A",
                parameter_ids=("k1",),
                species_ids=("A",),
            ),
            _kinetic_law(
                kinetic_law_id="kl2",
                reaction_id="r2",
                expression="k2 * B",
                parameter_ids=("k2",),
                species_ids=("B",),
            ),
        ),
        "parameters": (
            _parameter(parameter_id="k1", name="k1"),
            _parameter(parameter_id="k2", name="k2"),
        ),
    } | overrides
    return ModelSpecification(**merged)


def _two_module_split(**overrides) -> ModelSpecification:
    """modA = {r1, species A, B}, modB = {r2, species B, C} -- the identical shared-boundary
    shape ``test_modularization.py``'s own ``_user_defined_split`` fixture uses, with an
    explicit OUTPUT/INPUT port pair on the shared species B."""
    modularization = ModelModularization(
        modularization_id="mz1",
        name="two-module split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
    )
    modules = (
        ModelModule(module_id="modA", name="Module A"),
        ModelModule(module_id="modB", name="Module B"),
    )
    memberships = (
        ModuleMembership(
            membership_id="mem_r1",
            modularization_id="mz1",
            module_id="modA",
            component_type=ModuleComponentType.REACTION,
            component_id="r1",
        ),
        ModuleMembership(
            membership_id="mem_r2",
            modularization_id="mz1",
            module_id="modB",
            component_type=ModuleComponentType.REACTION,
            component_id="r2",
        ),
        ModuleMembership(
            membership_id="mem_a",
            modularization_id="mz1",
            module_id="modA",
            component_type=ModuleComponentType.SPECIES,
            component_id="A",
        ),
        ModuleMembership(
            membership_id="mem_b_a",
            modularization_id="mz1",
            module_id="modA",
            component_type=ModuleComponentType.SPECIES,
            component_id="B",
        ),
        ModuleMembership(
            membership_id="mem_b_b",
            modularization_id="mz1",
            module_id="modB",
            component_type=ModuleComponentType.SPECIES,
            component_id="B",
        ),
        ModuleMembership(
            membership_id="mem_c",
            modularization_id="mz1",
            module_id="modB",
            component_type=ModuleComponentType.SPECIES,
            component_id="C",
        ),
    )
    ports = (
        ModulePort(
            port_id="port_a_out",
            modularization_id="mz1",
            module_id="modA",
            species_id="B",
            direction=ModulePortDirection.OUTPUT,
        ),
        ModulePort(
            port_id="port_b_in",
            modularization_id="mz1",
            module_id="modB",
            species_id="B",
            direction=ModulePortDirection.INPUT,
        ),
    )
    merged = {
        "modularizations": (modularization,),
        "model_modules": modules,
        "module_memberships": memberships,
        "module_ports": ports,
    } | overrides
    return _model(**merged)


def _weights(**overrides) -> CriteriaWeights:
    merged = {
        "weights": (
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("1")),
            CriterionWeight(ModularizationCriterion.COMPARTMENT_COHERENCE, Decimal("1")),
            CriterionWeight(ModularizationCriterion.EC_CLASS_COHERENCE, Decimal("1")),
        ),
        "policy_version": "test-v1",
    } | overrides
    return CriteriaWeights(**merged)


def _criterion(evaluation, criterion: ModularizationCriterion):
    (cs,) = (c for c in evaluation.criterion_scores if c.criterion is criterion)
    return cs


# --- CriteriaWeights --------------------------------------------------------------------------


def test_criteria_weights_rejects_all_zero_vector():
    with pytest.raises(ValueError):
        CriteriaWeights(
            weights=(
                CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("0")),
            ),
            policy_version="v1",
        )


def test_criteria_weights_rejects_duplicate_criterion():
    with pytest.raises(ValueError):
        CriteriaWeights(
            weights=(
                CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
                CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("2")),
            ),
            policy_version="v1",
        )


def test_criteria_weights_rejects_negative_weight():
    with pytest.raises(ValueError):
        CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("-1"))


def test_criteria_weights_normalization_is_deterministic():
    w = _weights()
    for criterion in (
        ModularizationCriterion.TOPOLOGICAL_SEPARATION,
        ModularizationCriterion.BOUNDARY_SPARSITY,
        ModularizationCriterion.COMPARTMENT_COHERENCE,
        ModularizationCriterion.EC_CLASS_COHERENCE,
    ):
        assert w.normalized_weight(criterion) == Decimal("0.25")


def test_zero_weight_criterion_disabled_but_still_scored():
    model = _two_module_split()
    weights = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("0")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", weights)
    sparsity = _criterion(evaluation, ModularizationCriterion.BOUNDARY_SPARSITY)
    assert sparsity.available is True
    assert sparsity.raw_score is not None
    assert sparsity.normalized_weight == 0
    assert sparsity.weighted_contribution is None


def test_omitted_criterion_behaves_identically_to_explicit_zero():
    model = _two_module_split()
    explicit_zero = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("0")),
        )
    )
    omitted = _weights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),)
    )
    e1 = evaluate_modularization(model, "mz1", explicit_zero)
    e2 = evaluate_modularization(model, "mz1", omitted)
    assert e1.overall_score == e2.overall_score


# --- Each criterion independently ----------------------------------------------------------------


def test_topological_separation_scores_one_when_adjacent_reactions_share_a_module():
    model = _model(
        modularizations=(
            ModelModularization(
                modularization_id="mz1",
                name="one module",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA",),
            ),
        ),
        model_modules=(ModelModule(module_id="modA", name="Module A"),),
        module_memberships=(
            ModuleMembership(
                membership_id="mem_r1", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r1",
            ),
            ModuleMembership(
                membership_id="mem_r2", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r2",
            ),
        ),
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.available is True
    assert cs.raw_score == Decimal("1")


def test_topological_separation_scores_zero_when_adjacent_reactions_are_cut_apart():
    model = _two_module_split()  # r1 in modA, r2 in modB, sharing species B
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.available is True
    assert cs.raw_score == Decimal("0")


def test_topological_separation_unavailable_with_no_adjacency_edges():
    model = _model(
        full_network=_linear_network(
            reactions=(_reaction(reaction_id="r1", participants=(_participant(species_id="A"),)),)
        ),
        kinetic_laws=(),
        parameters=(),
        modularizations=(
            ModelModularization(
                modularization_id="mz1",
                name="single",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA",),
            ),
        ),
        model_modules=(ModelModule(module_id="modA", name="Module A"),),
        module_memberships=(
            ModuleMembership(
                membership_id="mem_r1", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r1",
            ),
        ),
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.available is False
    assert cs.raw_score is None


def test_boundary_sparsity_is_perfect_with_zero_declared_ports():
    model = _two_module_split(module_ports=())
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.BOUNDARY_SPARSITY)
    assert cs.available is True
    assert cs.raw_score == Decimal("1")


def test_boundary_sparsity_reflects_declared_cross_module_species():
    model = _two_module_split()  # species B has one OUTPUT + one INPUT port; A, B, C are members
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.BOUNDARY_SPARSITY)
    assert cs.available is True
    # 1 of 3 member species (A, B, C) has a declared port -> sparsity = 1 - 1/3
    assert cs.raw_score == Decimal("1") - Decimal("1") / Decimal("3")


def test_boundary_sparsity_unavailable_with_no_species_membership():
    model = _model(
        modularizations=(
            ModelModularization(
                modularization_id="mz1",
                name="no species",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA",),
            ),
        ),
        model_modules=(ModelModule(module_id="modA", name="Module A"),),
        module_memberships=(
            ModuleMembership(
                membership_id="mem_r1", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r1",
            ),
        ),
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.BOUNDARY_SPARSITY)
    assert cs.available is False


def test_compartment_coherence_scores_one_when_module_is_single_compartment():
    model = _two_module_split()  # all species in compartment c1
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.COMPARTMENT_COHERENCE)
    assert cs.available is True
    assert cs.raw_score == Decimal("1")


def test_compartment_coherence_reflects_a_compartment_spanning_module():
    network = _linear_network(
        species=(
            _species(species_id="A", compartment_id="c1"),
            _species(species_id="B", compartment_id="c1"),
            _species(species_id="C", compartment_id="c2"),
        ),
        compartments=(_compartment(compartment_id="c1"), _compartment(compartment_id="c2")),
    )
    model = _two_module_split(full_network=network)
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.COMPARTMENT_COHERENCE)
    assert cs.available is True
    # modA: {A, B} both c1 -> 2/2 = 1.0. modB: {B, C} -> modal compartment count 1 of 2 -> 0.5.
    assert cs.raw_score == (Decimal("1") + Decimal("0.5")) / Decimal("2")


def test_compartment_coherence_unavailable_with_no_species_membership():
    model = _model(
        modularizations=(
            ModelModularization(
                modularization_id="mz1",
                name="no species",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA",),
            ),
        ),
        model_modules=(ModelModule(module_id="modA", name="Module A"),),
        module_memberships=(),
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.COMPARTMENT_COHERENCE)
    assert cs.available is False


def test_ec_class_coherence_scores_one_with_consistent_ec_class():
    network = _linear_network(
        reactions=(
            _reaction(
                reaction_id="r1", ec_number="1.1.1.1",
                participants=(
                    _participant(species_id="A"),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2", ec_number="1.2.3.4",
                participants=(
                    _participant(species_id="B"),
                    _participant(species_id="C", role=ParticipantRole.PRODUCT),
                ),
            ),
        )
    )
    model = _two_module_split(full_network=network)
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.EC_CLASS_COHERENCE)
    assert cs.available is True
    assert cs.raw_score == Decimal("1")


def test_ec_class_coherence_reflects_mixed_ec_classes():
    network = _linear_network(
        reactions=(
            _reaction(
                reaction_id="r1", ec_number="1.1.1.1",
                participants=(
                    _participant(species_id="A"),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2", ec_number="6.4.1.2",
                participants=(
                    _participant(species_id="B"),
                    _participant(species_id="C", role=ParticipantRole.PRODUCT),
                ),
            ),
        )
    )
    model = _model(
        full_network=network,
        modularizations=(
            ModelModularization(
                modularization_id="mz1",
                name="one module",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA",),
            ),
        ),
        model_modules=(ModelModule(module_id="modA", name="Module A"),),
        module_memberships=(
            ModuleMembership(
                membership_id="mem_r1", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r1",
            ),
            ModuleMembership(
                membership_id="mem_r2", modularization_id="mz1", module_id="modA",
                component_type=ModuleComponentType.REACTION, component_id="r2",
            ),
        ),
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.EC_CLASS_COHERENCE)
    assert cs.available is True
    assert cs.raw_score == Decimal("1") / Decimal("2")


def test_ec_class_coherence_unavailable_with_no_ec_numbers():
    model = _two_module_split()  # fixture reactions carry no ec_number
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.EC_CLASS_COHERENCE)
    assert cs.available is False
    assert "unavailable" not in cs.explanation.lower()  # explanation states a fact, not a verdict
    assert "EC number" in cs.explanation


def test_pathway_annotation_coherence_is_reserved_vocabulary_with_no_producer():
    """Corrective follow-up increment: PATHWAY_ANNOTATION_COHERENCE now names the genuine,
    still-unimplemented pathway/network-membership signal -- it must exist on the enum (so a
    future increment's own CriteriaWeights can already reference it), but must never appear
    among IMPLEMENTED_CRITERIA, and must never be silently scored as if EC_CLASS_COHERENCE."""
    assert ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE not in IMPLEMENTED_CRITERIA
    assert ModularizationCriterion.EC_CLASS_COHERENCE in IMPLEMENTED_CRITERIA

    model = _two_module_split()
    weights = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE, Decimal("1")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", weights)
    # No criterion_score entry is ever produced for a reserved, unimplemented criterion.
    assert all(
        cs.criterion is not ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE
        for cs in evaluation.criterion_scores
    )
    # Current, honest, pre-existing weight-handling consequence (not introduced by this
    # increment): a weight assigned to a criterion with no producer contributes to
    # CriteriaWeights' own normalization denominator but can never itself be scored, so no
    # criterion ever receives a weighted_contribution and overall_score is None -- never
    # silently fabricated or redistributed among the (zero, here) implemented criteria.
    assert evaluation.evaluated_weight_fraction == Decimal("0")
    assert evaluation.overall_score is None


# --- Weighted-score calculation / unavailable-criterion handling --------------------------------


def test_weighted_overall_score_matches_hand_computed_sum():
    model = _two_module_split()
    weights = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("3")),
            CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("1")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", weights)
    topo = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    sparsity = _criterion(evaluation, ModularizationCriterion.BOUNDARY_SPARSITY)
    expected = topo.weighted_contribution + sparsity.weighted_contribution
    assert evaluation.overall_score == expected
    assert evaluation.evaluated_weight_fraction == Decimal("1")


def test_unavailable_criterion_with_positive_weight_excluded_and_warned():
    model = _two_module_split()  # no EC numbers -> EC_CLASS_COHERENCE unavailable
    weights = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.EC_CLASS_COHERENCE, Decimal("1")),
            CriterionWeight(ModularizationCriterion.COMPARTMENT_COHERENCE, Decimal("1")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", weights)
    ec_class = _criterion(evaluation, ModularizationCriterion.EC_CLASS_COHERENCE)
    compartment = _criterion(evaluation, ModularizationCriterion.COMPARTMENT_COHERENCE)
    assert ec_class.available is False
    assert ec_class.weighted_contribution is None
    # Only compartment's own (renormalized-to-0.5) weight actually contributed.
    assert evaluation.evaluated_weight_fraction == Decimal("0.5")
    assert evaluation.overall_score == compartment.weighted_contribution
    assert any("EC_CLASS_COHERENCE" in w for w in evaluation.warnings)


def test_overall_score_is_none_when_no_weighted_criterion_is_available():
    model = _two_module_split()
    weights = _weights(
        weights=(
            CriterionWeight(ModularizationCriterion.EC_CLASS_COHERENCE, Decimal("1")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", weights)
    assert evaluation.overall_score is None
    assert evaluation.evaluated_weight_fraction == Decimal("0")


# --- Determinism / mutation --------------------------------------------------------------------


def test_evaluation_is_fully_deterministic():
    model = _two_module_split()
    weights = _weights()
    first = evaluate_modularization(model, "mz1", weights)
    second = evaluate_modularization(model, "mz1", weights)
    assert first == second


def test_evaluation_never_mutates_model_or_modularization():
    model = _two_module_split()
    before = copy.deepcopy(model)
    evaluate_modularization(model, "mz1", _weights())
    assert model == before


# --- Multi-weight-vector / multi-modularization comparison --------------------------------------


def test_same_modularization_scored_under_multiple_weight_vectors():
    model = _two_module_split()
    topo_only = _weights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),)
    )
    sparsity_only = _weights(
        weights=(CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("1")),)
    )
    results = evaluate_modularization_under_weights(model, "mz1", (topo_only, sparsity_only))
    assert len(results) == 2
    assert results[0].weights is topo_only
    assert results[1].weights is sparsity_only
    assert results[0].overall_score != results[1].overall_score


def test_evaluation_id_differs_across_distinct_weight_vectors_for_the_same_modularization():
    model = _two_module_split()
    w1 = _weights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),)
    )
    w2 = _weights(
        weights=(CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("1")),)
    )
    e1 = evaluate_modularization(model, "mz1", w1)
    e2 = evaluate_modularization(model, "mz1", w2)
    assert e1.evaluation_id != e2.evaluation_id


def test_compare_modularizations_with_different_module_counts():
    one_modularization = ModelModularization(
        modularization_id="one", name="one module", method=ModularizationMethod.USER_DEFINED,
        module_ids=("modAll",),
    )
    one_module = (ModelModule(module_id="modAll", name="Everything"),)
    one_memberships = (
        ModuleMembership(
            membership_id="one_mem_r1", modularization_id="one", module_id="modAll",
            component_type=ModuleComponentType.REACTION, component_id="r1",
        ),
        ModuleMembership(
            membership_id="one_mem_r2", modularization_id="one", module_id="modAll",
            component_type=ModuleComponentType.REACTION, component_id="r2",
        ),
    )
    base = _two_module_split()
    two_modules = _two_module_split(
        modularizations=(one_modularization, *base.modularizations),
        model_modules=one_module + base.model_modules,
        module_memberships=one_memberships + base.module_memberships,
        module_ports=base.module_ports,
    )
    results = compare_modularizations(two_modules, ("one", "mz1"), _weights())
    assert [r.modularization_id for r in results] == ["one", "mz1"]
    assert results[0].module_count == 1
    assert results[1].module_count == 2
    # Neither comparison function picks a winner -- both evaluations are simply returned.
    assert {r.modularization_id for r in results} == {"one", "mz1"}


def test_evaluate_modularization_rejects_unknown_modularization_id():
    model = _two_module_split()
    with pytest.raises(ModuleEvaluationReferenceError):
        evaluate_modularization(model, "does-not-exist", _weights())


def test_evaluate_modularization_under_weights_requires_non_empty_tuple():
    model = _two_module_split()
    with pytest.raises(ModuleEvaluationReferenceError):
        evaluate_modularization_under_weights(model, "mz1", ())


def test_compare_modularizations_requires_non_empty_tuple():
    model = _two_module_split()
    with pytest.raises(ModuleEvaluationReferenceError):
        compare_modularizations(model, (), _weights())


# --- GENERATED/IMPORTED symmetry -----------------------------------------------------------------


def _imported_linear_model():
    text = """
    model m
      compartment c1 = 1.0;
      species A in c1 = 10.0;
      species B in c1 = 0.0;
      species C in c1 = 0.0;
      r1: A => B; k1 * A;
      r2: B => C; k2 * B;
      k1 = 0.5;
      k2 = 0.5;
    end
    """
    return import_antimony(text)


def test_evaluation_works_identically_for_generated_and_imported_models():
    generated = _two_module_split()
    imported = replace(
        _imported_linear_model(),
        modularizations=generated.modularizations,
        model_modules=generated.model_modules,
        module_memberships=generated.module_memberships,
        module_ports=generated.module_ports,
    )
    weights = _weights()
    generated_eval = evaluate_modularization(generated, "mz1", weights)
    imported_eval = evaluate_modularization(imported, "mz1", weights)

    for criterion in (
        ModularizationCriterion.TOPOLOGICAL_SEPARATION,
        ModularizationCriterion.BOUNDARY_SPARSITY,
        ModularizationCriterion.COMPARTMENT_COHERENCE,
    ):
        g = _criterion(generated_eval, criterion)
        i = _criterion(imported_eval, criterion)
        assert g.available == i.available
        assert g.raw_score == i.raw_score
    assert generated_eval.overall_score == imported_eval.overall_score


# --- No downstream contract regression -----------------------------------------------------------


def test_module_evaluation_package_does_not_alter_model_specification_shape():
    """This package only ever reads an already-assembled ModelSpecification -- it stores
    nothing new on it, so its mere existence/use cannot regress the downstream handoff."""
    model = _two_module_split()
    evaluate_modularization(model, "mz1", _weights())
    field_names = {f.name for f in __import__("dataclasses").fields(ModelSpecification)}
    assert "modularization_evaluations" not in field_names
    assert "criteria_weights" not in field_names


# --- Topology Hub/Currency Component Filtering increment -----------------------------------------
#
# modA = {r1, r3} (r1: A -> B; r3: B -> E -- a real, in-module pathway edge via B).
# modB = {r2} (r2: X -> Y). r1 and r2 additionally both consume ATP/produce ADP -- their *only*
# shared species, a purely currency-driven cut edge that artificially dilutes the raw score.


def _currency_species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "ATP", "name": "ATP", "compartment_id": "c1"} | overrides
    return SpeciesSpecification(**merged)


def _currency_network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "n1",
        "compartments": (_compartment(),),
        "species": (
            _species(species_id="A"),
            _species(species_id="B"),
            _species(species_id="E", name="E"),
            _species(species_id="X", name="X"),
            _species(species_id="Y", name="Y"),
            _currency_species(species_id="ATP", name="ATP"),
            _currency_species(species_id="ADP", name="ADP"),
        ),
        "reactions": (
            _reaction(
                reaction_id="r1",
                participants=(
                    _participant(species_id="A", role=ParticipantRole.REACTANT),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                    _participant(species_id="ATP", role=ParticipantRole.REACTANT),
                    _participant(species_id="ADP", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2",
                participants=(
                    _participant(species_id="X", role=ParticipantRole.REACTANT),
                    _participant(species_id="Y", role=ParticipantRole.PRODUCT),
                    _participant(species_id="ATP", role=ParticipantRole.REACTANT),
                    _participant(species_id="ADP", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r3",
                participants=(
                    _participant(species_id="B", role=ParticipantRole.REACTANT),
                    _participant(species_id="E", role=ParticipantRole.PRODUCT),
                ),
            ),
        ),
    } | overrides
    return FullNetwork(**merged)


def _currency_model(**overrides) -> ModelSpecification:
    modularization = ModelModularization(
        modularization_id="mz1",
        name="currency test split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
    )
    modules = (
        ModelModule(module_id="modA", name="Module A"),
        ModelModule(module_id="modB", name="Module B"),
    )
    memberships = (
        ModuleMembership(
            membership_id="mem_r1", modularization_id="mz1", module_id="modA",
            component_type=ModuleComponentType.REACTION, component_id="r1",
        ),
        ModuleMembership(
            membership_id="mem_r3", modularization_id="mz1", module_id="modA",
            component_type=ModuleComponentType.REACTION, component_id="r3",
        ),
        ModuleMembership(
            membership_id="mem_r2", modularization_id="mz1", module_id="modB",
            component_type=ModuleComponentType.REACTION, component_id="r2",
        ),
    )
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _currency_network(),
        "kinetic_laws": (),
        "parameters": (),
        "modularizations": (modularization,),
        "model_modules": modules,
        "module_memberships": memberships,
    } | overrides
    return ModelSpecification(**merged)


def test_raw_topology_score_is_diluted_by_pure_currency_sharing():
    """Without filtering, r1<->r2's purely-ATP-driven edge counts exactly as much as
    r1<->r3's real, in-module pathway edge -- raw_score = 1 internal / 2 total = 0.5."""
    model = _currency_model()
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.detail.raw_topology_score == Decimal("0.5")


def test_atp_like_currency_metabolite_excluded_by_default_recovers_filtered_score():
    """With default curated filtering, the ATP/ADP-only edge drops to weight 0 entirely --
    filtered_score = 1 internal / 1 total = 1.0, recovering the real pathway structure raw
    scoring alone could not see."""
    model = _currency_model()
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.available is True
    assert cs.raw_score == Decimal("1")  # the main, filtered score used for weighting
    assert cs.detail.filtered_topology_score == Decimal("1")
    filtered_species = {f.species_id for f in cs.detail.filters}
    assert filtered_species == {"ATP", "ADP"}
    for f in cs.detail.filters:
        assert f.role is TopologyRole.UNIVERSAL_CURRENCY
        assert f.weight == Decimal("0")
        assert f.source == "curated_default"


def test_cofactor_down_weighted_rather_than_hard_excluded():
    model = _currency_model(
        full_network=_currency_network(
            species=(
                _species(species_id="A"),
                _species(species_id="B"),
                _species(species_id="E", name="E"),
                _species(species_id="X", name="X"),
                _species(species_id="Y", name="Y"),
                _currency_species(species_id="ATP", name="NADH"),
                _currency_species(species_id="ADP", name="NAD+"),
            )
        )
    )
    evaluation = evaluate_modularization(model, "mz1", _weights())
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    # weight = 0.3 (DEFAULT_TOPOLOGY_ROLE_WEIGHT[COFACTOR]): filtered = 1 / (1 + 0.3)
    assert cs.detail.filtered_topology_score == Decimal("1") / (Decimal("1") + Decimal("0.3"))
    for f in cs.detail.filters:
        assert f.role is TopologyRole.COFACTOR
        assert f.weight == Decimal("0.3")


def test_generic_adaptor_down_weighted_only_via_explicit_override():
    """GENERIC_ADAPTOR (e.g. 14-3-3) is never auto-detected by name -- only an explicit
    override assigns it (task instructions §1/§5)."""
    model = _currency_model(
        full_network=_currency_network(
            species=(
                _species(species_id="A"),
                _species(species_id="B"),
                _species(species_id="E", name="E"),
                _species(species_id="X", name="X"),
                _species(species_id="Y", name="Y"),
                _currency_species(species_id="ATP", name="14-3-3"),
                _currency_species(species_id="ADP", name="14-3-3-complex"),
            )
        )
    )
    # Without an override, an unrecognized name is plain NORMAL -- no filtering at all.
    unfiltered = evaluate_modularization(model, "mz1", _weights())
    cs_unfiltered = _criterion(unfiltered, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs_unfiltered.detail.filtered_topology_score == Decimal("0.5")
    assert cs_unfiltered.detail.filters == ()

    # Both species that make up the shared complex must be overridden together -- an edge's
    # own weight is the *max* over every species it shares, so overriding only one half of a
    # two-species-shared edge is dominated by whichever half is left at its own, higher,
    # unrecognized-name NORMAL/weight-1 default.
    policy = TopologyFilteringPolicy(
        overrides=(
            TopologyRoleOverride("ATP", TopologyRole.GENERIC_ADAPTOR),
            TopologyRoleOverride("ADP", TopologyRole.GENERIC_ADAPTOR),
        )
    )
    overridden = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    cs = _criterion(overridden, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.detail.filtered_topology_score == Decimal("1") / (Decimal("1") + Decimal("0.3"))
    assert {f.species_id for f in cs.detail.filters} == {"ATP", "ADP"}
    for f in cs.detail.filters:
        assert f.role is TopologyRole.GENERIC_ADAPTOR
        assert f.weight == Decimal("0.3")
        assert f.source == "override"


def test_user_override_can_restore_normal_weight_for_a_curated_currency_species():
    """Context sensitivity (task §5): a caller may declare ATP/ADP mechanistically central
    (e.g. an ATP-transport-focused model) and override their weight back to full
    contribution -- fully canceling the default filtering, recovering the identical score
    the *unfiltered* (raw) computation would have reported for this network."""
    model = _currency_model()
    policy = TopologyFilteringPolicy(
        overrides=(
            TopologyRoleOverride("ATP", TopologyRole.NORMAL, weight=Decimal("1")),
            TopologyRoleOverride("ADP", TopologyRole.NORMAL, weight=Decimal("1")),
        )
    )
    evaluation = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert cs.detail.filtered_topology_score == cs.detail.raw_topology_score == Decimal("0.5")
    for f in cs.detail.filters:
        assert f.role is TopologyRole.NORMAL
        assert f.weight == Decimal("1")
        assert f.source == "override"


def test_user_override_can_fully_exclude_a_component_the_default_policy_would_not():
    model = _currency_model()
    policy = TopologyFilteringPolicy(
        overrides=(TopologyRoleOverride("B", TopologyRole.USER_EXCLUDED),)
    )
    evaluation = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    # B (r1<->r3's only real connection) is now excluded too -- only the ATP/ADP-driven
    # r1<->r2 edge remains, and that is itself filtered to weight 0 by default -> unavailable.
    assert cs.available is False
    assert cs.detail.filtered_topology_score is None
    assert cs.detail.raw_topology_score == Decimal("0.5")


def test_high_degree_hub_flagged_but_not_auto_excluded():
    """Degree-based hub detection only ever flags a candidate for disclosure -- it never
    changes a role or a weight on its own (task instructions §3)."""
    hub_network = _currency_network(
        species=(
            _species(species_id="A"),
            _species(species_id="B"),
            _species(species_id="E", name="E"),
            _species(species_id="X", name="X"),
            _species(species_id="Y", name="Y"),
            _species(species_id="ATP", name="HubX"),
            _currency_species(species_id="ADP", name="ADP"),
        ),
        reactions=(
            _reaction(
                reaction_id="r1",
                participants=(
                    _participant(species_id="A", role=ParticipantRole.REACTANT),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                    _participant(species_id="ATP", role=ParticipantRole.REACTANT),
                ),
            ),
            _reaction(
                reaction_id="r2",
                participants=(
                    _participant(species_id="X", role=ParticipantRole.REACTANT),
                    _participant(species_id="Y", role=ParticipantRole.PRODUCT),
                    _participant(species_id="ATP", role=ParticipantRole.REACTANT),
                ),
            ),
            _reaction(
                reaction_id="r3",
                participants=(
                    _participant(species_id="B", role=ParticipantRole.REACTANT),
                    _participant(species_id="E", role=ParticipantRole.PRODUCT),
                    _participant(species_id="ATP", role=ParticipantRole.REACTANT),
                ),
            ),
        ),
    )
    model = _currency_model(full_network=hub_network)
    policy = TopologyFilteringPolicy(hub_degree_threshold=3)
    evaluation = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    cs = _criterion(evaluation, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    # species_id "ATP" here is deliberately named "HubX" (unrecognized by the curated
    # name lists) -- only its *degree*, not its name, should get it flagged.
    assert "ATP" in cs.detail.hub_candidate_species_ids
    # Flagged, but never auto-filtered: no entry in `filters` for it, full weight still applied.
    assert all(f.species_id != "ATP" for f in cs.detail.filters)
    assert cs.detail.filtered_topology_score == cs.detail.raw_topology_score


def test_topology_filtering_is_fully_deterministic():
    model = _currency_model()
    policy = TopologyFilteringPolicy(
        overrides=(TopologyRoleOverride("B", TopologyRole.NORMAL, weight=Decimal("1")),)
    )
    first = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    second = evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    assert first == second


def test_topology_filtering_never_mutates_model():
    model = _currency_model()
    before = copy.deepcopy(model)
    policy = TopologyFilteringPolicy(
        overrides=(TopologyRoleOverride("ATP", TopologyRole.NORMAL, weight=Decimal("1")),)
    )
    evaluate_modularization(model, "mz1", _weights(), topology_filtering=policy)
    assert model == before


def test_topology_filtering_generated_imported_symmetry():
    generated = _currency_model()
    text = """
    model m
      compartment c1 = 1.0;
      species A in c1 = 1.0;
      species B in c1 = 0.0;
      species E in c1 = 0.0;
      species X in c1 = 1.0;
      species Y in c1 = 0.0;
      species ATP in c1 = 1.0;
      species ADP in c1 = 0.0;
      r1: A + ATP => B + ADP; k1 * A * ATP;
      r2: X + ATP => Y + ADP; k2 * X * ATP;
      r3: B => E; k3 * B;
      k1 = 0.5;
      k2 = 0.5;
      k3 = 0.5;
    end
    """
    imported = replace(
        import_antimony(text),
        modularizations=generated.modularizations,
        model_modules=generated.model_modules,
        module_memberships=generated.module_memberships,
    )
    weights = _weights()
    generated_eval = evaluate_modularization(generated, "mz1", weights)
    imported_eval = evaluate_modularization(imported, "mz1", weights)
    g = _criterion(generated_eval, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    i = _criterion(imported_eval, ModularizationCriterion.TOPOLOGICAL_SEPARATION)
    assert g.detail.raw_topology_score == i.detail.raw_topology_score
    assert g.detail.filtered_topology_score == i.detail.filtered_topology_score
    assert {f.species_id for f in g.detail.filters} == {f.species_id for f in i.detail.filters}
