"""Tests for Candidate Modularization Search: ``app.agent2.modularization_search``.

Builds a 4-reaction chain (A -> B -> C -> D -> E, mirroring ``tests/agent2
.test_weight_space_exploration.py``'s own convention) with a seed modularization
modA={r1,r2}/modB={r3,r4}, so each proposal operator's own expected output can be hand-verified
exactly.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.agent2.antimony_import import import_antimony
from app.agent2.modularization_search import (
    BoundaryFixedState,
    FixedBoundary,
    ProposalOperation,
    SearchConstraints,
    SearchPolicy,
    extract_bundle,
    module_content_key,
    propose_add_boundary,
    propose_merge_modules,
    propose_move_reaction,
    propose_remove_boundary,
    propose_split_module,
    propose_vary_module_count,
    search_candidate_modularizations,
)
from app.agent2.modularization_search.assembly import canonicalize_bundle
from app.agent2.module_calibration.types import ModuleCalibrationEvaluation, ModuleCalibrationStatus
from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
from app.agent2.module_evaluation.types import (
    TopologyFilteringPolicy,
    TopologyRole,
    TopologyRoleOverride,
)
from app.agent2.types import (
    CompartmentSourceScope,
    CompartmentSpecification,
    FullNetwork,
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ModulePortDirection,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures --------------------------------------------------------------------------------


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
            _reaction(
                reaction_id="r3",
                participants=(
                    _participant(species_id="C", role=ParticipantRole.REACTANT),
                    _participant(species_id="D", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r4",
                participants=(
                    _participant(species_id="D", role=ParticipantRole.REACTANT),
                    _participant(species_id="E", role=ParticipantRole.PRODUCT),
                ),
            ),
        ),
    } | overrides
    return FullNetwork(**merged)


def _membership(
    module_id: str, reaction_id: str, *, modularization_id: str = "seed"
) -> ModuleMembership:
    return ModuleMembership(
        membership_id=f"mem_{modularization_id}_{module_id}_{reaction_id}",
        modularization_id=modularization_id,
        module_id=module_id,
        component_type=ModuleComponentType.REACTION,
        component_id=reaction_id,
    )


def _seed_model(**overrides) -> ModelSpecification:
    """modA={r1,r2}, modB={r3,r4} -- the chain's own natural, contiguous split."""
    modularization = ModelModularization(
        modularization_id="seed",
        name="seed",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
    )
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _chain_network(),
        "kinetic_laws": (),
        "parameters": (),
        "modularizations": (modularization,),
        "model_modules": (
            ModelModule(module_id="modA", name="A"),
            ModelModule(module_id="modB", name="B"),
        ),
        "module_memberships": (
            _membership("modA", "r1"),
            _membership("modA", "r2"),
            _membership("modB", "r3"),
            _membership("modB", "r4"),
        ),
    } | overrides
    return ModelSpecification(**merged)


def _canonical_seed_bundle(model: ModelSpecification = None):
    model = model or _seed_model()
    return canonicalize_bundle(extract_bundle(model, "seed"))


def _topology_weights() -> CriteriaWeights:
    return CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),),
        policy_version="test-v1",
    )


def _policy(**overrides) -> SearchPolicy:
    merged = {
        "max_iterations": 3,
        "max_candidates_per_iteration": 50,
        "beam_width": 10,
        "allowed_operations": tuple(
            op for op in ProposalOperation if op is not ProposalOperation.SEED
        ),
        "policy_version": "test-v1",
    } | overrides
    return SearchPolicy(**merged)


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


# --- Proposal operators: MOVE_REACTION -------------------------------------------------------


def test_move_reaction_relocates_a_single_reaction():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    proposals = propose_move_reaction(bundle, model, SearchConstraints())
    # Each of modA={r1,r2}/modB={r3,r4} has 2 reactions -- moving any single one still leaves
    # its own source module non-empty, so all four are valid move targets.
    moved_reactions = {p.affected_component_ids[0] for p in proposals}
    assert moved_reactions == {"r1", "r2", "r3", "r4"}
    for p in proposals:
        reaction_id = p.affected_component_ids[0]
        module_ids = {m.module_id for m in p.bundle.memberships}
        assert len(module_ids) == 2  # module count never changes for a move
        reaction_module = {
            m.component_id: m.module_id
            for m in p.bundle.memberships
            if m.component_type is ModuleComponentType.REACTION
        }
        # the moved reaction now shares a module with a reaction it was not with before
        other_module_reactions = {
            rid for rid, mid in reaction_module.items() if mid == reaction_module[reaction_id]
        }
        assert reaction_id in other_module_reactions


