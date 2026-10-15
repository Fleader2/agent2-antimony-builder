"""Tests for the Recursive Agent-4-Assisted Candidate Search Orchestration increment's own
Agent2-side half: ``app.agent2.candidate_orchestration``.

Fixture style mirrors ``tests/agent2/test_modularization_search.py``'s own chain network
(A -> B -> C -> D -> E, seed modA={r1,r2}/modB={r3,r4}) exactly, so results can be hand-verified.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony_import import import_antimony
from app.agent2.candidate_orchestration import (
    CalibrationDecisionOutcome,
    CalibrationSelectionPolicy,
    build_submodel,
    could_change_ordering,
    run_candidate_search_round,
    serialize_round_result,
)
from app.agent2.candidate_orchestration.errors import CandidateOrchestrationReferenceError
from app.agent2.modularization_search import (
    ProposalOperation,
    SearchPolicy,
    extract_bundle,
    module_content_key,
)
from app.agent2.modularization_search.assembly import canonicalize_bundle
from app.agent2.module_calibration.types import ModuleCalibrationEvaluation, ModuleCalibrationStatus
from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
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

# --- Fixtures (mirrors tests/agent2/test_modularization_search.py) --------------------------------


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
    """modA={r1,r2}, modB={r3,r4} -- the chain's own natural, contiguous split. No declared
    ``ModulePort`` -- every module is ineligible for a real standalone artifact (VIEW_ONLY),
    so any calibration attempt resolves locally as ``BOUNDARY_INADEQUATE``."""
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


_SUBSTRATE_BY_REACTION = {"r1": "A", "r2": "B", "r3": "C", "r4": "D"}


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


def _kinetic_seed_model(**overrides) -> ModelSpecification:
    """The identical chain/seed topology as ``_seed_model``, but with a real mass-action
    kinetic law and parameter for every reaction, plus one already-declared, genuinely
    ``externally_controlled`` boundary port on the shared species "C" -- so each module's own
    standalone Antimony artifact is genuinely ``EXECUTABLE`` (``_seed_model`` alone has no
    kinetics and no eligible boundary at all, so every module stays ``VIEW_ONLY`` regardless).
    Mirrors ``tests/agent2/test_module_calibration.py``'s own ``_eligible_model`` convention:
    only a real ``externally_controlled`` port -- never one ``ADD_BOUNDARY`` itself declares,
    which is deliberately scoring-only (``has_explicit_boundary_treatment`` in ``app.agent2
    .antimony.generator`` requires ``externally_controlled``, which that operator never sets)
    -- makes a module eligible."""
    merged = {
        "kinetic_laws": tuple(_kinetic_law(r) for r in ("r1", "r2", "r3", "r4")),
        "parameters": tuple(_parameter(r) for r in ("r1", "r2", "r3", "r4")),
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
    return _seed_model(**merged)


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


def _blended_weights(*, calibration_weight: Decimal = Decimal("0.5")) -> CriteriaWeights:
    return CriteriaWeights(
        weights=(
            CriterionWeight(
                ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1") - calibration_weight
            ),
            CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, calibration_weight),
        ),
        policy_version="test-v1",
    )


def _search_policy(**overrides) -> SearchPolicy:
    merged = {
        "max_iterations": 2,
        "max_candidates_per_iteration": 50,
        "beam_width": 10,
        "allowed_operations": (ProposalOperation.MOVE_REACTION, ProposalOperation.ADD_BOUNDARY),
        "policy_version": "test-v1",
    } | overrides
    return SearchPolicy(**merged)


def _calibration_selection_policy(**overrides) -> CalibrationSelectionPolicy:
    merged = {
        "max_candidates_per_generation": 10,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_calibration_run_budget": 1000,
        "policy_version": "test-v1",
    } | overrides
    return CalibrationSelectionPolicy(**merged)


def _evaluation_dict(status: ModuleCalibrationStatus) -> ModuleCalibrationEvaluation:
    return ModuleCalibrationEvaluation(
        evaluation_id="eval-1",
        request_id="req-1",
        correlation_id="corr-1",
        run_id="run-1",
        parent_model_id="m1",
        modularization_id="seed",
        module_id="placeholder",
        status=status,
        policy_version="test-v1",
    )


# --- select_candidates_for_calibration: structural pre-filter ---------------------------------


def test_structural_prefilter_prevents_unnecessary_calibration():
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy(score_threshold=Decimal("0.99"))
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.calibration_requests == ()
    assert result.locally_resolved_evidence == ()
    assert all(
        d.outcome is CalibrationDecisionOutcome.SKIP_BELOW_SCORE_THRESHOLD
        for d in result.calibration_decisions
    )
    assert len(result.calibration_decisions) > 0


def test_calibration_budget_enforced():
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy(total_calibration_run_budget=1)
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    calibrate_decisions = [
        d for d in result.calibration_decisions if d.outcome is CalibrationDecisionOutcome.CALIBRATE
    ]
    assert len(calibrate_decisions) == 1
    assert any(
        d.outcome is CalibrationDecisionOutcome.SKIP_TOTAL_BUDGET_EXHAUSTED
        for d in result.calibration_decisions
    )


def test_max_candidates_per_generation_enforced():
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy(max_candidates_per_generation=1)
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    calibrated_candidates = {
        d.candidate_id
        for d in result.calibration_decisions
        if d.outcome is CalibrationDecisionOutcome.CALIBRATE
    }
    assert len(calibrated_candidates) <= 1
    assert any(
        d.outcome is CalibrationDecisionOutcome.SKIP_CANDIDATE_BUDGET_EXHAUSTED
        for d in result.calibration_decisions
    )


def test_max_modules_per_candidate_enforced():
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy(max_modules_per_candidate=1)
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    by_candidate: dict[str, int] = {}
    for d in result.calibration_decisions:
        if d.outcome is CalibrationDecisionOutcome.CALIBRATE:
            by_candidate[d.candidate_id] = by_candidate.get(d.candidate_id, 0) + 1
    assert all(count <= 1 for count in by_candidate.values())
    assert any(
        d.outcome is CalibrationDecisionOutcome.SKIP_MODULE_LIMIT_REACHED
        for d in result.calibration_decisions
    )


def test_already_evidenced_modules_are_skipped():
    model = _seed_model()
    bundle = canonicalize_bundle(extract_bundle(model, "seed"))
    weights = _topology_weights()
    # REMOVE_BOUNDARY can produce nothing from a seed with no declared ports -- the search
    # retains only the (canonicalized) seed itself, with no further generations.
    policy = _search_policy(allowed_operations=(ProposalOperation.REMOVE_BOUNDARY,))
    selection_policy = _calibration_selection_policy()
    # "Already evidenced" is derived from calibration_evidence's own keys (content-addressed),
    # never a separately-tracked, independently-passed set -- an entry here, regardless of its
    # own disclosed outcome, is still a real, already-spent attempt.
    evidence = {
        module_content_key(bundle.memberships, m.module_id): _evaluation_dict(
            ModuleCalibrationStatus.INSUFFICIENT_DATA
        )
        for m in bundle.modules
    }
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        calibration_evidence=evidence,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert all(
        d.outcome is CalibrationDecisionOutcome.SKIP_ALREADY_EVIDENCED
        for d in result.calibration_decisions
    )


def test_degenerate_candidates_are_excluded_upstream_by_default_never_even_gated():
    """With the default ``exclude_single_module_from_ranking=True``,
    ``search_candidate_modularizations`` itself already removes a one-module merge from
    ``.retained`` into ``.degenerate`` -- ``select_candidates_for_calibration`` only ever
    iterates ``.retained``, so no decision is ever recorded for a degenerate candidate at all
    (never wasted bookkeeping for something already excluded one layer below)."""
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    selection_policy = _calibration_selection_policy()
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.search_result.degenerate  # the 1-module merge really was produced
    degenerate_ids = {b.modularization.modularization_id for b in result.search_result.degenerate}
    assert not any(d.candidate_id in degenerate_ids for d in result.calibration_decisions)


def test_degenerate_candidate_skipped_even_when_override_lets_it_into_retained():
    """A defense-in-depth check: if a caller passes ``exclude_single_module_from_ranking=
    False`` (restoring the search's own pre-degenerate-policy behavior, letting a one-module
    candidate compete normally and appear in ``.retained``), this package's own gate still
    never wastes a calibration run on it."""
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MERGE_MODULES,))
    selection_policy = _calibration_selection_policy()
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        exclude_single_module_from_ranking=False,
        correlation_id="corr-1",
        run_id="run-1",
    )
    one_module_candidate_ids = {
        b.modularization.modularization_id
        for b in result.search_result.retained
        if len(b.modules) == 1
    }
    assert one_module_candidate_ids
    decisions_for_those = [
        d for d in result.calibration_decisions if d.candidate_id in one_module_candidate_ids
    ]
    assert decisions_for_those
    assert all(
        d.outcome is CalibrationDecisionOutcome.SKIP_DEGENERATE_CANDIDATE
        for d in decisions_for_those
    )


# --- could_change_ordering ----------------------------------------------------------------------


def test_could_change_ordering_zero_weight_never_selects():
    assert (
        could_change_ordering(
            current_score=Decimal("0.5"),
            neighbor_scores=(Decimal("0.5001"),),
            remaining_calibration_weight=Decimal("0"),
        )
        is False
    )


def test_could_change_ordering_selects_when_gap_within_remaining_weight():
    assert (
        could_change_ordering(
            current_score=Decimal("0.5"),
            neighbor_scores=(Decimal("0.6"),),
            remaining_calibration_weight=Decimal("0.5"),
        )
        is True
    )


def test_could_change_ordering_unavailable_score_always_true():
    assert (
        could_change_ordering(
            current_score=None,
            neighbor_scores=(Decimal("0.9"),),
            remaining_calibration_weight=Decimal("0"),
        )
        is True
    )


def test_only_if_could_change_ordering_skips_when_calibration_weight_is_zero():
    model = _seed_model()
    weights = _topology_weights()  # no CALIBRATION_INDEPENDENCE weight at all
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy(only_if_could_change_ordering=True)
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert not any(
        d.outcome is CalibrationDecisionOutcome.CALIBRATE for d in result.calibration_decisions
    )
    assert any(
        d.outcome is CalibrationDecisionOutcome.SKIP_COULD_NOT_CHANGE_ORDERING
        for d in result.calibration_decisions
    )


# --- build_calibration_requests: eligible vs. BOUNDARY_INADEQUATE -------------------------------


def test_calibration_round_resolves_boundary_inadequate_locally_when_no_port_declared():
    model = _seed_model()  # no ModulePort declared anywhere, and no kinetic laws at all
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.REMOVE_BOUNDARY,))
    selection_policy = _calibration_selection_policy()
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert result.calibration_requests == ()
    assert len(result.locally_resolved_evidence) == 2  # modA and modB, both ineligible
    assert all(
        e.status is ModuleCalibrationStatus.BOUNDARY_INADEQUATE
        for e in result.locally_resolved_evidence
    )


def test_calibration_round_builds_a_real_request_once_a_boundary_is_declared():
    model = _kinetic_seed_model()
    weights = _topology_weights()
    # MOVE_REACTION never touches port declarations -- the seed's own already-declared,
    # externally_controlled port on "C" survives unchanged (content-addressed port survival).
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()
    result = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert len(result.calibration_requests) > 0
    envelope = result.calibration_requests[0]
    assert envelope.request.module_handoff["antimony_text"]
    assert envelope.decision.outcome is CalibrationDecisionOutcome.CALIBRATE


# --- Calibration reverses ranking (round-to-round, via accumulated evidence) --------------------


def test_calibration_evidence_reverses_candidate_ranking_across_rounds():
    model = _seed_model()
    weights = _blended_weights(calibration_weight=Decimal("0.9"))
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()

    round1 = run_candidate_search_round(
        model, "seed", weights, policy, selection_policy, correlation_id="corr-1", run_id="run-1"
    )
    ranked_without_evidence = sorted(
        zip(round1.search_result.retained, round1.search_result.evaluations, strict=True),
        key=lambda item: (
            item[1].overall_score is None,
            -(item[1].overall_score) if item[1].overall_score is not None else Decimal(0),
        ),
    )
    top_without_evidence = ranked_without_evidence[0][0].modularization.modularization_id

    # Fabricate evidence making every OTHER candidate's own modules perfectly calibrated and
    # the previous top candidate's own modules UNIDENTIFIABLE (the worst score) -- forcing a
    # ranking reversal on round 2.
    evidence = {}
    for bundle, _ev in ranked_without_evidence:
        status = (
            ModuleCalibrationStatus.UNIDENTIFIABLE
            if bundle.modularization.modularization_id == top_without_evidence
            else ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        )
        for module in bundle.modules:
            key = module_content_key(bundle.memberships, module.module_id)
            evidence[key] = ModuleCalibrationEvaluation(
                evaluation_id=f"eval::{module.module_id}",
                request_id=f"req::{module.module_id}",
                correlation_id="corr-1",
                run_id="run-1",
                parent_model_id="m1",
                modularization_id=bundle.modularization.modularization_id,
                module_id=module.module_id,
                status=status,
                policy_version="test-v1",
            )

    round2 = run_candidate_search_round(
        model,
        "seed",
        weights,
        policy,
        selection_policy,
        calibration_evidence=evidence,
        correlation_id="corr-1",
        run_id="run-2",
    )
    ranked_with_evidence = sorted(
        zip(round2.search_result.retained, round2.search_result.evaluations, strict=True),
        key=lambda item: (
            item[1].overall_score is None,
            -(item[1].overall_score) if item[1].overall_score is not None else Decimal(0),
        ),
    )
    top_with_evidence = ranked_with_evidence[0][0].modularization.modularization_id
    assert top_with_evidence != top_without_evidence


# --- Recursive/submodel invocation --------------------------------------------------------------


def test_build_submodel_is_usable_by_the_same_round_function():
    model = _seed_model()
    submodel, sub_id = build_submodel(model, "seed", "modA")
    assert submodel.modularizations[0].module_ids == ("modA",)
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()
    result = run_candidate_search_round(
        submodel, sub_id, weights, policy, selection_policy, correlation_id="corr-1", run_id="run-1"
    )
    assert result.search_result.model_id == submodel.model_id


def test_build_submodel_rejects_unknown_module_id():
    model = _seed_model()
    with pytest.raises(CandidateOrchestrationReferenceError):
        build_submodel(model, "seed", "does-not-exist")


# --- GENERATED/IMPORTED symmetry and no-mutation ------------------------------------------------


def test_generated_and_imported_models_produce_identical_decision_shapes():
    generated = _seed_model()
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
    )
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=(ProposalOperation.MOVE_REACTION,))
    selection_policy = _calibration_selection_policy()
    result_generated = run_candidate_search_round(
        generated, "seed", weights, policy, selection_policy, correlation_id="c", run_id="r1"
    )
    result_imported = run_candidate_search_round(
        imported_with_modularization,
        "seed",
        weights,
        policy,
        selection_policy,
        correlation_id="c",
        run_id="r1",
    )
    outcomes_generated = [d.outcome for d in result_generated.calibration_decisions]
    outcomes_imported = [d.outcome for d in result_imported.calibration_decisions]
    assert outcomes_generated == outcomes_imported


_MOVE_AND_ADD_BOUNDARY = (ProposalOperation.MOVE_REACTION, ProposalOperation.ADD_BOUNDARY)


def test_run_candidate_search_round_never_mutates_canonical_model():
    model = _seed_model()
    before = replace(model)
    run_candidate_search_round(
        model,
        "seed",
        _topology_weights(),
        _search_policy(allowed_operations=_MOVE_AND_ADD_BOUNDARY),
        _calibration_selection_policy(),
        correlation_id="c",
        run_id="r1",
    )
    assert model == before


def test_run_candidate_search_round_is_deterministic():
    model = _seed_model()
    weights = _topology_weights()
    policy = _search_policy(allowed_operations=_MOVE_AND_ADD_BOUNDARY)
    selection_policy = _calibration_selection_policy()
    first = run_candidate_search_round(
        model, "seed", weights, policy, selection_policy, correlation_id="c", run_id="r1"
    )
    second = run_candidate_search_round(
        model, "seed", weights, policy, selection_policy, correlation_id="c", run_id="r1"
    )
    assert [d.outcome for d in first.calibration_decisions] == [
        d.outcome for d in second.calibration_decisions
    ]
    assert [ev.overall_score for ev in first.search_result.evaluations] == [
        ev.overall_score for ev in second.search_result.evaluations
    ]


# --- serialize_round_result -----------------------------------------------------------------------


def test_serialize_round_result_is_json_shaped():
    import json

    model = _seed_model()
    result = run_candidate_search_round(
        model,
        "seed",
        _topology_weights(),
        _search_policy(allowed_operations=(ProposalOperation.ADD_BOUNDARY,)),
        _calibration_selection_policy(),
        correlation_id="c",
        run_id="r1",
    )
    payload = serialize_round_result(result)
    encoded = json.dumps(payload)  # raises if anything is not JSON-serializable
    assert json.loads(encoded)["search_id"] == result.search_result.search_id
    assert len(payload["calibration_requests"]) == len(result.calibration_requests)


def test_serialize_round_result_content_key_round_trips_to_the_identical_module():
    """The serialized ``content_key`` for a calibration decision/request/locally-resolved
    evidence entry must reconstruct the identical ``ModuleContentKey`` a caller would need to
    supply back as the next round's own ``calibration_evidence`` key."""
    model = _seed_model()
    bundle = canonicalize_bundle(extract_bundle(model, "seed"))
    result = run_candidate_search_round(
        model,
        "seed",
        _topology_weights(),
        _search_policy(allowed_operations=(ProposalOperation.REMOVE_BOUNDARY,)),
        _calibration_selection_policy(),
        correlation_id="c",
        run_id="r1",
    )
    payload = serialize_round_result(result)
    for decision in payload["calibration_decisions"]:
        reconstructed = frozenset((t, c) for t, c in decision["content_key"])
        expected = module_content_key(bundle.memberships, decision["module_id"])
        assert reconstructed == expected
