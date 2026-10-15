"""Tests for the Functional Modularity Criteria from Agents 3 and 4 increment's own Agent2-side
half: ``app.agent2.module_functional_evaluation`` (request construction/serialization) and
``app.agent2.module_evaluation.functional_adapter`` (the ``DYNAMIC_ISOLATION``/``SENSITIVITY_
COHERENCE`` scoring formulas), plus their integration into ``evaluate_modularization``.

Fixture: a 4-reaction chain A -> B -> C -> D -> E (mirrors ``tests/agent2
.test_candidate_orchestration.py``'s own chain, extended with real mass-action kinetics and
explicit species memberships), split modA={r1,r2}(species A,B,C)/modB={r3,r4}(species C,D,E),
with species C declared as a boundary port on both sides.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony_import import import_antimony
from app.agent2.module_evaluation import (
    CriteriaWeights,
    CriterionWeight,
    ModularizationCriterion,
    evaluate_modularization,
)
from app.agent2.module_evaluation.functional_adapter import (
    score_dynamic_isolation,
    score_sensitivity_coherence,
)
from app.agent2.module_functional_evaluation import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationReferenceError,
    PerturbationEffectRecord,
    build_module_functional_evaluation_request,
    insufficient_targets_evaluation,
    parse_module_functional_evaluation_request,
    parse_module_functional_evaluation_result,
    select_functional_evaluation_targets,
    serialize_module_functional_evaluation_request,
    serialize_module_functional_evaluation_result,
    unsupported_analysis_evaluation,
)
from app.agent2.module_functional_evaluation.types import ModuleFunctionalEvaluationResult
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

# --- Fixtures ---------------------------------------------------------------------------------

_SUBSTRATE_BY_REACTION = {"r1": "A", "r2": "B", "r3": "C", "r4": "D"}


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
    module_id: str,
    component_type: ModuleComponentType,
    component_id: str,
    *,
    modularization_id: str = "mz-1",
) -> ModuleMembership:
    return ModuleMembership(
        membership_id=f"mem_{modularization_id}_{module_id}_{component_type.value}_{component_id}",
        modularization_id=modularization_id,
        module_id=module_id,
        component_type=component_type,
        component_id=component_id,
    )


def _chain_model(**overrides) -> ModelSpecification:
    """modA={r1,r2}(species A,B,C)/modB={r3,r4}(species C,D,E) -- C is the shared, declared
    boundary species."""
    modularization = ModelModularization(
        modularization_id="mz-1",
        name="mz-1",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
    )
    memberships = []
    for reaction_id in ("r1", "r2"):
        memberships.append(_membership("modA", ModuleComponentType.REACTION, reaction_id))
    for species_id in ("A", "B", "C"):
        memberships.append(_membership("modA", ModuleComponentType.SPECIES, species_id))
    for reaction_id in ("r3", "r4"):
        memberships.append(_membership("modB", ModuleComponentType.REACTION, reaction_id))
    for species_id in ("C", "D", "E"):
        memberships.append(_membership("modB", ModuleComponentType.SPECIES, species_id))

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
        "module_memberships": tuple(memberships),
        "module_ports": (
            ModulePort(
                port_id="port-C-modA",
                modularization_id="mz-1",
                module_id="modA",
                species_id="C",
                direction=ModulePortDirection.OUTPUT,
                externally_controlled=True,
                initial_value=Decimal("1"),
            ),
            ModulePort(
                port_id="port-C-modB",
                modularization_id="mz-1",
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
      r1: A => B; k_r1 * A;
      r2: B => C; k_r2 * B;
      r3: C => D; k_r3 * C;
      r4: D => E; k_r4 * D;
      k_r1 = 0.5;
      k_r2 = 0.5;
      k_r3 = 0.5;
      k_r4 = 0.5;
    end
    """
    imported = import_antimony(text)
    chain = _chain_model()
    return replace(
        imported,
        # Raw Antimony import never resolves reaction-parameter association on its own (that
        # is a separate, later Agent2 pipeline stage, not import itself: every imported
        # parameter's own reaction_id is None) -- carry over only the chain's own reaction_id-
        # aware parameters (never kinetic_laws too, which would break the imported network's
        # own internal reaction->kinetic_law_id cross-references) so the GENERATED/IMPORTED
        # comparison is genuinely about origin, not about a pipeline stage neither fixture ran.
        parameters=chain.parameters,
        modularizations=chain.modularizations,
        model_modules=chain.model_modules,
        module_memberships=chain.module_memberships,
        module_ports=chain.module_ports,
    )