def test_move_reaction_never_empties_source_module():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    proposals = propose_move_reaction(bundle, model, SearchConstraints())
    for p in proposals:
        for module_id in {m.module_id for m in p.bundle.memberships}:
            reaction_count = sum(
                1
                for m in p.bundle.memberships
                if m.module_id == module_id and m.component_type is ModuleComponentType.REACTION
            )
            assert reaction_count >= 1


def test_move_reaction_skips_excluded_components():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(excluded_component_ids=frozenset({"r2"}))
    proposals = propose_move_reaction(bundle, model, constraints)
    assert "r2" not in {p.affected_component_ids[0] for p in proposals}


def test_move_reaction_respects_must_stay_together():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(must_stay_together=(frozenset({"r2", "r3"}),))
    proposals = propose_move_reaction(bundle, model, constraints)
    # V1 simplification: neither grouped reaction (r2/r3) is ever proposed for a solo move --
    # r1/r4 are ungrouped and remain proposable.
    assert {p.affected_component_ids[0] for p in proposals} == {"r1", "r4"}


# --- Proposal operators: MERGE_MODULES -------------------------------------------------------


def test_merge_modules_only_proposes_adjacent_pairs():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    proposals = propose_merge_modules(bundle, model, SearchConstraints())
    assert len(proposals) == 1  # only one pair exists, and it is adjacent (r2<->r3 share C)
    merged = proposals[0].bundle
    assert len(set({m.module_id for m in merged.memberships})) == 1
    reaction_ids = {
        m.component_id
        for m in merged.memberships
        if m.component_type is ModuleComponentType.REACTION
    }
    assert reaction_ids == {"r1", "r2", "r3", "r4"}


def test_merge_modules_respects_forbidden_together():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(forbidden_together=(frozenset({"r2", "r3"}),))
    proposals = propose_merge_modules(bundle, model, constraints)
    assert proposals == ()


def test_merge_modules_respects_max_module_size():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(max_module_size=3)
    proposals = propose_merge_modules(bundle, model, constraints)
    assert proposals == ()  # merged module would have 4 reactions


def test_merge_modules_respects_min_module_count():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(min_module_count=2)
    proposals = propose_merge_modules(bundle, model, constraints)
    assert proposals == ()  # merging would drop to 1 module


# --- Proposal operators: SPLIT_MODULE ---------------------------------------------------------


def test_split_module_bisects_a_fully_connected_module():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    proposals = propose_split_module(bundle, model, SearchConstraints())
    # modA={r1,r2} and modB={r3,r4} are each internally connected (share B / share D), so the
    # fallback bisection applies to both -- two proposals, one per original module.
    assert len(proposals) == 2
    for p in proposals:
        new_module_ids = {m.module_id for m in p.bundle.memberships}
        assert len(new_module_ids) == 3  # the other original module + 2 new halves


def test_split_module_uses_connected_components_when_disconnected():
    # modA = {r1, r4} -- not topologically connected to each other at all (r1: A->B, r4: D->E).
    model = _seed_model(
        module_memberships=(
            _membership("modA", "r1"),
            _membership("modA", "r4"),
            _membership("modB", "r2"),
            _membership("modB", "r3"),
        )
    )
    bundle = _canonical_seed_bundle(model)
    proposals = propose_split_module(bundle, model, SearchConstraints())
    mod_a_module_ids = {
        m.module_id for m in bundle.memberships if m.component_id == "r1"
    }
    mod_a_split = next(
        p for p in proposals if p.affected_module_ids[0] in mod_a_module_ids
    )
    reaction_sets = []
    for module_id in {m.module_id for m in mod_a_split.bundle.memberships}:
        reactions = frozenset(
            m.component_id
            for m in mod_a_split.bundle.memberships
            if m.module_id == module_id and m.component_type is ModuleComponentType.REACTION
        )
        if reactions:
            reaction_sets.append(reactions)
    assert frozenset({"r1"}) in reaction_sets
    assert frozenset({"r4"}) in reaction_sets


def test_split_module_respects_min_module_size():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(min_module_size=2)
    proposals = propose_split_module(bundle, model, constraints)
    assert proposals == ()  # any 2-reaction module split produces two 1-reaction halves


