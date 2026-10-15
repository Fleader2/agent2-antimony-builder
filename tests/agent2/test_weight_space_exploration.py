"""Tests for Weight-Space Exploration and Stable Boundary Discovery:
``app.agent2.weight_space_exploration``.

Builds a 4-reaction chain (A -> B -> C -> D -> E, mirroring
``tests/agent2/test_module_evaluation.py``'s own convention) with two deliberately
conflicting candidate modularizations -- one that respects the network's own topology, one
that respects its reactions' curated EC-number classes instead -- so each test's own expected
score/stability outcome can be hand-computed exactly.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony_import import import_antimony
from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
from app.agent2.module_evaluation.criteria import IMPLEMENTED_CRITERIA
from app.agent2.module_evaluation.types import (
    TopologyFilteringPolicy,
    TopologyRole,
    TopologyRoleOverride,
)
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
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)
from app.agent2.weight_space_exploration import (
    HighScoringSolutionPolicy,
    HighScoringSolutionSelectionMethod,
    WeightGridSpec,
    WeightRange,
    WeightSpaceExplorationReferenceError,
    explore_weight_space,
    generate_weight_vectors,
    uniform_weight_grid,
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


def _chain_network(**overrides) -> FullNetwork:
    """A -> B -> C -> D -> E. r1/r3 share EC class "1"; r2/r4 share EC class "6" -- a
    deliberately cross-cutting pattern against the chain's own topology."""
    merged = {
        "network_id": "n1",
        "name": "n1",
        "compartments": (_compartment(),),
        "species": (
            _species(species_id="A"),
            _species(species_id="B"),
            _species(species_id="C"),
            _species(species_id="D"),
            _species(species_id="E"),
        ),
        "reactions": (
            _reaction(
                reaction_id="r1",
                ec_number="1.1.1.1",
                participants=(
                    _participant(species_id="A", role=ParticipantRole.REACTANT),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2",
                ec_number="6.1.1.1",
                participants=(
                    _participant(species_id="B", role=ParticipantRole.REACTANT),
                    _participant(species_id="C", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r3",
                ec_number="1.2.2.2",
                participants=(
                    _participant(species_id="C", role=ParticipantRole.REACTANT),
                    _participant(species_id="D", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r4",
                ec_number="6.2.2.2",
                participants=(
                    _participant(species_id="D", role=ParticipantRole.REACTANT),
                    _participant(species_id="E", role=ParticipantRole.PRODUCT),
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


def _membership(modularization_id: str, module_id: str, reaction_id: str) -> ModuleMembership:
    return ModuleMembership(
        membership_id=f"mem_{modularization_id}_{module_id}_{reaction_id}",
        modularization_id=modularization_id,
        module_id=module_id,
        component_type=ModuleComponentType.REACTION,
        component_id=reaction_id,
    )


def _two_candidate_model(**overrides) -> ModelSpecification:
    """Two conflicting candidate modularizations of the identical chain network:

    * "topo": modA={r1, r2}, modB={r3, r4} -- respects network adjacency
      (TOPOLOGICAL_SEPARATION = 2/3), splits EC classes evenly (EC_CLASS_COHERENCE = 0.5).
    * "ec": modA={r1, r3}, modB={r2, r4} -- respects EC classes perfectly
      (EC_CLASS_COHERENCE = 1.0), cuts every network-adjacency edge (TOPOLOGICAL_SEPARATION
      = 0.0).

    r2<->r3 is cut by *both* (stable cut); r1<->r2 and r3<->r4 are cut by "ec" but internal
    to "topo" (disagreement -- ambiguous whenever both appear in the high-scoring set).
    """
    topo = ModelModularization(
        modularization_id="topo",
        name="topological split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("topoA", "topoB"),
    )
    ec = ModelModularization(
        modularization_id="ec",
        name="EC-class split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("ecA", "ecB"),
    )
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _chain_network(),
        "kinetic_laws": (),
        "parameters": (),
        "modularizations": (topo, ec),
        "model_modules": (
            ModelModule(module_id="topoA", name="Topo A"),
            ModelModule(module_id="topoB", name="Topo B"),
            ModelModule(module_id="ecA", name="EC A"),
            ModelModule(module_id="ecB", name="EC B"),
        ),
        "module_memberships": (
            _membership("topo", "topoA", "r1"),
            _membership("topo", "topoA", "r2"),
            _membership("topo", "topoB", "r3"),
            _membership("topo", "topoB", "r4"),
            _membership("ec", "ecA", "r1"),
            _membership("ec", "ecA", "r3"),
            _membership("ec", "ecB", "r2"),
            _membership("ec", "ecB", "r4"),
        ),
    } | overrides
    return ModelSpecification(**merged)


def _single_weight(criterion: ModularizationCriterion, value: str = "1") -> CriteriaWeights:
    return CriteriaWeights(
        weights=(CriterionWeight(criterion, Decimal(value)),), policy_version="test-v1"
    )


def _top_n(n: int) -> HighScoringSolutionPolicy:
    return HighScoringSolutionPolicy(
        HighScoringSolutionSelectionMethod.TOP_N, Decimal(n), policy_version="test-v1"
    )


# --- Deterministic weight-grid generation ---------------------------------------------------


def test_uniform_weight_grid_produces_expected_combination_count():
    spec = uniform_weight_grid(IMPLEMENTED_CRITERIA, steps=3, policy_version="test-v1")
    vectors = generate_weight_vectors(spec)
    assert len(vectors) == 3 ** len(IMPLEMENTED_CRITERIA) - 1  # all-zero excluded


def test_weight_grid_generation_is_deterministic():
    spec = uniform_weight_grid(IMPLEMENTED_CRITERIA, steps=3, policy_version="test-v1")
    first = generate_weight_vectors(spec)
    second = generate_weight_vectors(spec)
    assert first == second


def test_weight_grid_max_combinations_caps_deterministically():
    spec = uniform_weight_grid(
        IMPLEMENTED_CRITERIA, steps=3, max_combinations=10, policy_version="v1"
    )
    vectors = generate_weight_vectors(spec)
    assert len(vectors) == 10
    assert generate_weight_vectors(spec) == vectors


def test_weight_grid_supports_explicit_user_supplied_ranges():
    spec = WeightGridSpec(
        ranges=(
            WeightRange(
                ModularizationCriterion.TOPOLOGICAL_SEPARATION,
                (Decimal("0"), Decimal("1")),
            ),
            WeightRange(ModularizationCriterion.EC_CLASS_COHERENCE, (Decimal("1"),)),
        ),
        policy_version="v1",
    )
    vectors = generate_weight_vectors(spec)
    assert len(vectors) == 2
    for v in vectors:
        assert v.raw_weight(ModularizationCriterion.EC_CLASS_COHERENCE) == Decimal("1")


def test_weight_grid_rejects_all_zero_only_ranges():
    spec = WeightGridSpec(
        ranges=(WeightRange(ModularizationCriterion.TOPOLOGICAL_SEPARATION, (Decimal("0"),)),),
        policy_version="v1",
    )
    with pytest.raises(WeightSpaceExplorationReferenceError):
        generate_weight_vectors(spec)


# --- Different weight regimes favoring different solutions ---------------------------------


def test_topology_weighted_exploration_favors_the_topological_split():
    model = _two_candidate_model()
    weights = (_single_weight(ModularizationCriterion.TOPOLOGICAL_SEPARATION),)
    result = explore_weight_space(model, ("topo", "ec"), weights, _top_n(1), policy_version="v1")
    (winner,) = result.high_scoring_evaluation_ids
    (evaluation,) = [e for e in result.evaluations if e.evaluation_id == winner]
    assert evaluation.modularization_id == "topo"


def test_ec_weighted_exploration_favors_the_ec_class_split():
    model = _two_candidate_model()
    weights = (_single_weight(ModularizationCriterion.EC_CLASS_COHERENCE),)
    result = explore_weight_space(model, ("topo", "ec"), weights, _top_n(1), policy_version="v1")
    (winner,) = result.high_scoring_evaluation_ids
    (evaluation,) = [e for e in result.evaluations if e.evaluation_id == winner]
    assert evaluation.modularization_id == "ec"


# --- Stable boundary detected across many weight vectors; unstable reported correctly -------


def _mixed_weight_result(policy: HighScoringSolutionPolicy):
    model = _two_candidate_model()
    weights = (
        CriteriaWeights(
            weights=(
                CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
                CriterionWeight(ModularizationCriterion.EC_CLASS_COHERENCE, Decimal("1")),
            ),
            policy_version="test-v1",
        ),
    )
    return explore_weight_space(model, ("topo", "ec"), weights, policy, policy_version="v1")


def test_boundary_cut_by_every_candidate_is_reported_fully_stable():
    # Both "topo" and "ec" score close enough (0.583 vs 0.5) to both be selected under a
    # generous within-delta-of-best policy.
    result = _mixed_weight_result(
        HighScoringSolutionPolicy(
            HighScoringSolutionSelectionMethod.WITHIN_DELTA_OF_BEST,
            Decimal("0.1"),
            policy_version="v1",
        )
    )
    assert len(result.high_scoring_evaluation_ids) == 2
    (r2_r3,) = [
        b for b in result.boundary_stability if {b.reaction_id_a, b.reaction_id_b} == {"r2", "r3"}
    ]
    assert r2_r3.cut_frequency == Decimal("1")
    assert r2_r3 not in result.ambiguous_boundaries


def test_boundary_disagreed_on_by_candidates_is_reported_ambiguous():
    result = _mixed_weight_result(
        HighScoringSolutionPolicy(
            HighScoringSolutionSelectionMethod.WITHIN_DELTA_OF_BEST,
            Decimal("0.1"),
            policy_version="v1",
        )
    )
    assert len(result.high_scoring_evaluation_ids) == 2
    (r1_r2,) = [
        b for b in result.boundary_stability if {b.reaction_id_a, b.reaction_id_b} == {"r1", "r2"}
    ]
    assert r1_r2.cut_frequency == Decimal("0.5")
    assert r1_r2 in result.ambiguous_boundaries
    (r3_r4,) = [
        b for b in result.boundary_stability if {b.reaction_id_a, b.reaction_id_b} == {"r3", "r4"}
    ]
    assert r3_r4.cut_frequency == Decimal("0.5")
    assert r3_r4 in result.ambiguous_boundaries


def test_single_candidate_boundary_is_always_fully_resolved_never_ambiguous():
    """A single, fixed modularization's own boundary structure never varies across weight
    vectors -- every cut_frequency is always exactly 0 or 1, never inside the ambiguous band,
    regardless of how many distinct weight vectors are explored."""
    model = _two_candidate_model()
    spec = uniform_weight_grid(IMPLEMENTED_CRITERIA, steps=3, policy_version="v1")
    weights = generate_weight_vectors(spec)
    result = explore_weight_space(model, ("topo",), weights, _top_n(5), policy_version="v1")
    assert result.ambiguous_boundaries == ()
    for b in result.boundary_stability:
        assert b.cut_frequency in (Decimal("0"), Decimal("1"))


# --- Comparison across different module counts ----------------------------------------------


def test_module_count_is_preserved_separately_per_candidate():
    singleton = ModelModularization(
        modularization_id="singleton",
        name="every reaction its own module",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("s1", "s2", "s3", "s4"),
    )
    model = _two_candidate_model(
        modularizations=(
            *_two_candidate_model().modularizations,
            singleton,
        ),
        model_modules=(
            *_two_candidate_model().model_modules,
            ModelModule(module_id="s1", name="s1"),
            ModelModule(module_id="s2", name="s2"),
            ModelModule(module_id="s3", name="s3"),
            ModelModule(module_id="s4", name="s4"),
        ),
        module_memberships=(
            *_two_candidate_model().module_memberships,
            _membership("singleton", "s1", "r1"),
            _membership("singleton", "s2", "r2"),
            _membership("singleton", "s3", "r3"),
            _membership("singleton", "s4", "r4"),
        ),
    )
    weights = (_single_weight(ModularizationCriterion.TOPOLOGICAL_SEPARATION),)
    result = explore_weight_space(
        model, ("topo", "ec", "singleton"), weights, _top_n(10), policy_version="v1"
    )
    module_counts = {e.modularization_id: e.module_count for e in result.evaluations}
    assert module_counts == {"topo": 2, "ec": 2, "singleton": 4}
    reported_counts = {g.module_count for g in result.by_module_count}
    assert reported_counts == {2, 4}
    # Never assumes one module count is preferred -- no field ranks module counts against
    # each other; both groups are simply both present.
    assert len(result.by_module_count) == 2


# --- Filtered topology integration ------------------------------------------------------------


def test_topology_filtering_parameter_changes_exploration_scores():
    # "Linker" is not on either curated name list -- it is plain NORMAL (full weight) unless
    # an explicit override says otherwise, so it cleanly isolates the effect of the
    # `topology_filtering` parameter itself from the pre-existing curated-name defaults.
    network = _chain_network(
        species=(
            _species(species_id="A"),
            _species(species_id="B"),
            _species(species_id="C"),
            _species(species_id="D"),
            _species(species_id="E"),
            _species(species_id="Linker", name="Linker"),
        ),
        reactions=(
            *_chain_network().reactions[:-1],
            ReactionSpecification(
                reaction_id="r4",
                name="r4",
                ec_number="6.2.2.2",
                participants=(
                    _participant(species_id="D", role=ParticipantRole.REACTANT),
                    _participant(species_id="E", role=ParticipantRole.PRODUCT),
                    _participant(species_id="Linker", role=ParticipantRole.REACTANT),
                ),
            ),
        ),
    )
    # Add a purely-Linker-driven adjacency between r1 and r4 (otherwise non-adjacent).
    network = replace(
        network,
        reactions=(
            replace(
                network.reactions[0],
                participants=(
                    *network.reactions[0].participants,
                    _participant(species_id="Linker"),
                ),
            ),
            *network.reactions[1:],
        ),
    )
    model = _two_candidate_model(full_network=network)
    weights = (_single_weight(ModularizationCriterion.TOPOLOGICAL_SEPARATION),)

    unfiltered = explore_weight_space(model, ("topo",), weights, _top_n(1), policy_version="v1")
    filtered = explore_weight_space(
        model,
        ("topo",),
        weights,
        _top_n(1),
        topology_filtering=TopologyFilteringPolicy(
            overrides=(TopologyRoleOverride("Linker", TopologyRole.UNIVERSAL_CURRENCY),)
        ),
        policy_version="v1",
    )
    unfiltered_score = unfiltered.evaluations[0].overall_score
    filtered_score = filtered.evaluations[0].overall_score
    assert filtered_score != unfiltered_score
    # The spurious Linker-only edge (r1<->r4, cut by "topo") is counted at full weight
    # without filtering, diluting the score; filtering removes it entirely, recovering the
    # cleaner 2/3 structure.
    assert unfiltered_score == Decimal("0.5")
    assert filtered_score == Decimal("2") / Decimal("3")


# --- Unavailable-criterion handling ----------------------------------------------------------


def test_weight_vector_naming_only_an_unavailable_criterion_yields_empty_high_scoring_set():
    network = _chain_network(
        reactions=tuple(replace(r, ec_number=None) for r in _chain_network().reactions)
    )
    model = _two_candidate_model(full_network=network)
    weights = (_single_weight(ModularizationCriterion.EC_CLASS_COHERENCE),)
    result = explore_weight_space(model, ("topo", "ec"), weights, _top_n(5), policy_version="v1")
    assert result.high_scoring_evaluation_ids == ()
    assert result.boundary_stability == ()
    assert result.co_membership_stability == ()
    assert any("empty" in w.lower() for w in result.warnings)
    assert all(e.overall_score is None for e in result.evaluations)


# --- No mutation --------------------------------------------------------------------------------


def test_explore_weight_space_never_mutates_model():
    model = _two_candidate_model()
    before = copy.deepcopy(model)
    spec = uniform_weight_grid(IMPLEMENTED_CRITERIA, steps=2, policy_version="v1")
    weights = generate_weight_vectors(spec)
    explore_weight_space(model, ("topo", "ec"), weights, _top_n(3), policy_version="v1")
    assert model == before


def test_explore_weight_space_is_deterministic():
    model = _two_candidate_model()
    spec = uniform_weight_grid(IMPLEMENTED_CRITERIA, steps=2, policy_version="v1")
    weights = generate_weight_vectors(spec)
    policy = _top_n(3)
    first = explore_weight_space(model, ("topo", "ec"), weights, policy, policy_version="v1")
    second = explore_weight_space(model, ("topo", "ec"), weights, policy, policy_version="v1")
    assert first == second


# --- Reference errors ----------------------------------------------------------------------


def test_explore_weight_space_rejects_empty_modularization_ids():
    model = _two_candidate_model()
    weights = (_single_weight(ModularizationCriterion.TOPOLOGICAL_SEPARATION),)
    with pytest.raises(WeightSpaceExplorationReferenceError):
        explore_weight_space(model, (), weights, _top_n(1))


def test_explore_weight_space_rejects_empty_weight_vectors():
    model = _two_candidate_model()
    with pytest.raises(WeightSpaceExplorationReferenceError):
        explore_weight_space(model, ("topo",), (), _top_n(1))


# --- GENERATED/IMPORTED symmetry -------------------------------------------------------------


def _imported_chain_model():
    text = """
    model m
      compartment c1 = 1.0;
      species A in c1 = 1.0;
      species B in c1 = 0.0;
      species C in c1 = 0.0;
      species D in c1 = 0.0;
      species E in c1 = 0.0;
      r1: A => B; k1 * A;
      r2: B => C; k2 * B;
      r3: C => D; k3 * C;
      r4: D => E; k4 * D;
      k1 = 0.5;
      k2 = 0.5;
      k3 = 0.5;
      k4 = 0.5;
    end
    """
    return import_antimony(text)


def test_exploration_works_identically_for_generated_and_imported_models():
    generated = _two_candidate_model()
    imported = replace(
        _imported_chain_model(),
        modularizations=generated.modularizations,
        model_modules=generated.model_modules,
        module_memberships=generated.module_memberships,
    )
    # EC_CLASS_COHERENCE is deliberately excluded from this grid: curated ec_number is an
    # Agent-1-sourced annotation with no Antimony-text equivalent, so it is genuinely,
    # expectedly unavailable for any Antimony-imported model (see docs/27 §5/§4) -- that is
    # not an asymmetry explore_weight_space introduces, and comparing scores that depend on
    # it would conflate "no EC data in this Antimony source" with a real behavioral
    # difference. The three criteria that are equally available for either origin are
    # exercised fully here instead.
    criteria = tuple(
        c for c in IMPLEMENTED_CRITERIA if c is not ModularizationCriterion.EC_CLASS_COHERENCE
    )
    spec = uniform_weight_grid(criteria, steps=2, policy_version="v1")
    weights = generate_weight_vectors(spec)
    policy = _top_n(3)

    generated_result = explore_weight_space(
        generated, ("topo", "ec"), weights, policy, policy_version="v1"
    )
    imported_result = explore_weight_space(
        imported, ("topo", "ec"), weights, policy, policy_version="v1"
    )

    generated_scores = sorted(
        e.overall_score for e in generated_result.evaluations if e.overall_score is not None
    )
    imported_scores = sorted(
        e.overall_score for e in imported_result.evaluations if e.overall_score is not None
    )
    assert generated_scores == imported_scores
    assert len(generated_result.boundary_stability) == len(imported_result.boundary_stability)

    def _signature(stabilities):
        return {(b.reaction_id_a, b.reaction_id_b, b.cut_frequency) for b in stabilities}

    assert _signature(generated_result.boundary_stability) == _signature(
        imported_result.boundary_stability
    )