# --- select_functional_evaluation_targets / build_module_functional_evaluation_request --------


def test_select_functional_evaluation_targets_splits_internal_and_external():
    model = _chain_model()
    targets = select_functional_evaluation_targets(model, "mz-1", "modA")
    internal_ids = {t.target_id for t in targets if t.is_internal}
    external_ids = {t.target_id for t in targets if not t.is_internal}
    assert internal_ids == {"k_r1", "k_r2"}
    assert external_ids == {"k_r3", "k_r4"}


def test_select_functional_evaluation_targets_is_deterministic():
    model = _chain_model()
    first = select_functional_evaluation_targets(model, "mz-1", "modA")
    second = select_functional_evaluation_targets(model, "mz-1", "modA")
    assert first == second


def test_build_request_succeeds_for_an_executable_whole_network():
    model = _chain_model()
    request = build_module_functional_evaluation_request(
        model, "mz-1", "modA", correlation_id="corr-1", run_id="run-1"
    )
    assert request.parent_model_id == "m1"
    assert request.whole_network_handoff["antimony_text"]
    assert request.internal_species_ids == ("A", "B", "C")
    assert request.boundary_species_ids == ("C",)
    assert any(t.target_id == "k_r1" and t.is_internal for t in request.perturbation_targets)
    assert any(t.target_id == "k_r3" and not t.is_internal for t in request.perturbation_targets)


def test_build_request_raises_for_non_executable_whole_network():
    # r1's own kinetic law is left genuinely UNASSIGNED (never merely omitted -- the real
    # pipeline always produces some law per reaction, even an unresolved one) -- makes the
    # whole network NON_EXECUTABLE_UNRESOLVED_KINETICS.
    unassigned_r1 = KineticLawSpecification(
        kinetic_law_id="kl-r1",
        reaction_id="r1",
        law_type=KineticLawType.UNASSIGNED,
        assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        expression=None,
        parameter_ids=(),
        species_ids=(),
    )
    model = _chain_model(
        kinetic_laws=(unassigned_r1, *(_kinetic_law(r) for r in ("r2", "r3", "r4"))),
        parameters=tuple(_parameter(r) for r in ("r2", "r3", "r4")),
    )
    with pytest.raises(ModuleFunctionalEvaluationReferenceError):
        build_module_functional_evaluation_request(
            model, "mz-1", "modA", correlation_id="corr-1", run_id="run-1"
        )


def test_build_request_raises_for_insufficient_targets():
    # A single-reaction module has only 1 internal parameter -- below MIN_INTERNAL_TARGETS=2.
    model = _chain_model()
    small_modularization = ModelModularization(
        modularization_id="mz-2",
        name="mz-2",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modSmall", "modRest"),
    )
    memberships = [
        _membership("modSmall", ModuleComponentType.REACTION, "r1", modularization_id="mz-2"),
        _membership("modSmall", ModuleComponentType.SPECIES, "A", modularization_id="mz-2"),
        _membership("modSmall", ModuleComponentType.SPECIES, "B", modularization_id="mz-2"),
    ]
    for r in ("r2", "r3", "r4"):
        memberships.append(
            _membership("modRest", ModuleComponentType.REACTION, r, modularization_id="mz-2")
        )
    for s in ("C", "D", "E"):
        memberships.append(
            _membership("modRest", ModuleComponentType.SPECIES, s, modularization_id="mz-2")
        )
    model = replace(
        model,
        modularizations=(*model.modularizations, small_modularization),
        model_modules=(
            *model.model_modules,
            ModelModule(module_id="modSmall", name="Small"),
            ModelModule(module_id="modRest", name="Rest"),
        ),
        module_memberships=(*model.module_memberships, *memberships),
    )
    with pytest.raises(ModuleFunctionalEvaluationReferenceError):
        build_module_functional_evaluation_request(
            model, "mz-2", "modSmall", correlation_id="corr-1", run_id="run-1"
        )


def test_build_request_never_mutates_canonical_model():
    model = _chain_model()
    before = replace(model)
    build_module_functional_evaluation_request(
        model, "mz-1", "modA", correlation_id="corr-1", run_id="run-1"
    )
    assert model == before