def test_split_module_respects_max_module_count():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(max_module_count=2)
    proposals = propose_split_module(bundle, model, constraints)
    assert proposals == ()


# --- Proposal operators: ADD_BOUNDARY / REMOVE_BOUNDARY --------------------------------------


def test_add_boundary_declares_a_port_pair_for_shared_species():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    proposals = propose_add_boundary(bundle, model, SearchConstraints())
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.affected_component_ids == ("C",)  # the shared species between modA/modB
    ports = proposal.bundle.ports
    assert len(ports) == 2
    directions = {p.direction for p in ports}
    assert directions == {ModulePortDirection.OUTPUT, ModulePortDirection.INPUT}
    # membership partition is unchanged -- only ports changed.
    assert {
        (m.module_id, m.component_id) for m in proposal.bundle.memberships
    } == {(m.module_id, m.component_id) for m in bundle.memberships}


def test_add_boundary_respects_fixed_boundary_must_not_be_declared():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(
        fixed_boundaries=(FixedBoundary("C", BoundaryFixedState.MUST_NOT_BE_DECLARED),)
    )
    proposals = propose_add_boundary(bundle, model, constraints)
    assert proposals == ()


def test_remove_boundary_removes_a_declared_pair():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    (added,) = propose_add_boundary(bundle, model, SearchConstraints())
    proposals = propose_remove_boundary(added.bundle, model, SearchConstraints())
    assert len(proposals) == 1
    assert proposals[0].bundle.ports == ()


def test_remove_boundary_respects_fixed_boundary_must_be_declared():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    (added,) = propose_add_boundary(bundle, model, SearchConstraints())
    constraints = SearchConstraints(
        fixed_boundaries=(FixedBoundary("C", BoundaryFixedState.MUST_BE_DECLARED),)
    )
    proposals = propose_remove_boundary(added.bundle, model, constraints)
    assert proposals == ()


# --- Proposal operators: VARY_MODULE_COUNT ---------------------------------------------------


def test_vary_module_count_reaches_the_allowed_maximum():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(max_module_count=4)
    proposals = propose_vary_module_count(bundle, model, constraints)
    assert len(proposals) == 1
    assert len({m.module_id for m in proposals[0].bundle.memberships}) == 4


def test_vary_module_count_reaches_the_allowed_minimum():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    constraints = SearchConstraints(min_module_count=1)
    proposals = propose_vary_module_count(bundle, model, constraints)
    assert len(proposals) == 1
    assert len({m.module_id for m in proposals[0].bundle.memberships}) == 1


def test_vary_module_count_produces_nothing_when_unconstrained():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    assert propose_vary_module_count(bundle, model, SearchConstraints()) == ()


# --- Search: determinism, bounded termination, no mutation ----------------------------------


def test_search_is_deterministic():
    model = _seed_model()
    weights = _topology_weights()
    policy = _policy()
    first = search_candidate_modularizations(model, "seed", weights, policy)
    second = search_candidate_modularizations(model, "seed", weights, policy)
    assert [b.modularization.modularization_id for b in first.retained] == [
        b.modularization.modularization_id for b in second.retained
    ]
    first_scores = [e.overall_score for e in first.evaluations]
    second_scores = [e.overall_score for e in second.evaluations]
    assert first_scores == second_scores
    assert len(first.lineage) == len(second.lineage)


def test_search_never_mutates_canonical_model():
    model = _seed_model()
    before = replace(model)  # a structurally-identical, independent copy for comparison
    search_candidate_modularizations(model, "seed", _topology_weights(), _policy())
    assert model == before
    assert model.modularizations == (model.modularizations[0],)
    assert len(model.modularizations) == 1  # still just "seed" -- no candidate ever attached


def test_bounded_termination_respects_max_iterations():
    model = _seed_model()
    policy = _policy(max_iterations=2)
    result = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    assert result.iterations_run <= 2


def test_bounded_termination_stops_early_when_no_new_candidates():
    model = _seed_model()
    # A single-reaction-module seed has no further MOVE/MERGE/SPLIT to propose once fully
    # explored within very few generations -- confirms the search stops before max_iterations
    # rather than looping uselessly.
    policy = _policy(max_iterations=50, allowed_operations=(ProposalOperation.MERGE_MODULES,))
    result = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    assert result.iterations_run < 50


