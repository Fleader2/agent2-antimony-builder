"""Tests for the Automatic Functional-Evaluation Selection and Caching increment's own
Agent2-side half: ``app.agent2.candidate_orchestration``'s new functional-evaluation-selection
gate (``FunctionalEvaluationSelectionPolicy``/``select_modules_for_functional_evaluation``/
``build_functional_evaluation_requests``), threaded through ``run_candidate_search_round``.

Fixture style mirrors ``tests/agent2/test_candidate_orchestration.py``'s own chain network
(A -> B -> C -> D -> E, seed modA={r1,r2}/modB={r3,r4}) exactly, so results can be hand-verified
and cross-referenced against that file's own identical-shaped calibration tests.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.agent2.antimony_import import import_antimony
from app.agent2.candidate_orchestration import (
    CalibrationDecisionOutcome,
    CalibrationSelectionPolicy,
    FunctionalEvaluationDecisionOutcome,
    FunctionalEvaluationSelectionPolicy,
    build_submodel,
    run_candidate_search_round,
)
from app.agent2.modularization_search import ProposalOperation, SearchPolicy
from app.agent2.modularization_search.identity import derive_module_id, module_content_key
from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
from app.agent2.module_evaluation.evaluator import evaluate_modularization
from app.agent2.module_functional_evaluation.types import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationResult,
    PerturbationEffectRecord,
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
    ModulePort,
    ModulePortDirection,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures (mirrors tests/agent2/test_candidate_orchestration.py's _kinetic_seed_model) ------


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


_SUBSTRATE_BY_REACTION = {"r1": "A", "r2": "B", "r3": "C", "r4": "D"}
_PRODUCT_BY_REACTION = {"r1": "B", "r2": "C", "r3": "D", "r4": "E"}


def _chain_network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "n1",
        "compartments": (_compartment(),),
        "species": tuple(_species(species_id=sid) for sid in ("A", "B", "C", "D", "E")),
        "reactions": tuple(
            _reaction(
                reaction_id=rid,
                participants=(
                    _participant(
                        species_id=_SUBSTRATE_BY_REACTION[rid], role=ParticipantRole.REACTANT
                    ),
                    _participant(
                        species_id=_PRODUCT_BY_REACTION[rid], role=ParticipantRole.PRODUCT
                    ),
                ),
            )
            for rid in ("r1", "r2", "r3", "r4")
        ),
    } | overrides
    return FullNetwork(**merged)


def _kinetic_law(reaction_id: str) -> KineticLawSpecification:
    substrate = _SUBSTRATE_BY_REACTION[reaction_id]
    return KineticLawSpecification(
        kinetic_law_id=f"kl-{reaction_id}",
        reaction_id=reaction_id,
        law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        expression=f"k_{reaction_id} * {substrate}",
        parameter_ids=(f"k_{reaction_id}",),
        species_ids=(substrate,),
    )


def _parameter(reaction_id: str) -> ParameterSpecification:
    return ParameterSpecification(
        parameter_id=f"k_{reaction_id}",
        name=f"k_{reaction_id}",
        source=ParameterSource.CURATED,
        value=Decimal("0.5"),
        reaction_id=reaction_id,
    )


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


def _kinetic_seed_model(**overrides) -> ModelSpecification:
    """modA={r1,r2}, modB={r3,r4}, real mass-action kinetics/parameters for every reaction,
    plus a genuinely ``externally_controlled`` boundary port on the shared species "C" -- so
    the whole network is ``EXECUTABLE`` and each module has >= 2 internal + >= 1 external
    parameter targets (eligible for a real ``ModuleFunctionalEvaluationRequest``)."""
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
        "kinetic_laws": tuple(_kinetic_law(r) for r in ("r1", "r2", "r3", "r4")),
        "parameters": tuple(_parameter(r) for r in ("r1", "r2", "r3", "r4")),
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
        "module_ports": (
            ModulePort(
                port_id="port-C-modA",
                modularization_id="seed",
                module_id="modA",
                species_id="C",
                direction=ModulePortDirection.OUTPUT,
                externally_controlled=True,
                initial_value=Decimal("1"),
            ),
            ModulePort(
                port_id="port-C-modB",
                modularization_id="seed",
                module_id="modB",
                species_id="C",
                direction=ModulePortDirection.INPUT,
                externally_controlled=True,
                initial_value=Decimal("1"),
            ),
        ),
    } | overrides
    return ModelSpecification(**merged)


def _imported_chain_model() -> ModelSpecification:
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


def _topology_weights() -> CriteriaWeights:
    return CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),),
        policy_version="test-v1",
    )


def _functional_weights(**overrides) -> CriteriaWeights:
    merged = {
        "weights": (
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("0.5")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("0.25")),
            CriterionWeight(ModularizationCriterion.SENSITIVITY_COHERENCE, Decimal("0.25")),
        ),
        "policy_version": "test-v1",
    } | overrides
    return CriteriaWeights(**merged)


def _search_policy(**overrides) -> SearchPolicy:
    merged = {
        "max_iterations": 2,
        "max_candidates_per_iteration": 10,
        "beam_width": 5,
        "allowed_operations": (ProposalOperation.MOVE_REACTION,),
        "policy_version": "test-v1",
    } | overrides
    return SearchPolicy(**merged)


def _calibration_selection_policy(**overrides) -> CalibrationSelectionPolicy:
    merged = {
        "max_candidates_per_generation": 1,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_calibration_run_budget": 0,
        "policy_version": "test-v1",
    } | overrides
    return CalibrationSelectionPolicy(**merged)


def _functional_selection_policy(**overrides) -> FunctionalEvaluationSelectionPolicy:
    merged = {
        "max_candidates_per_generation": 10,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_functional_evaluation_budget": 1000,
        "policy_version": "test-v1",
    } | overrides
    return FunctionalEvaluationSelectionPolicy(**merged)


def _effect(target_id: str, is_internal: bool, changes: dict[str, str]) -> PerturbationEffectRecord:
    return PerturbationEffectRecord(
        target_kind="PARAMETER",
        target_id=target_id,
        is_internal=is_internal,
        simulation_status="SUCCESS",
        remained_numerically_stable=True,
        relative_change_by_species=tuple(sorted((k, Decimal(v)) for k, v in changes.items())),
    )


def _isolated_result(modularization_id: str, module_id: str) -> ModuleFunctionalEvaluationResult:
    return ModuleFunctionalEvaluationResult(
        evaluation_id="e",
        request_id="r",
        correlation_id="c",
        run_id="run",
        parent_model_id="m1",
        modularization_id=modularization_id,
        module_id=module_id,
        status=FunctionalEvaluationStatus.EVALUATED,
        policy_version="v1",
        perturbation_effects=(
            _effect("k_r1", True, {"A": "0.5", "B": "0.4", "C": "0.001", "D": "0.001"}),
            _effect("k_r2", True, {"A": "0.3", "B": "0.35", "C": "0.001", "D": "0.001"}),
            _effect("k_r3", False, {"A": "0.001", "B": "0.02", "C": "0.4", "D": "0.3"}),
        ),
    )


def _coupled_result(modularization_id: str, module_id: str) -> ModuleFunctionalEvaluationResult:
    return ModuleFunctionalEvaluationResult(
        evaluation_id="e",
        request_id="r",
        correlation_id="c",
        run_id="run",
        parent_model_id="m1",
        modularization_id=modularization_id,
        module_id=module_id,
        status=FunctionalEvaluationStatus.EVALUATED,
        policy_version="v1",
        perturbation_effects=(
            _effect("k_r1", True, {"A": "0.5", "B": "0.4", "C": "0.45", "D": "0.4"}),
            _effect("k_r2", True, {"A": "0.3", "B": "0.35", "C": "0.3", "D": "0.35"}),
            _effect("k_r3", False, {"A": "0.4", "B": "0.02", "C": "0.4", "D": "0.3"}),
        ),
    )


def _content_key(model: ModelSpecification, module_id: str, *, modularization_id: str = "seed"):
    memberships = tuple(
        m for m in model.module_memberships if m.modularization_id == modularization_id
    )
    return module_content_key(memberships, module_id)


# --- zero functional weights -> no Agent 3 calls --------------------------------------------------


def test_zero_functional_weights_produces_no_requests():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _topology_weights(),
        _search_policy(),
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(),
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.functional_evaluation_requests == ()
    assert result.locally_resolved_functional_evidence == ()
    assert len(result.functional_evaluation_decisions) > 0
    assert all(
        d.outcome is FunctionalEvaluationDecisionOutcome.SKIP_ZERO_FUNCTIONAL_WEIGHT
        for d in result.functional_evaluation_decisions
    )


def test_omitting_the_policy_entirely_produces_no_decisions_at_all():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(),
        _calibration_selection_policy(),
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.functional_evaluation_decisions == ()
    assert result.functional_evaluation_requests == ()
    assert result.locally_resolved_functional_evidence == ()


# --- structural gate prevents unnecessary functional evaluation -----------------------------------


def test_structural_prefilter_prevents_unnecessary_functional_evaluation():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(),
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(
            score_threshold=Decimal("0.99")
        ),
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.functional_evaluation_requests == ()
    assert result.locally_resolved_functional_evidence == ()
    assert len(result.functional_evaluation_decisions) > 0
    assert all(
        d.outcome is FunctionalEvaluationDecisionOutcome.SKIP_BELOW_SCORE_THRESHOLD
        for d in result.functional_evaluation_decisions
    )


# --- functional evidence reverses candidate ranking -----------------------------------------------


def test_functional_evidence_changes_candidate_ranking():
    """The functional evidence this increment's own gate ultimately produces feeds into
    ``evaluate_modularization`` exactly like calibration evidence already does (unchanged,
    prior increment) -- verified directly at that layer (bypassing the search's own beam
    machinery, which is free to retain a different candidate *set* run to run once evidence
    changes a borderline candidate's score, making candidate-id-based comparison across two
    separate ``run_candidate_search_round`` calls an unreliable way to test this specific
    mechanism)."""

    def _species_membership(
        module_id: str, species_id: str, *, modularization_id: str
    ) -> ModuleMembership:
        return ModuleMembership(
            membership_id=f"mem_species_{modularization_id}_{module_id}_{species_id}",
            modularization_id=modularization_id,
            module_id=module_id,
            component_type=ModuleComponentType.SPECIES,
            component_id=species_id,
        )

    model = _kinetic_seed_model()
    # DYNAMIC_ISOLATION/SENSITIVITY_COHERENCE derive "which species are internal to this
    # module" from explicit SPECIES-type ModuleMembership rows (app.agent2.module_evaluation
    # .evaluator._species_by_module) -- never from REACTION memberships alone -- so this test
    # (unlike every other one in this file, which only needs REACTION memberships for the
    # search's own purposes) must declare them.
    model = replace(
        model,
        module_memberships=(
            *model.module_memberships,
            *(
                _species_membership(mod, sid, modularization_id="seed")
                for mod, sid in (
                    ("modA", "A"),
                    ("modA", "B"),
                    ("modA", "C"),
                    ("modB", "C"),
                    ("modB", "D"),
                    ("modB", "E"),
                )
            ),
        ),
    )
    second_split = ModelModularization(
        modularization_id="alt",
        name="alt",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modC", "modD"),
    )
    model = replace(
        model,
        modularizations=(*model.modularizations, second_split),
        model_modules=(
            *model.model_modules,
            ModelModule(module_id="modC", name="C"),
            ModelModule(module_id="modD", name="D"),
        ),
        module_memberships=(
            *model.module_memberships,
            _membership("modC", "r1", modularization_id="alt"),
            _membership("modD", "r2", modularization_id="alt"),
            _membership("modD", "r3", modularization_id="alt"),
            _membership("modD", "r4", modularization_id="alt"),
            *(
                _species_membership(mod, sid, modularization_id="alt")
                for mod, sid in (
                    ("modC", "A"),
                    ("modC", "B"),
                    ("modD", "B"),
                    ("modD", "C"),
                    ("modD", "D"),
                    ("modD", "E"),
                )
            ),
        ),
    )
    weights = CriteriaWeights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("0.1")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("0.45")),
            CriterionWeight(ModularizationCriterion.SENSITIVITY_COHERENCE, Decimal("0.45")),
        ),
        policy_version="test-v1",
    )
    without_evidence_seed = evaluate_modularization(model, "seed", weights)
    without_evidence_alt = evaluate_modularization(model, "alt", weights)
    assert without_evidence_seed.overall_score == without_evidence_alt.overall_score  # both 0

    with_evidence_seed = evaluate_modularization(
        model,
        "seed",
        weights,
        functional_evaluation_evidence={
            "modA": _coupled_result("seed", "modA"),
            "modB": _coupled_result("seed", "modB"),
        },
    )
    with_evidence_alt = evaluate_modularization(
        model,
        "alt",
        weights,
        functional_evaluation_evidence={
            "modC": _isolated_result("alt", "modC"),
            "modD": _isolated_result("alt", "modD"),
        },
    )
    assert with_evidence_alt.overall_score > with_evidence_seed.overall_score
    assert with_evidence_seed.overall_score != without_evidence_seed.overall_score
    assert with_evidence_alt.overall_score != without_evidence_alt.overall_score


# --- functional budget enforced -------------------------------------------------------------------


def test_functional_evaluation_budget_enforced():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,)),
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(
            total_functional_evaluation_budget=1
        ),
        correlation_id="corr-1",
        run_id="run-1",
    )
    evaluate_decisions = [
        d
        for d in result.functional_evaluation_decisions
        if d.outcome is FunctionalEvaluationDecisionOutcome.EVALUATE
    ]
    assert len(evaluate_decisions) == 1
    assert any(
        d.outcome is FunctionalEvaluationDecisionOutcome.SKIP_TOTAL_BUDGET_EXHAUSTED
        for d in result.functional_evaluation_decisions
    )


def test_max_candidates_per_generation_enforced_for_functional_evaluation():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,)),
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(
            max_candidates_per_generation=1
        ),
        correlation_id="corr-1",
        run_id="run-1",
    )
    evaluated_candidates = {
        d.candidate_id
        for d in result.functional_evaluation_decisions
        if d.outcome is FunctionalEvaluationDecisionOutcome.EVALUATE
    }
    assert len(evaluated_candidates) <= 1
    assert any(
        d.outcome is FunctionalEvaluationDecisionOutcome.SKIP_CANDIDATE_BUDGET_EXHAUSTED
        for d in result.functional_evaluation_decisions
    )


# --- real requests are actually built for an EVALUATE decision ------------------------------------


def test_evaluate_decisions_produce_real_requests():
    model = _kinetic_seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,)),
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(),
        correlation_id="corr-1",
        run_id="run-1",
    )
    evaluate_decisions = [
        d
        for d in result.functional_evaluation_decisions
        if d.outcome is FunctionalEvaluationDecisionOutcome.EVALUATE
    ]
    assert len(evaluate_decisions) > 0
    # An EVALUATE decision becomes either a real request or a local UNSUPPORTED_ANALYSIS/
    # INSUFFICIENT_TARGETS resolution (e.g. a single-reaction candidate module has too few
    # internal targets) -- mirrors CALIBRATE's own identical "request or local resolution"
    # split exactly.
    assert len(result.functional_evaluation_requests) + len(
        result.locally_resolved_functional_evidence
    ) == len(evaluate_decisions)
    assert len(result.functional_evaluation_requests) > 0
    for envelope in result.functional_evaluation_requests:
        assert envelope.request.whole_network_handoff["antimony_text"]
        internal_count = sum(1 for t in envelope.request.perturbation_targets if t.is_internal)
        external_count = len(envelope.request.perturbation_targets) - internal_count
        assert internal_count >= 2
        assert external_count >= 1


# --- already-evidenced modules are never re-evaluated ---------------------------------------------


def test_already_evidenced_module_is_skipped():
    model = _kinetic_seed_model()
    key_a = _content_key(model, "modA")
    # Module ids on the search's own retained candidates are always content-addressed
    # (``derive_module_id``), never the parent's own human-given "modA" label -- the same
    # derived id string is both this evidence dict's own lookup key and what every matching
    # retained candidate's own module is actually called.
    derived_module_id = derive_module_id(key_a)
    evidence = {key_a: _isolated_result("seed", derived_module_id)}
    result = run_candidate_search_round(
        model,
        "seed",
        _functional_weights(),
        _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,)),
        _calibration_selection_policy(),
        functional_evaluation_evidence=evidence,
        functional_evaluation_selection_policy=_functional_selection_policy(),
        correlation_id="corr-1",
        run_id="run-1",
    )
    mod_a_decisions = [
        d for d in result.functional_evaluation_decisions if d.module_id == derived_module_id
    ]
    assert mod_a_decisions
    assert all(
        d.outcome is FunctionalEvaluationDecisionOutcome.SKIP_ALREADY_EVIDENCED
        for d in mod_a_decisions
    )


# --- functional + calibration evidence compose correctly ------------------------------------------


def test_functional_and_calibration_selection_have_independent_budgets():
    model = _kinetic_seed_model()
    weights = CriteriaWeights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("0.4")),
            CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("0.3")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("0.15")),
            CriterionWeight(ModularizationCriterion.SENSITIVITY_COHERENCE, Decimal("0.15")),
        ),
        policy_version="test-v1",
    )
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,)),
        _calibration_selection_policy(
            max_candidates_per_generation=10, total_calibration_run_budget=0
        ),
        functional_evaluation_selection_policy=_functional_selection_policy(
            max_candidates_per_generation=10, total_functional_evaluation_budget=1000
        ),
        correlation_id="corr-1",
        run_id="run-1",
    )
    # Calibration budget is zero -> every calibration decision is a skip; functional budget is
    # generous -> functional decisions include real EVALUATE outcomes. Neither gate's own
    # outcome depends on the other's -- a genuinely separate budget/policy (task instructions
    # §5).
    assert all(
        d.outcome is not CalibrationDecisionOutcome.CALIBRATE for d in result.calibration_decisions
    )
    assert any(
        d.outcome is FunctionalEvaluationDecisionOutcome.EVALUATE
        for d in result.functional_evaluation_decisions
    )


# --- recursive / materialized-submodel operation --------------------------------------------------


def test_functional_evaluation_selection_works_on_a_materialized_submodel():
    model = _kinetic_seed_model()
    submodel, sub_id = build_submodel(model, "seed", "modA")
    weights = CriteriaWeights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("0.5")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("0.5")),
        ),
        policy_version="test-v1",
    )
    # The submodel's own seed modularization has exactly one module (modA's own closure) --
    # a degenerate seed never seeds the search frontier at all under the default
    # exclude_single_module_from_ranking=True (nothing to propose *from*); SPLIT_MODULE is the
    # one operator that can turn it into a real, >= 2-module candidate once the frontier is
    # allowed to start from it.
    policy = _search_policy(allowed_operations=(ProposalOperation.SPLIT_MODULE,))
    result = run_candidate_search_round(
        submodel,
        sub_id,
        weights,
        policy,
        _calibration_selection_policy(),
        functional_evaluation_selection_policy=_functional_selection_policy(),
        exclude_single_module_from_ranking=False,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.search_result.model_id == submodel.model_id
    assert len(result.functional_evaluation_decisions) > 0


# --- deterministic repeated execution -------------------------------------------------------------


def test_functional_evaluation_selection_is_deterministic():
    model = _kinetic_seed_model()
    weights = _functional_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()
    functional_policy = _functional_selection_policy()
    first = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        functional_evaluation_selection_policy=functional_policy,
        correlation_id="c",
        run_id="r1",
    )
    second = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        functional_evaluation_selection_policy=functional_policy,
        correlation_id="c",
        run_id="r1",
    )
    assert [d.outcome for d in first.functional_evaluation_decisions] == [
        d.outcome for d in second.functional_evaluation_decisions
    ]


# --- GENERATED/IMPORTED symmetry ------------------------------------------------------------------


def test_generated_and_imported_models_produce_identical_functional_decision_shapes():
    generated = _kinetic_seed_model()
    imported = _imported_chain_model()
    imported_with_modularization = replace(
        imported,
        modularizations=(
            ModelModularization(
                modularization_id="seed",
                name="seed",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA", "modB"),
            ),
        ),
        model_modules=(
            ModelModule(module_id="modA", name="A"),
            ModelModule(module_id="modB", name="B"),
        ),
        module_memberships=(
            _membership("modA", "r1"),
            _membership("modA", "r2"),
            _membership("modB", "r3"),
            _membership("modB", "r4"),
        ),
        module_ports=generated.module_ports,
    )
    weights = _functional_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()
    functional_policy = _functional_selection_policy()
    result_generated = run_candidate_search_round(
        generated,
        "seed",
        weights,
        policy,
        selection_policy,
        functional_evaluation_selection_policy=functional_policy,
        correlation_id="c",
        run_id="r1",
    )
    result_imported = run_candidate_search_round(
        imported_with_modularization,
        "seed",
        weights,
        policy,
        selection_policy,
        functional_evaluation_selection_policy=functional_policy,
        correlation_id="c",
        run_id="r1",
    )
    outcomes_generated = [d.outcome for d in result_generated.functional_evaluation_decisions]
    outcomes_imported = [d.outcome for d in result_imported.functional_evaluation_decisions]
    assert outcomes_generated == outcomes_imported