def test_unsupported_analysis_evaluation_is_disclosed_not_an_error():
    evaluation = unsupported_analysis_evaluation(
        parent_model_id="m1",
        modularization_id="mz-1",
        module_id="modA",
        reason="no eligible artifact",
        request_id="req-1",
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert evaluation.status is FunctionalEvaluationStatus.UNSUPPORTED_ANALYSIS
    assert evaluation.perturbation_effects == ()


def test_insufficient_targets_evaluation_is_disclosed_not_an_error():
    evaluation = insufficient_targets_evaluation(
        parent_model_id="m1",
        modularization_id="mz-1",
        module_id="modA",
        reason="too few targets",
        request_id="req-1",
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert evaluation.status is FunctionalEvaluationStatus.INSUFFICIENT_TARGETS
    assert evaluation.perturbation_effects == ()


# --- Serialization round trips ------------------------------------------------------------------


def test_request_serialization_round_trips():
    model = _chain_model()
    request = build_module_functional_evaluation_request(
        model, "mz-1", "modA", correlation_id="corr-1", run_id="run-1"
    )
    payload = serialize_module_functional_evaluation_request(request)
    parsed = parse_module_functional_evaluation_request(payload)
    assert parsed == request


def test_result_serialization_round_trips():
    result = ModuleFunctionalEvaluationResult(
        evaluation_id="eval-1",
        request_id="req-1",
        correlation_id="corr-1",
        run_id="run-1",
        parent_model_id="m1",
        modularization_id="mz-1",
        module_id="modA",
        status=FunctionalEvaluationStatus.EVALUATED,
        policy_version="test-v1",
        perturbation_effects=(
            PerturbationEffectRecord(
                target_kind="PARAMETER",
                target_id="k_r1",
                is_internal=True,
                simulation_status="SUCCESS",
                remained_numerically_stable=True,
                relative_change_by_species=(("A", Decimal("0.5")), ("B", Decimal("0.3"))),
            ),
        ),
    )
    payload = serialize_module_functional_evaluation_result(result)
    parsed = parse_module_functional_evaluation_result(payload)
    assert parsed == result


# --- functional_adapter: formulas ----------------------------------------------------------------


def _effect(target_id: str, is_internal: bool, changes: dict[str, str]) -> PerturbationEffectRecord:
    return PerturbationEffectRecord(
        target_kind="PARAMETER",
        target_id=target_id,
        is_internal=is_internal,
        simulation_status="SUCCESS",
        remained_numerically_stable=True,
        relative_change_by_species=tuple(sorted((k, Decimal(v)) for k, v in changes.items())),
    )


def _result(effects: list[PerturbationEffectRecord]) -> ModuleFunctionalEvaluationResult:
    return ModuleFunctionalEvaluationResult(
        evaluation_id="e",
        request_id="r",
        correlation_id="c",
        run_id="run",
        parent_model_id="m",
        modularization_id="mz",
        module_id="mod",
        status=FunctionalEvaluationStatus.EVALUATED,
        policy_version="v1",
        perturbation_effects=tuple(effects),
    )


_ISOLATED_RESULT = _result(
    [
        _effect("k1", True, {"A": "0.5", "B": "0.4", "C": "0.001", "D": "0.001"}),
        _effect("k2", True, {"A": "0.3", "B": "0.35", "C": "0.001", "D": "0.001"}),
        _effect("k3", False, {"A": "0.001", "B": "0.02", "C": "0.4", "D": "0.3"}),
    ]
)
_COUPLED_RESULT = _result(
    [
        _effect("k1", True, {"A": "0.5", "B": "0.4", "C": "0.45", "D": "0.4"}),
        _effect("k2", True, {"A": "0.3", "B": "0.35", "C": "0.3", "D": "0.35"}),
        _effect("k3", False, {"A": "0.4", "B": "0.02", "C": "0.4", "D": "0.3"}),
    ]
)
_INTERNAL_SPECIES = {"mod": frozenset({"A", "B"})}
_BOUNDARY_SPECIES = {"mod": frozenset({"B"})}


def test_dynamically_isolated_module_scores_high():
    result = score_dynamic_isolation(
        ("mod",), {"mod": _ISOLATED_RESULT}, _INTERNAL_SPECIES, _BOUNDARY_SPECIES
    )
    assert result.available is True
    assert result.raw_score > Decimal("0.9")


def test_strongly_coupled_module_scores_low():
    result = score_dynamic_isolation(
        ("mod",), {"mod": _COUPLED_RESULT}, _INTERNAL_SPECIES, _BOUNDARY_SPECIES
    )
    assert result.available is True
    assert result.raw_score < Decimal("0.5")


def test_sensitivity_coherent_grouping_scores_higher_than_incoherent():
    coherent = score_sensitivity_coherence(("mod",), {"mod": _ISOLATED_RESULT}, _INTERNAL_SPECIES)
    incoherent = score_sensitivity_coherence(("mod",), {"mod": _COUPLED_RESULT}, _INTERNAL_SPECIES)
    assert coherent.available is True
    assert incoherent.available is True
    assert coherent.raw_score > incoherent.raw_score


def test_unavailable_evidence_handling_missing_module():
    result = score_dynamic_isolation(
        ("mod", "mod2"), {"mod": _ISOLATED_RESULT}, _INTERNAL_SPECIES, _BOUNDARY_SPECIES
    )
    assert result.available is False
    assert result.detail.module_ids_missing_evidence == ("mod2",)


def test_unavailable_evidence_handling_unsupported_status():
    unsupported = ModuleFunctionalEvaluationResult(
        evaluation_id="e",
        request_id="r",
        correlation_id="c",
        run_id="run",
        parent_model_id="m",
        modularization_id="mz",
        module_id="mod",
        status=FunctionalEvaluationStatus.UNSUPPORTED_ANALYSIS,
        policy_version="v1",
    )
    result = score_dynamic_isolation(
        ("mod",), {"mod": unsupported}, _INTERNAL_SPECIES, _BOUNDARY_SPECIES
    )
    assert result.available is False


def test_unavailable_evidence_handling_insufficient_internal_targets():
    only_one_internal = _result(
        [
            _effect("k1", True, {"A": "0.5", "B": "0.4"}),
            _effect("k3", False, {"A": "0.01", "B": "0.02"}),
        ]
    )
    result = score_sensitivity_coherence(("mod",), {"mod": only_one_internal}, _INTERNAL_SPECIES)
    assert result.available is False


# --- evaluate_modularization integration --------------------------------------------------------


def _functional_weights(**overrides) -> CriteriaWeights:
    merged = {
        "weights": (
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.SENSITIVITY_COHERENCE, Decimal("1")),
        ),
        "policy_version": "test-v1",
    } | overrides
    return CriteriaWeights(**merged)


def test_evaluate_modularization_threads_functional_evidence():
    model = _chain_model()
    weights = _functional_weights()
    evidence = {"modA": _ISOLATED_RESULT, "modB": _ISOLATED_RESULT}
    evaluation = evaluate_modularization(
        model, "mz-1", weights, functional_evaluation_evidence=evidence
    )
    criteria = {cs.criterion for cs in evaluation.criterion_scores}
    assert ModularizationCriterion.DYNAMIC_ISOLATION in criteria
    assert ModularizationCriterion.SENSITIVITY_COHERENCE in criteria
    assert evaluation.overall_score is not None


def test_weight_zero_reproduces_prior_behavior():
    model = _chain_model()
    weights_zero = CriteriaWeights(
        weights=(
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("0")),
        ),
        policy_version="test-v1",
    )
    without_evidence = evaluate_modularization(model, "mz-1", weights_zero)
    with_evidence = evaluate_modularization(
        model,
        "mz-1",
        weights_zero,
        functional_evaluation_evidence={"modA": _ISOLATED_RESULT, "modB": _ISOLATED_RESULT},
    )
    assert without_evidence.overall_score == with_evidence.overall_score


