"""Tests for Recursive Module Evaluation Orchestration: ``app.agent2.module_calibration`` and
its companion ``app.agent2.module_evaluation.calibration_adapter``/``evaluate_modularization``
integration and ``app.agent2.pipeline.build_module_downstream_handoff``.

Fixture style mirrors ``tests/agent2/test_antimony_generation.py``'s own standalone-module-
eligibility fixtures exactly (single reaction ``a => b``, module ``mod-1`` = {r1, a, b, k1},
one ``externally_controlled`` ``ModulePort`` on species ``a``) -- the proven, already-tested
shape ``generate_module_artifacts`` turns into a real ``EXECUTABLE`` standalone artifact.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony import generate_antimony
from app.agent2.antimony_import import import_antimony
from app.agent2.module_calibration import (
    ModuleCalibrationContractError,
    ModuleCalibrationEvaluation,
    ModuleCalibrationReferenceError,
    ModuleCalibrationStatus,
    boundary_inadequate_evaluation,
    build_module_calibration_request,
    parse_module_calibration_evaluation,
    parse_module_calibration_request,
    serialize_module_calibration_request,
)
from app.agent2.module_calibration.types import (
    FitQualitySummary,
    IdentifiabilityFindingSummary,
)
from app.agent2.module_evaluation import (
    CriteriaWeights,
    CriterionWeight,
    ModularizationCriterion,
    evaluate_modularization,
)
from app.agent2.module_evaluation.calibration_adapter import score_calibration_independence
from app.agent2.pipeline import build_module_downstream_handoff
from app.agent2.types import (
    Agent2OutputPackage,
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
from app.agent2.version import MODULE_CALIBRATION_POLICY_VERSION

# --- Fixtures (mirrors tests/agent2/test_antimony_generation.py) --------------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "cyto",
        "name": "cyto",
        "source_scope": CompartmentSourceScope.AGENT1_CURATED,
        "source_entity_id": "agent1-c1",
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    species_id = overrides.get("species_id", "a")
    merged = {"species_id": species_id, "name": species_id, "compartment_id": "cyto"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "a",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "r1",
        "participants": (
            _participant(species_id="a", role=ParticipantRole.REACTANT),
            _participant(species_id="b", role=ParticipantRole.PRODUCT),
        ),
        "reversible": False,
    } | overrides
    return ReactionSpecification(**merged)


def _network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "test network",
        "compartments": (_compartment(),),
        "species": (_species(species_id="a"), _species(species_id="b")),
        "reactions": (_reaction(),),
    } | overrides
    return FullNetwork(**merged)


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "k1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": "k1 * a",
        "parameter_ids": ("k1",),
        "species_ids": ("a",),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    merged = {
        "parameter_id": "k1",
        "name": "k1",
        "source": ParameterSource.CURATED,
        "value": Decimal("0.5"),
        "reaction_id": "r1",
    } | overrides
    return ParameterSpecification(**merged)


def _modularization(**overrides) -> ModelModularization:
    merged = {
        "modularization_id": "mz-1",
        "name": "test modularization",
        "method": ModularizationMethod.USER_DEFINED,
        "module_ids": ("mod-1",),
    } | overrides
    return ModelModularization(**merged)


def _model_module(**overrides) -> ModelModule:
    merged = {"module_id": "mod-1", "name": "test module"} | overrides
    return ModelModule(**merged)


def _memberships_for(
    module_id: str,
    *,
    modularization_id: str = "mz-1",
    reaction_ids: tuple[str, ...] = (),
    species_ids: tuple[str, ...] = (),
    parameter_ids: tuple[str, ...] = (),
) -> tuple[ModuleMembership, ...]:
    memberships = []
    for component_type, ids in (
        (ModuleComponentType.REACTION, reaction_ids),
        (ModuleComponentType.SPECIES, species_ids),
        (ModuleComponentType.PARAMETER, parameter_ids),
    ):
        for component_id in ids:
            memberships.append(
                ModuleMembership(
                    membership_id=(
                        f"membership::{modularization_id}::{module_id}::"
                        f"{component_type.value}::{component_id}"
                    ),
                    modularization_id=modularization_id,
                    module_id=module_id,
                    component_type=component_type,
                    component_id=component_id,
                )
            )
    return tuple(memberships)


def _port(**overrides) -> ModulePort:
    merged = {
        "port_id": "port-1",
        "modularization_id": "mz-1",
        "module_id": "mod-1",
        "species_id": "a",
        "direction": ModulePortDirection.INPUT,
    } | overrides
    return ModulePort(**merged)


def _model(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "test model",
        "full_network": _network(),
        "kinetic_laws": (_kinetic_law(),),
        "parameters": (_parameter(),),
    } | overrides
    return ModelSpecification(**merged)


def _eligible_model(**overrides) -> ModelSpecification:
    """One module (mod-1 = {r1, a, b, k1}) with an explicit, eligible boundary port on "a"."""
    merged = {
        "modularizations": (_modularization(),),
        "model_modules": (_model_module(),),
        "module_memberships": _memberships_for(
            "mod-1", reaction_ids=("r1",), species_ids=("a", "b"), parameter_ids=("k1",)
        ),
        "module_ports": (_port(externally_controlled=True, initial_value=Decimal("5")),),
    } | overrides
    return _model(**merged)


def _ineligible_model(**overrides) -> ModelSpecification:
    """The identical module, but with no externally_controlled port -- VIEW_ONLY, never
    eligible for a calibration request."""
    merged = {
        "modularizations": (_modularization(),),
        "model_modules": (_model_module(),),
        "module_memberships": _memberships_for(
            "mod-1", reaction_ids=("r1",), species_ids=("a", "b"), parameter_ids=("k1",)
        ),
    } | overrides
    return _model(**merged)


def _imported_eligible_model() -> ModelSpecification:
    text = """
    model m
      compartment cyto = 1.0;
      species a in cyto = 10.0;
      species b in cyto = 0.0;
      r1: a => b; k1 * a;
      k1 = 0.5;
    end
    """
    imported = import_antimony(text)
    eligible = _eligible_model()
    return replace(
        imported,
        modularizations=eligible.modularizations,
        model_modules=eligible.model_modules,
        module_memberships=eligible.module_memberships,
        module_ports=eligible.module_ports,
    )


def _package_for(model: ModelSpecification) -> Agent2OutputPackage:
    return generate_antimony(model)


def _evaluation(**overrides) -> ModuleCalibrationEvaluation:
    merged = {
        "evaluation_id": "eval-1",
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "run_id": "run-1",
        "parent_model_id": "m1",
        "modularization_id": "mz-1",
        "module_id": "mod-1",
        "status": ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
        "policy_version": MODULE_CALIBRATION_POLICY_VERSION,
    } | overrides
    return ModuleCalibrationEvaluation(**merged)


def _weights(**overrides) -> CriteriaWeights:
    merged = {
        "weights": (
            CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),
            CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),
        ),
        "policy_version": "test-weights-v1",
    } | overrides
    return CriteriaWeights(**merged)


# --- build_module_calibration_request ------------------------------------------------------------


def test_build_request_for_eligible_module_embeds_standalone_artifact_and_ports():
    model = _eligible_model()
    request = build_module_calibration_request(
        model, "mz-1", "mod-1", correlation_id="corr-1", run_id="run-1"
    )
    assert request.parent_model_id == "m1"
    assert request.modularization_id == "mz-1"
    assert request.module_id == "mod-1"
    assert "const s_a;" in request.module_handoff["antimony_text"]
    assert request.module_handoff["antimony_symbol_map"]["species"]["a"] == "s_a"
    assert {s["species_id"] for s in request.module_handoff["species"]} == {"a", "b"}
    assert {p["parameter_id"] for p in request.module_handoff["parameters"]} == {"k1"}
    assert len(request.boundary_ports) == 1
    assert request.boundary_ports[0].species_id == "a"
    assert request.boundary_ports[0].externally_controlled is True
    assert request.calibration_dataset_references == ()


def test_build_request_raises_for_ineligible_module():
    model = _ineligible_model()
    with pytest.raises(ModuleCalibrationReferenceError):
        build_module_calibration_request(
            model, "mz-1", "mod-1", correlation_id="corr-1", run_id="run-1"
        )


def test_build_request_raises_for_non_model_specification():
    with pytest.raises(ModuleCalibrationReferenceError):
        build_module_calibration_request(
            "not a model", "mz-1", "mod-1", correlation_id="c", run_id="r"
        )  # type: ignore[arg-type]


def test_boundary_inadequate_evaluation_is_disclosed_not_an_error():
    evaluation = boundary_inadequate_evaluation(
        parent_model_id="m1",
        modularization_id="mz-1",
        module_id="mod-1",
        reason="no externally_controlled port",
        request_id="req-1",
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert evaluation.status is ModuleCalibrationStatus.BOUNDARY_INADEQUATE
    assert evaluation.fit_quality is None
    assert evaluation.identifiability_findings == ()
    assert "no externally_controlled port" in evaluation.warnings


# --- serialize/parse round trips -----------------------------------------------------------------


def test_request_serialize_then_parse_round_trips():
    model = _eligible_model()
    request = build_module_calibration_request(
        model, "mz-1", "mod-1", correlation_id="corr-1", run_id="run-1"
    )
    data = serialize_module_calibration_request(request)
    parsed = parse_module_calibration_request(data)
    assert parsed == request


@pytest.mark.parametrize(
    "status",
    [
        ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
        ModuleCalibrationStatus.CALIBRATION_FAILED,
        ModuleCalibrationStatus.INSUFFICIENT_DATA,
        ModuleCalibrationStatus.UNIDENTIFIABLE,
        ModuleCalibrationStatus.BOUNDARY_INADEQUATE,
    ],
)
def test_evaluation_parse_round_trips_for_every_status(status):
    if status in (
        ModuleCalibrationStatus.INSUFFICIENT_DATA,
        ModuleCalibrationStatus.BOUNDARY_INADEQUATE,
    ):
        evaluation = _evaluation(status=status)
    else:
        evaluation = _evaluation(
            status=status,
            fit_quality=FitQualitySummary(
                objective_before=Decimal("10"),
                objective_after=Decimal("1"),
                total_sum_squared_residual=Decimal("1"),
                validation_sum_squared_residual=None,
            ),
        )
    data = {
        "evaluation_id": evaluation.evaluation_id,
        "request_id": evaluation.request_id,
        "correlation_id": evaluation.correlation_id,
        "run_id": evaluation.run_id,
        "parent_model_id": evaluation.parent_model_id,
        "modularization_id": evaluation.modularization_id,
        "module_id": evaluation.module_id,
        "status": evaluation.status.value,
        "policy_version": evaluation.policy_version,
        "fit_quality": (
            None
            if evaluation.fit_quality is None
            else {
                "objective_before": str(evaluation.fit_quality.objective_before),
                "objective_after": str(evaluation.fit_quality.objective_after),
                "total_sum_squared_residual": str(
                    evaluation.fit_quality.total_sum_squared_residual
                ),
                "validation_sum_squared_residual": None,
            }
        ),
    }
    parsed = parse_module_calibration_evaluation(data)
    assert parsed.status is status
    assert parsed.fit_quality == evaluation.fit_quality


def test_parse_evaluation_rejects_unknown_status():
    with pytest.raises(ModuleCalibrationContractError):
        parse_module_calibration_evaluation(
            {
                "evaluation_id": "e",
                "request_id": "r",
                "correlation_id": "c",
                "run_id": "run",
                "parent_model_id": "m",
                "modularization_id": "mz",
                "module_id": "mod",
                "status": "NOT_A_REAL_STATUS",
                "policy_version": "v1",
            }
        )


def test_evaluation_rejects_evidence_alongside_unavailable_status():
    with pytest.raises(ValueError):
        _evaluation(
            status=ModuleCalibrationStatus.INSUFFICIENT_DATA,
            fit_quality=FitQualitySummary(
                objective_before=Decimal("1"),
                objective_after=Decimal("1"),
                total_sum_squared_residual=Decimal("1"),
                validation_sum_squared_residual=None,
            ),
        )


# --- score_calibration_independence (calibration_adapter) ----------------------------------------


def test_score_calibration_independence_empty_module_ids_is_unavailable_not_error():
    result = score_calibration_independence((), {})
    assert result.available is False
    assert result.raw_score is None


def test_score_calibration_independence_unavailable_when_any_module_missing_evidence():
    evaluations = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-b": _evaluation(
            module_id="mod-b", status=ModuleCalibrationStatus.INSUFFICIENT_DATA
        ),
    }
    result = score_calibration_independence(("mod-a", "mod-b"), evaluations)
    assert result.available is False
    assert result.raw_score is None
    assert "mod-b" in result.explanation
    assert result.detail.module_ids_missing_evidence == ("mod-b",)
    assert result.detail.module_ids_with_evidence == ("mod-a",)


def test_score_calibration_independence_unavailable_when_module_has_no_entry_at_all():
    """A module named in module_ids with *no key at all* in evaluations must be treated
    identically to one with an explicitly unavailable status -- never silently skipped."""
    evaluations = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
    }
    result = score_calibration_independence(("mod-a", "mod-b"), evaluations)
    assert result.available is False
    assert result.detail.module_ids_missing_evidence == ("mod-b",)


def test_score_calibration_independence_available_min_aggregation_across_modules():
    high = _evaluation(
        module_id="mod-a",
        status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
        identifiability_findings=(),
    )
    low = _evaluation(
        module_id="mod-b",
        status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
        identifiability_findings=(
            IdentifiabilityFindingSummary(
                finding_id="f1", category="HIGH_CORRELATION", severity="CRITICAL", summary="s"
            ),
        ),
    )
    result = score_calibration_independence(("mod-a", "mod-b"), {"mod-a": high, "mod-b": low})
    assert result.available is True
    assert result.raw_score == Decimal("0.5")  # min(1, 1 - 0.5)
    assert result.detail.module_ids_with_evidence == ("mod-a", "mod-b")


def test_score_calibration_independence_zero_for_failed_and_unidentifiable():
    statuses = (
        ModuleCalibrationStatus.CALIBRATION_FAILED,
        ModuleCalibrationStatus.UNIDENTIFIABLE,
    )
    for status in statuses:
        evaluation = _evaluation(status=status)
        result = score_calibration_independence(("mod-1",), {"mod-1": evaluation})
        assert result.available is True
        assert result.raw_score == Decimal("0")


def test_score_calibration_independence_full_score_with_no_findings():
    evaluation = _evaluation(status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED)
    result = score_calibration_independence(("mod-1",), {"mod-1": evaluation})
    assert result.available is True
    assert result.raw_score == Decimal("1")


def test_score_calibration_independence_penalty_is_deterministic():
    evaluation = _evaluation(
        status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
        identifiability_findings=(
            IdentifiabilityFindingSummary(
                finding_id="f1", category="BOUND_HIT", severity="WARNING", summary="s"
            ),
            IdentifiabilityFindingSummary(
                finding_id="f2", category="LOW_SENSITIVITY", severity="ERROR", summary="s"
            ),
        ),
    )
    result = score_calibration_independence(("mod-1",), {"mod-1": evaluation})
    assert result.raw_score == Decimal("0.6")  # 1 - 0.1 - 0.3


# --- evaluate_modularization integration ----------------------------------------------------


def test_evaluate_modularization_omits_calibration_independence_by_default():
    model = _eligible_model()
    weights = _weights()
    evaluation = evaluate_modularization(model, "mz-1", weights)
    criteria = {cs.criterion for cs in evaluation.criterion_scores}
    assert ModularizationCriterion.CALIBRATION_INDEPENDENCE not in criteria


def test_evaluate_modularization_includes_calibration_independence_when_evidence_supplied():
    model = _eligible_model()
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),),
        policy_version="test-weights-v1",
    )
    supported = ModuleCalibrationStatus.CALIBRATION_SUPPORTED
    calibration_evidence = {"mod-1": _evaluation(status=supported)}
    evaluation = evaluate_modularization(
        model, "mz-1", weights, calibration_evidence=calibration_evidence
    )
    scores_by_criterion = {cs.criterion: cs for cs in evaluation.criterion_scores}
    assert ModularizationCriterion.CALIBRATION_INDEPENDENCE in scores_by_criterion
    score = scores_by_criterion[ModularizationCriterion.CALIBRATION_INDEPENDENCE]
    assert score.available is True
    assert score.raw_score == Decimal("1")
    assert evaluation.evaluated_weight_fraction == Decimal("1")
    assert evaluation.overall_score == Decimal("1")


def test_evaluate_modularization_never_fabricates_calibration_score_when_unavailable():
    """TOPOLOGICAL_SEPARATION is itself unavailable on this one-module, one-reaction fixture
    (no reaction-adjacency edge exists at all) -- weighting it alongside CALIBRATION_INDEPENDENCE
    (also made unavailable here) lets this test confirm evaluated_weight_fraction correctly
    discloses a *total* shortfall (0), never fabricating a score from zero real evidence."""
    model = _eligible_model()
    weights = _weights()
    insufficient = ModuleCalibrationStatus.INSUFFICIENT_DATA
    calibration_evidence = {"mod-1": _evaluation(status=insufficient)}
    evaluation = evaluate_modularization(
        model, "mz-1", weights, calibration_evidence=calibration_evidence
    )
    scores_by_criterion = {cs.criterion: cs for cs in evaluation.criterion_scores}
    score = scores_by_criterion[ModularizationCriterion.CALIBRATION_INDEPENDENCE]
    assert score.available is False
    assert score.raw_score is None
    assert score.weighted_contribution is None
    assert evaluation.evaluated_weight_fraction == Decimal("0")
    assert evaluation.overall_score is None


# --- build_module_downstream_handoff ----------------------------------------------------------


def test_build_module_downstream_handoff_is_minimal_valid_agent3_shape():
    model = _eligible_model()
    package = _package_for(model)
    from app.agent2.antimony import generate_module_artifacts

    (artifact,) = generate_module_artifacts(model, "mz-1", module_ids=("mod-1",))
    handoff = build_module_downstream_handoff(model, package, "mz-1", "mod-1", artifact)
    assert handoff["antimony_text"] == artifact.standalone_antimony
    assert handoff["readiness"] == "EXECUTABLE"
    species_ids = {s["species_id"] for s in handoff["species"]}
    assert species_ids == {"a", "b"}
    reaction_ids = {r["reaction_id"] for r in handoff["reactions"]}
    assert reaction_ids == {"r1"}


def test_build_module_downstream_handoff_raises_for_ineligible_artifact():
    model = _ineligible_model()
    package = _package_for(model)
    from app.agent2.antimony import generate_module_artifacts

    (artifact,) = generate_module_artifacts(model, "mz-1", module_ids=("mod-1",))
    with pytest.raises(ValueError):
        build_module_downstream_handoff(model, package, "mz-1", "mod-1", artifact)


# --- GENERATED/IMPORTED symmetry + recursive readiness -----------------------------------------


def test_build_request_works_identically_for_generated_and_imported_parent_models():
    generated_request = build_module_calibration_request(
        _eligible_model(), "mz-1", "mod-1", correlation_id="corr-1", run_id="run-1"
    )
    imported_request = build_module_calibration_request(
        _imported_eligible_model(), "mz-1", "mod-1", correlation_id="corr-1", run_id="run-1"
    )
    assert generated_request.module_handoff["antimony_text"] is not None
    assert imported_request.module_handoff["antimony_text"] is not None
    assert generated_request.boundary_ports == imported_request.boundary_ports


def test_recursive_readiness_module_rebuilt_as_its_own_model_specification():
    """The same request builder works unchanged when its own input is itself a module's own
    filtered network re-assembled as a standalone ModelSpecification (no whole-model-only
    assumption anywhere in app.agent2.module_calibration) -- a single-module modularization
    wrapping the entire (now standalone) network."""
    submodel = ModelSpecification(
        model_id="submodel::mz-1::mod-1",
        name="submodel",
        full_network=_network(),
        kinetic_laws=(_kinetic_law(),),
        parameters=(_parameter(),),
        modularizations=(
            ModelModularization(
                modularization_id="mz-recursive",
                name="whole-submodel wrap",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("mod-whole",),
            ),
        ),
        model_modules=(ModelModule(module_id="mod-whole", name="whole submodel"),),
        module_memberships=_memberships_for(
            "mod-whole",
            modularization_id="mz-recursive",
            reaction_ids=("r1",),
            species_ids=("a", "b"),
            parameter_ids=("k1",),
        ),
        module_ports=(
            ModulePort(
                port_id="port-recursive",
                modularization_id="mz-recursive",
                module_id="mod-whole",
                species_id="a",
                direction=ModulePortDirection.INPUT,
                externally_controlled=True,
                initial_value=Decimal("5"),
            ),
        ),
    )
    request = build_module_calibration_request(
        submodel, "mz-recursive", "mod-whole", correlation_id="corr-1", run_id="run-1"
    )
    assert request.parent_model_id == "submodel::mz-1::mod-1"
    assert request.module_handoff["antimony_text"] is not None