def test_max_candidates_per_iteration_caps_exploration():
    model = _seed_model()
    policy = _policy(max_candidates_per_iteration=1, max_iterations=1)
    result = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    # at most 1 new candidate considered in the one generation run
    new_lineage = [entry for entry in result.lineage if entry.generation == 1]
    assert len(new_lineage) <= 1


# --- Duplicate-equivalence elimination -------------------------------------------------------


def test_duplicate_candidates_are_rejected():
    model = _seed_model()
    policy = _policy(
        max_iterations=1,
        allowed_operations=(ProposalOperation.MOVE_REACTION, ProposalOperation.MERGE_MODULES),
    )
    result = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    all_candidate_ids = {entry.candidate_id for entry in result.lineage}
    assert len(all_candidate_ids) == len(result.lineage)  # every lineage id is unique
    # No two retained candidates share an identical membership partition.
    seen_signatures = set()
    for bundle in result.retained:
        module_ids = {m.module_id for m in bundle.memberships}
        signature = frozenset(module_content_key(bundle.memberships, mid) for mid in module_ids)
        assert signature not in seen_signatures
        seen_signatures.add(signature)


# --- Candidate lineage ------------------------------------------------------------------------


def test_candidate_lineage_traces_to_seed():
    model = _seed_model()
    result = search_candidate_modularizations(model, "seed", _topology_weights(), _policy())
    lineage_by_id = {entry.candidate_id: entry for entry in result.lineage}
    seed_entry = lineage_by_id[result.seed_candidate_id]
    assert seed_entry.operation is ProposalOperation.SEED
    assert seed_entry.parent_candidate_id is None
    for entry in result.lineage:
        if entry.candidate_id == result.seed_candidate_id:
            continue
        # every non-seed candidate's own ancestry chain terminates at the seed.
        current = entry
        depth = 0
        while current.parent_candidate_id is not None and depth < 100:
            current = lineage_by_id[current.parent_candidate_id]
            depth += 1
        assert current.candidate_id == result.seed_candidate_id


def test_rejected_candidates_carry_a_reason():
    model = _seed_model()
    result = search_candidate_modularizations(model, "seed", _topology_weights(), _policy())
    for r in result.rejected:
        assert r.reason
        assert r.parent_candidate_id


# --- Module-count variation across the search -------------------------------------------------


def test_module_count_varies_across_the_search():
    model = _seed_model()
    result = search_candidate_modularizations(model, "seed", _topology_weights(), _policy())
    module_counts = {ev.module_count for ev in result.evaluations}
    assert len(module_counts) > 1  # the search explores more than one module count


# --- Rankings change under different weights / calibration evidence -------------------------


def test_candidate_rankings_change_under_different_weights():
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    topology_result = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    boundary_weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.BOUNDARY_SPARSITY, Decimal("1")),),
        policy_version="test-v1",
    )
    boundary_result = search_candidate_modularizations(model, "seed", boundary_weights, policy)
    topology_scores = {
        ev.modularization_id: ev.overall_score for ev in topology_result.evaluations
    }
    boundary_scores = {
        ev.modularization_id: ev.overall_score for ev in boundary_result.evaluations
    }
    assert topology_scores != boundary_scores


def test_calibration_evidence_affects_retention():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    module_ids = sorted({m.module_id for m in bundle.memberships})
    content_keys = {mid: module_content_key(bundle.memberships, mid) for mid in module_ids}

    def _evaluation(module_id: str, status: ModuleCalibrationStatus) -> ModuleCalibrationEvaluation:
        return ModuleCalibrationEvaluation(
            evaluation_id=f"eval::{module_id}",
            request_id=f"req::{module_id}",
            correlation_id="corr-1",
            run_id="run-1",
            parent_model_id="m1",
            modularization_id="seed",
            module_id=module_id,
            status=status,
            policy_version="test-v1",
        )

    good_evidence = {
        content_keys[module_ids[0]]: _evaluation(
            module_ids[0], ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        content_keys[module_ids[1]]: _evaluation(
            module_ids[1], ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
    }
    calibration_weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),),
        policy_version="test-v1",
    )
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    without_evidence = search_candidate_modularizations(model, "seed", calibration_weights, policy)
    with_evidence = search_candidate_modularizations(
        model, "seed", calibration_weights, policy, calibration_evidence=good_evidence
    )
    without_seed_id = without_evidence.seed_candidate_id
    with_seed_id = with_evidence.seed_candidate_id
    seed_eval_without = next(
        ev for ev in without_evidence.evaluations if ev.modularization_id == without_seed_id
    )
    seed_eval_with = next(
        ev for ev in with_evidence.evaluations if ev.modularization_id == with_seed_id
    )
    assert seed_eval_without.overall_score is None  # no evidence supplied at all -> unavailable
    assert seed_eval_with.overall_score == Decimal("1")  # both modules fully supported