def test_functional_criteria_change_candidate_ranking():
    model = _chain_model()
    weights = _functional_weights()
    isolated_evidence = {"modA": _ISOLATED_RESULT, "modB": _ISOLATED_RESULT}
    coupled_evidence = {"modA": _COUPLED_RESULT, "modB": _COUPLED_RESULT}
    isolated_eval = evaluate_modularization(
        model, "mz-1", weights, functional_evaluation_evidence=isolated_evidence
    )
    coupled_eval = evaluate_modularization(
        model, "mz-1", weights, functional_evaluation_evidence=coupled_evidence
    )
    assert isolated_eval.overall_score > coupled_eval.overall_score


def test_calibration_dynamic_and_sensitivity_combine_correctly():
    from app.agent2.module_calibration.types import (
        ModuleCalibrationEvaluation,
        ModuleCalibrationStatus,
    )

    model = _chain_model()
    weights = CriteriaWeights(
        weights=(
            CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),
            CriterionWeight(ModularizationCriterion.DYNAMIC_ISOLATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.SENSITIVITY_COHERENCE, Decimal("1")),
        ),
        policy_version="test-v1",
    )

    def _calib(module_id: str) -> ModuleCalibrationEvaluation:
        return ModuleCalibrationEvaluation(
            evaluation_id=f"eval::{module_id}",
            request_id=f"req::{module_id}",
            correlation_id="c",
            run_id="r",
            parent_model_id="m1",
            modularization_id="mz-1",
            module_id=module_id,
            status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
            policy_version="test-v1",
        )

    evaluation = evaluate_modularization(
        model,
        "mz-1",
        weights,
        calibration_evidence={"modA": _calib("modA"), "modB": _calib("modB")},
        functional_evaluation_evidence={"modA": _ISOLATED_RESULT, "modB": _ISOLATED_RESULT},
    )
    criteria = {cs.criterion: cs for cs in evaluation.criterion_scores}
    assert criteria[ModularizationCriterion.CALIBRATION_INDEPENDENCE].available
    assert criteria[ModularizationCriterion.DYNAMIC_ISOLATION].available
    assert criteria[ModularizationCriterion.SENSITIVITY_COHERENCE].available
    assert evaluation.overall_score is not None
    # All three criteria contributed -- evaluated_weight_fraction covers all of them.
    # Three equal-weighted criteria -- Decimal division of 1/3 three times does not sum back
    # to exactly 1 at this policy's own precision; close enough is the real, expected result.
    assert abs(evaluation.evaluated_weight_fraction - Decimal("1")) < Decimal("1e-20")


def test_generated_and_imported_models_produce_identical_available_targets():
    generated = _chain_model()
    imported = _imported_chain_model()
    generated_targets = select_functional_evaluation_targets(generated, "mz-1", "modA")
    imported_targets = select_functional_evaluation_targets(imported, "mz-1", "modA")
    assert [(t.target_kind, t.target_id, t.is_internal) for t in generated_targets] == [
        (t.target_kind, t.target_id, t.is_internal) for t in imported_targets
    ]


def test_recursive_submodel_compatibility():
    """``build_module_functional_evaluation_request`` must work identically whether ``model``
    is the whole canonical network or itself a previously-derived submodel re-assembled as its
    own ``ModelSpecification`` (recursive readiness) -- no origin-specific branch anywhere."""
    whole = _chain_model()
    submodel = ModelSpecification(
        model_id="submodel::mz-1::modA",
        name="submodel",
        full_network=whole.full_network,
        kinetic_laws=whole.kinetic_laws,
        parameters=whole.parameters,
        modularizations=(
            ModelModularization(
                modularization_id="mz-sub",
                name="mz-sub",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA2", "modB2"),
            ),
        ),
        model_modules=(
            ModelModule(module_id="modA2", name="A2"),
            ModelModule(module_id="modB2", name="B2"),
        ),
        module_memberships=(
            _membership("modA2", ModuleComponentType.REACTION, "r1", modularization_id="mz-sub"),
            _membership("modA2", ModuleComponentType.REACTION, "r2", modularization_id="mz-sub"),
            _membership("modA2", ModuleComponentType.SPECIES, "A", modularization_id="mz-sub"),
            _membership("modA2", ModuleComponentType.SPECIES, "B", modularization_id="mz-sub"),
            _membership("modA2", ModuleComponentType.SPECIES, "C", modularization_id="mz-sub"),
            _membership("modB2", ModuleComponentType.REACTION, "r3", modularization_id="mz-sub"),
            _membership("modB2", ModuleComponentType.REACTION, "r4", modularization_id="mz-sub"),
            _membership("modB2", ModuleComponentType.SPECIES, "D", modularization_id="mz-sub"),
            _membership("modB2", ModuleComponentType.SPECIES, "E", modularization_id="mz-sub"),
        ),
    )
    request = build_module_functional_evaluation_request(
        submodel, "mz-sub", "modA2", correlation_id="c", run_id="r1"
    )
    assert request.parent_model_id == "submodel::mz-1::modA"
    assert request.internal_species_ids == ("A", "B", "C")