def test_calibration_evidence_unavailable_is_handled_honestly():
    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    module_ids = sorted({m.module_id for m in bundle.memberships})
    content_keys = {mid: module_content_key(bundle.memberships, mid) for mid in module_ids}
    partial_evidence = {
        content_keys[module_ids[0]]: ModuleCalibrationEvaluation(
            evaluation_id="eval-1",
            request_id="req-1",
            correlation_id="corr-1",
            run_id="run-1",
            parent_model_id="m1",
            modularization_id="seed",
            module_id=module_ids[0],
            status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
            policy_version="test-v1",
        )
    }
    calibration_weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),),
        policy_version="test-v1",
    )
    result = search_candidate_modularizations(
        model,
        "seed",
        calibration_weights,
        _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,)),
        calibration_evidence=partial_evidence,
    )
    seed_id = result.seed_candidate_id
    seed_eval = next(ev for ev in result.evaluations if ev.modularization_id == seed_id)
    calib_score = next(
        cs
        for cs in seed_eval.criterion_scores
        if cs.criterion is ModularizationCriterion.CALIBRATION_INDEPENDENCE
    )
    assert calib_score.available is False  # module_ids[1] has no evidence -- never fabricated


# --- Filtered-topology integration ------------------------------------------------------------


def test_filtered_topology_integration_changes_scores():
    model = _seed_model(
        full_network=_chain_network(
            species=(
                _species(species_id="A"),
                _species(species_id="B"),
                _species(species_id="ATP"),
                _species(species_id="C"),
                _species(species_id="D"),
                _species(species_id="E"),
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
                        _participant(species_id="B", role=ParticipantRole.REACTANT),
                        _participant(species_id="C", role=ParticipantRole.PRODUCT),
                    ),
                ),
                _reaction(
                    reaction_id="r3",
                    participants=(
                        _participant(species_id="C", role=ParticipantRole.REACTANT),
                        _participant(species_id="D", role=ParticipantRole.PRODUCT),
                        _participant(species_id="ATP", role=ParticipantRole.PRODUCT),
                    ),
                ),
                _reaction(
                    reaction_id="r4",
                    participants=(
                        _participant(species_id="D", role=ParticipantRole.REACTANT),
                        _participant(species_id="E", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
        )
    )
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    unfiltered = search_candidate_modularizations(model, "seed", _topology_weights(), policy)
    filtered = search_candidate_modularizations(
        model,
        "seed",
        _topology_weights(),
        policy,
        topology_filtering=TopologyFilteringPolicy(
            overrides=(TopologyRoleOverride("ATP", TopologyRole.UNIVERSAL_CURRENCY),)
        ),
    )
    unfiltered_seed = next(
        ev for ev in unfiltered.evaluations if ev.modularization_id == unfiltered.seed_candidate_id
    )
    filtered_seed = next(
        ev for ev in filtered.evaluations if ev.modularization_id == filtered.seed_candidate_id
    )
    assert unfiltered_seed.overall_score != filtered_seed.overall_score


# --- GENERATED/IMPORTED symmetry --------------------------------------------------------------


def test_generated_and_imported_models_search_identically():
    generated = _seed_model()
    seed_bundle = extract_bundle(generated, "seed")
    imported_base = _imported_chain_model()
    imported = replace(
        imported_base,
        modularizations=generated.modularizations,
        model_modules=generated.model_modules,
        module_memberships=seed_bundle.memberships,
    )
    policy = _policy()
    weights = _topology_weights()
    generated_result = search_candidate_modularizations(generated, "seed", weights, policy)
    imported_result = search_candidate_modularizations(imported, "seed", weights, policy)
    generated_scores = sorted(
        ev.overall_score for ev in generated_result.evaluations if ev.overall_score is not None
    )
    imported_scores = sorted(
        ev.overall_score for ev in imported_result.evaluations if ev.overall_score is not None
    )
    assert generated_scores == imported_scores
    assert len(generated_result.retained) == len(imported_result.retained)


# --- Output never declares a "correct" solution ------------------------------------------------


def test_result_reports_every_retained_candidate_without_picking_a_winner():
    model = _seed_model()
    result = search_candidate_modularizations(model, "seed", _topology_weights(), _policy())
    assert len(result.retained) > 1
    assert len(result.evaluations) == len(result.retained)
    # every evaluation is independently inspectable; nothing in the result type itself singles
    # one out (confirmed structurally: no "best"/"winner"/"correct" field exists on the type).
    assert not hasattr(result, "best_candidate_id")
    assert not hasattr(result, "winner")


# --- Regression: VARY_MODULE_COUNT direction, fair per-operation capping ---------------------
#
# Both bugs below were only caught against the real sce00061 yeast model (26 real modules,
# min_module_count=2/max_module_count=8): a seed far outside the allowed range, and six
# operations competing for one shared per-iteration budget.


def test_vary_module_count_shrinks_toward_max_when_currently_above_it():
    model = _seed_model()  # 2 modules
    constraints = SearchConstraints(max_module_count=1)
    proposals = propose_vary_module_count(_canonical_seed_bundle(model), model, constraints)
    assert len(proposals) == 1
    assert len({m.module_id for m in proposals[0].bundle.memberships}) == 1


def test_vary_module_count_grows_toward_min_when_currently_below_it():
    model = _seed_model()  # 2 modules, each splittable (2 reactions apiece)
    constraints = SearchConstraints(min_module_count=3)
    proposals = propose_vary_module_count(_canonical_seed_bundle(model), model, constraints)
    assert len(proposals) == 1
    assert len({m.module_id for m in proposals[0].bundle.memberships}) == 3


def test_cap_fairly_across_operations_never_starves_a_low_volume_operation():
    from app.agent2.modularization_search.operators import Proposal
    from app.agent2.modularization_search.search import _cap_fairly_across_operations

    model = _seed_model()
    bundle = _canonical_seed_bundle(model)
    stub_proposal = Proposal(bundle, (), ())
    # ADD_BOUNDARY dominates volume (100 items); VARY_MODULE_COUNT has only 1 -- a single
    # global lexicographic cut (ADD_BOUNDARY sorts first) would starve it out entirely at a
    # tight budget shared across both.
    raw = [("parent", ProposalOperation.ADD_BOUNDARY, stub_proposal) for _ in range(100)]
    raw.append(("parent", ProposalOperation.VARY_MODULE_COUNT, stub_proposal))
    capped = _cap_fairly_across_operations(raw, 4)
    operations_present = {item[1] for item in capped}
    assert ProposalOperation.VARY_MODULE_COUNT in operations_present
    assert ProposalOperation.ADD_BOUNDARY in operations_present
    # VARY_MODULE_COUNT's own single item is fully included; ADD_BOUNDARY fills its own
    # 2-item share (max_candidates=4 split evenly across 2 active operations) -- 3 total,
    # never ADD_BOUNDARY alone consuming the entire budget.
    assert len(capped) == 3


# --- apply_resolution_correction (Module-Count / Resolution Bias Audit increment) -------------


def test_apply_resolution_correction_neutralizes_intermediate_resolution_bias():
    """The seed (modA={r1,r2}/modB={r3,r4}) under TOPOLOGICAL_SEPARATION alone scores 2/3 raw
    -- but a matched, structure-blind null partition at module_count=2 on this same simple
    chain scores identically (both are the identical contiguous 2/2 split): the seed's own raw
    score reflects zero real signal beyond pure chunking, and the correction must disclose
    that honestly (corrected_score == 0, driving overall_score to 0), never silently leaving
    the uncorrected 2/3 unexamined."""
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    weights = _topology_weights()
    result = search_candidate_modularizations(
        model, "seed", weights, policy, apply_resolution_correction=True
    )
    seed_id = result.seed_candidate_id
    seed_eval = next(ev for ev in result.evaluations if ev.modularization_id == seed_id)
    score = seed_eval.criterion_scores[0]
    assert score.raw_score == Decimal("2") / Decimal("3")
    assert score.null_reference_score == score.raw_score
    assert score.corrected_score == Decimal("0")
    assert seed_eval.overall_score == Decimal("0")


def test_apply_resolution_correction_cannot_fix_the_degenerate_single_module_case():
    """Honest, disclosed limitation (never papered over with an arbitrary module-count
    penalty, per the task's own explicit non-goal): a single-module candidate's own null
    baseline is *also* always exactly 1.0 (there is only one way to partition into one group),
    so corrected_score is None (0/0 is never fabricated) and overall_score falls back to the
    uncorrected raw score of 1 -- the correction mechanism neutralizes intermediate-resolution
    bias but cannot, by construction, suppress the absolute degenerate case on its own;
    distinguishing real multi-criterion biological signal from this one remaining blind spot
    is exactly why this framework never relies on a single criterion alone."""
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    weights = _topology_weights()
    result = search_candidate_modularizations(
        model, "seed", weights, policy, apply_resolution_correction=True
    )
    # The 1-module merge is, by default, excluded from ranking (degenerate-single-module
    # policy, Calibration-Independence Aggregation increment) -- still fully evaluated and
    # reported, just in ``degenerate_evaluations`` rather than ``evaluations``.
    merged_eval = next(ev for ev in result.degenerate_evaluations if ev.module_count == 1)
    score = merged_eval.criterion_scores[0]
    assert score.null_reference_score == Decimal("1")
    assert score.corrected_score is None
    assert merged_eval.overall_score == Decimal("1")


def test_apply_resolution_correction_default_false_reproduces_prior_search():
    model = _seed_model()
    policy = _policy()
    weights = _topology_weights()
    without_flag = search_candidate_modularizations(model, "seed", weights, policy)
    with_flag_false = search_candidate_modularizations(
        model, "seed", weights, policy, apply_resolution_correction=False
    )
    without_ids = [b.modularization.modularization_id for b in without_flag.retained]
    with_ids = [b.modularization.modularization_id for b in with_flag_false.retained]
    assert without_ids == with_ids
    without_scores = [ev.overall_score for ev in without_flag.evaluations]
    with_scores = [ev.overall_score for ev in with_flag_false.evaluations]
    assert without_scores == with_scores
    for ev in with_flag_false.evaluations:
        assert all(cs.null_reference_score is None for cs in ev.criterion_scores)


# --- Degenerate single-module policy (Calibration-Independence Aggregation + Degenerate -----
# Resolution Policy increment) -----------------------------------------------------------------


def _one_module_seed_model(**overrides) -> ModelSpecification:
    """The identical chain network as ``_seed_model``, but seeded as one single module (``r1``-
    ``r4`` all together) -- the degenerate, boundary-free starting point."""
    modularization = ModelModularization(
        modularization_id="seed1",
        name="seed1",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modAll",),
    )
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _chain_network(),
        "kinetic_laws": (),
        "parameters": (),
        "modularizations": (modularization,),
        "model_modules": (ModelModule(module_id="modAll", name="All"),),
        "module_memberships": (
            _membership("modAll", "r1", modularization_id="seed1"),
            _membership("modAll", "r2", modularization_id="seed1"),
            _membership("modAll", "r3", modularization_id="seed1"),
            _membership("modAll", "r4", modularization_id="seed1"),
        ),
    } | overrides
    return ModelSpecification(**merged)


def test_exclude_single_module_from_ranking_defaults_to_true():
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    weights = _topology_weights()
    result = search_candidate_modularizations(model, "seed", weights, policy)
    assert result.exclude_single_module_from_ranking is True


def test_one_module_candidate_is_evaluated_and_reported_but_excluded_from_ranking():
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    weights = _topology_weights()
    result = search_candidate_modularizations(model, "seed", weights, policy)

    # Never a valid winner: no 1-module candidate occupies a retained/evaluations slot.
    assert all(len(b.modules) != 1 for b in result.retained)
    assert all(ev.module_count != 1 for ev in result.evaluations)

    # Still fully evaluated and reported, never silently dropped.
    assert any(len(b.modules) == 1 for b in result.degenerate)
    assert any(ev.module_count == 1 for ev in result.degenerate_evaluations)
    degenerate_eval = next(ev for ev in result.degenerate_evaluations if ev.module_count == 1)
    assert degenerate_eval.overall_score is not None  # a real, computed score, not a stub

    # Lineage records every candidate ever produced regardless of fate -- including the
    # degenerate one, which is neither "rejected" (a competitive loss) nor silently absent.
    degenerate_candidate_ids = {
        b.modularization.modularization_id for b in result.degenerate
    }
    assert degenerate_candidate_ids
    lineage_ids = {entry.candidate_id for entry in result.lineage}
    assert degenerate_candidate_ids <= lineage_ids
    rejected_ids = {entry.candidate_id for entry in result.rejected}
    assert degenerate_candidate_ids.isdisjoint(rejected_ids)


def test_exclude_single_module_from_ranking_false_restores_prior_behavior():
    model = _seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    weights = _topology_weights()
    result = search_candidate_modularizations(
        model, "seed", weights, policy, exclude_single_module_from_ranking=False
    )
    assert result.exclude_single_module_from_ranking is False
    # The 1-module merge now competes normally -- it is retained/evaluated directly.
    assert any(len(b.modules) == 1 for b in result.retained)
    assert any(ev.module_count == 1 for ev in result.evaluations)
    # ...and never duplicated into the degenerate-reporting buckets.
    assert result.degenerate == ()
    assert result.degenerate_evaluations == ()


def test_degenerate_exclusion_matches_prior_search_results_otherwise():
    """Excluding the degenerate candidate from ranking must not change any *other* retained
    candidate's own score or membership -- it is removed from competition, not allowed to
    perturb anyone else's evaluation."""
    model = _seed_model()
    policy = _policy(
        allowed_operations=(ProposalOperation.MERGE_MODULES, ProposalOperation.MOVE_REACTION)
    )
    weights = _topology_weights()
    excluded = search_candidate_modularizations(model, "seed", weights, policy)
    included = search_candidate_modularizations(
        model, "seed", weights, policy, exclude_single_module_from_ranking=False
    )
    excluded_multi = {
        frozenset(m.component_id for m in bundle.memberships): ev.overall_score
        for bundle, ev in zip(excluded.retained, excluded.evaluations, strict=True)
    }
    included_multi = {
        frozenset(m.component_id for m in bundle.memberships): ev.overall_score
        for bundle, ev in zip(included.retained, included.evaluations, strict=True)
        if len(bundle.modules) != 1
    }
    assert excluded_multi == included_multi


def test_fully_degenerate_seed_yields_empty_retained_and_no_weight_space_by_default():
    """An intentionally one-module seed, with no override: the search cannot even start (there
    is nothing non-degenerate to build the frontier from), so every output collection is
    honestly empty/``None`` rather than fabricated -- a disclosed outcome, never an exception."""
    model = _one_module_seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.SPLIT_MODULE,))
    weights = _topology_weights()
    result = search_candidate_modularizations(model, "seed1", weights, policy)
    assert result.retained == ()
    assert result.evaluations == ()
    assert result.weight_space_result is None
    assert len(result.degenerate) == 1
    assert len(result.degenerate_evaluations) == 1
    assert any("exclude_single_module_from_ranking=False" in w for w in result.warnings)


def test_fully_degenerate_seed_with_override_competes_and_can_still_split():
    """The override restores the ability to explore from a one-module seed (e.g. splitting it
    back out) -- the exact scenario the default exclusion would otherwise foreclose."""
    model = _one_module_seed_model()
    policy = _policy(allowed_operations=(ProposalOperation.SPLIT_MODULE,))
    weights = _topology_weights()
    result = search_candidate_modularizations(
        model, "seed1", weights, policy, exclude_single_module_from_ranking=False
    )
    assert result.retained != ()
    assert result.weight_space_result is not None
    assert any(len(b.modules) > 1 for b in result.retained)  # SPLIT_MODULE found a 2-module split


def test_degenerate_policy_results_are_deterministic():
    model = _seed_model()
    policy = _policy(
        allowed_operations=(ProposalOperation.MERGE_MODULES, ProposalOperation.MOVE_REACTION)
    )
    weights = _topology_weights()
    first = search_candidate_modularizations(model, "seed", weights, policy)
    second = search_candidate_modularizations(model, "seed", weights, policy)
    first_degenerate_ids = {b.modularization.modularization_id for b in first.degenerate}
    second_degenerate_ids = {b.modularization.modularization_id for b in second.degenerate}
    assert first_degenerate_ids == second_degenerate_ids
    first_scores = [ev.overall_score for ev in first.degenerate_evaluations]
    second_scores = [ev.overall_score for ev in second.degenerate_evaluations]
    assert first_scores == second_scores
