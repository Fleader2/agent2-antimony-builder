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
from app.agent2.module_evaluation.calibration_adapter import (
    DEFAULT_CALIBRATION_AGGREGATION_POLICY,
    MINIMUM_CALIBRATION_AGGREGATION_POLICY,
    score_calibration_independence,
)
from app.agent2.module_evaluation.types import (
    CalibrationAggregationMethod,
    CalibrationAggregationPolicy,
)
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
    result = score_calibration_independence(
        ("mod-a", "mod-b"),
        {"mod-a": high, "mod-b": low},
        policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY,
    )
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


# --- CalibrationAggregationPolicy / pluggable aggregation (Calibration-Independence ----------
# Aggregation increment) -----------------------------------------------------------------------


def test_calibration_aggregation_policy_rejects_non_enum_method():
    with pytest.raises(TypeError):
        CalibrationAggregationPolicy(method="MINIMUM", policy_version="v1")  # type: ignore[arg-type]


def test_calibration_aggregation_policy_lower_quantile_requires_quantile():
    with pytest.raises(ValueError, match="quantile is required"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.LOWER_QUANTILE, policy_version="v1"
        )


def test_calibration_aggregation_policy_fraction_above_threshold_requires_threshold():
    with pytest.raises(ValueError, match="threshold is required"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD, policy_version="v1"
        )


def test_calibration_aggregation_policy_rejects_quantile_for_wrong_method():
    with pytest.raises(ValueError, match="quantile must be None"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.MINIMUM,
            quantile=Decimal("0.5"),
            policy_version="v1",
        )


def test_calibration_aggregation_policy_rejects_threshold_for_wrong_method():
    with pytest.raises(ValueError, match="threshold must be None"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.WEIGHTED_MEAN,
            threshold=Decimal("0.5"),
            policy_version="v1",
        )


def test_calibration_aggregation_policy_rejects_module_weights_for_wrong_method():
    with pytest.raises(ValueError, match="module_weights must be empty"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.MINIMUM,
            module_weights=(("mod-1", Decimal("2")),),
            policy_version="v1",
        )


def test_calibration_aggregation_policy_rejects_duplicate_module_weight_key():
    with pytest.raises(ValueError, match="must not repeat a module_id"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.WEIGHTED_MEAN,
            module_weights=(("mod-1", Decimal("2")), ("mod-1", Decimal("3"))),
            policy_version="v1",
        )


def test_calibration_aggregation_policy_quantile_zero_rejected():
    with pytest.raises(ValueError, match="must be > 0"):
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.LOWER_QUANTILE,
            quantile=Decimal("0"),
            policy_version="v1",
        )


def _three_module_evidence() -> dict[str, ModuleCalibrationEvaluation]:
    """Three modules at three distinct score tiers: ``mod-hi`` = 1 (no findings), ``mod-mid`` =
    0.9 (one WARNING), ``mod-lo`` = 0.5 (one CRITICAL) -- deliberately spread, not clustered, so
    every aggregation method produces a visibly distinct number."""
    return {
        "mod-hi": _evaluation(
            module_id="mod-hi", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-mid": _evaluation(
            module_id="mod-mid",
            status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
            identifiability_findings=(
                IdentifiabilityFindingSummary(
                    finding_id="f-mid", category="HIGH_CORRELATION", severity="WARNING", summary="s"
                ),
            ),
        ),
        "mod-lo": _evaluation(
            module_id="mod-lo",
            status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
            identifiability_findings=(
                IdentifiabilityFindingSummary(
                    finding_id="f-lo", category="HIGH_CORRELATION", severity="CRITICAL", summary="s"
                ),
            ),
        ),
    }


_THREE_MODULE_IDS = ("mod-hi", "mod-lo", "mod-mid")


def test_default_policy_is_weighted_mean():
    evidence = _three_module_evidence()
    result = score_calibration_independence(_THREE_MODULE_IDS, evidence)
    assert result.available is True
    # mean(1, 0.5, 0.9) == 0.8
    assert result.raw_score == Decimal("0.8")
    assert result.detail.aggregation_method is CalibrationAggregationMethod.WEIGHTED_MEAN


def test_minimum_policy_is_opt_in_not_default():
    evidence = _three_module_evidence()
    mean_result = score_calibration_independence(
        _THREE_MODULE_IDS, evidence, policy=DEFAULT_CALIBRATION_AGGREGATION_POLICY
    )
    min_result = score_calibration_independence(
        _THREE_MODULE_IDS, evidence, policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY
    )
    assert mean_result.raw_score == Decimal("0.8")
    assert min_result.raw_score == Decimal("0.5")
    assert mean_result.raw_score != min_result.raw_score


def test_one_poor_module_scores_differently_under_mean_vs_minimum():
    """Task instructions §6's own explicit test: one poor module among otherwise-perfect ones
    pulls ``MINIMUM`` all the way down to its own score, but only partially drags ``WEIGHTED_
    MEAN`` -- demonstrating why ``MINIMUM`` is a strict diagnostic (it reports the single worst
    module verbatim) while ``WEIGHTED_MEAN`` blends it with the rest."""
    evidence = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-b": _evaluation(
            module_id="mod-b", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-poor": _evaluation(
            module_id="mod-poor", status=ModuleCalibrationStatus.UNIDENTIFIABLE
        ),
    }
    module_ids = ("mod-a", "mod-b", "mod-poor")
    mean_result = score_calibration_independence(module_ids, evidence)
    min_result = score_calibration_independence(
        module_ids, evidence, policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY
    )
    assert min_result.raw_score == Decimal("0")  # the one poor module, verbatim
    assert mean_result.raw_score == Decimal("2") / Decimal("3")  # (1 + 1 + 0) / 3
    assert mean_result.raw_score > min_result.raw_score


def test_weighted_mean_respects_explicit_module_weights():
    evidence = _three_module_evidence()
    policy = CalibrationAggregationPolicy(
        method=CalibrationAggregationMethod.WEIGHTED_MEAN,
        module_weights=(("mod-lo", Decimal("10")),),  # mod-hi/mod-mid default to weight 1
        policy_version="v1",
    )
    result = score_calibration_independence(_THREE_MODULE_IDS, evidence, policy=policy)
    # (1*1 + 0.9*1 + 0.5*10) / (1 + 1 + 10) = 6.9 / 12
    assert result.raw_score == Decimal("6.9") / Decimal("12")


def test_lower_quantile_aggregation_deterministic_nearest_rank():
    evidence = _three_module_evidence()  # sorted scores: 0.5, 0.9, 1
    policy = CalibrationAggregationPolicy(
        method=CalibrationAggregationMethod.LOWER_QUANTILE,
        quantile=Decimal("0.5"),
        policy_version="v1",
    )
    result = score_calibration_independence(_THREE_MODULE_IDS, evidence, policy=policy)
    # ceil(0.5 * 3) = 2 -> the 2nd-lowest of 3 -> 0.9
    assert result.raw_score == Decimal("0.9")

    smallest_policy = CalibrationAggregationPolicy(
        method=CalibrationAggregationMethod.LOWER_QUANTILE,
        quantile=Decimal("0.1"),
        policy_version="v1",
    )
    smallest_result = score_calibration_independence(
        _THREE_MODULE_IDS, evidence, policy=smallest_policy
    )
    # ceil(0.1 * 3) = 1 -> the lowest of 3 -> 0.5 (same as MINIMUM at a small enough quantile)
    assert smallest_result.raw_score == Decimal("0.5")


def test_fraction_above_threshold_aggregation():
    evidence = _three_module_evidence()  # scores: mod-hi=1, mod-mid=0.9, mod-lo=0.5
    policy = CalibrationAggregationPolicy(
        method=CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD,
        threshold=Decimal("0.8"),
        policy_version="v1",
    )
    result = score_calibration_independence(_THREE_MODULE_IDS, evidence, policy=policy)
    assert result.raw_score == Decimal("2") / Decimal("3")  # mod-hi and mod-mid qualify

    strict_policy = CalibrationAggregationPolicy(
        method=CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD,
        threshold=Decimal("1"),
        policy_version="v1",
    )
    strict_result = score_calibration_independence(
        _THREE_MODULE_IDS, evidence, policy=strict_policy
    )
    assert strict_result.raw_score == Decimal("1") / Decimal("3")  # only mod-hi qualifies


def test_per_module_scores_and_dispersion_always_disclosed_regardless_of_method():
    evidence = _three_module_evidence()
    for policy in (
        DEFAULT_CALIBRATION_AGGREGATION_POLICY,
        MINIMUM_CALIBRATION_AGGREGATION_POLICY,
    ):
        result = score_calibration_independence(_THREE_MODULE_IDS, evidence, policy=policy)
        assert dict(result.detail.per_module_scores) == {
            "mod-hi": Decimal("1"),
            "mod-mid": Decimal("0.9"),
            "mod-lo": Decimal("0.5"),
        }
        assert result.detail.min_score == Decimal("0.5")
        assert result.detail.max_score == Decimal("1")
        assert result.detail.mean_score == Decimal("0.8")
        assert result.detail.unavailable_module_count == 0


def test_per_module_scores_disclosed_even_when_aggregate_unavailable():
    """"Never hide a weak module behind the aggregate" extends to the unavailable case too:
    the modules that *do* have evidence still disclose their own scores even though the whole
    aggregate is withheld because one other module is missing."""
    evidence = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-b": _evaluation(
            module_id="mod-b", status=ModuleCalibrationStatus.INSUFFICIENT_DATA
        ),
    }
    result = score_calibration_independence(("mod-a", "mod-b"), evidence)
    assert result.available is False
    assert dict(result.detail.per_module_scores) == {"mod-a": Decimal("1")}
    assert result.detail.unavailable_module_count == 1


def test_unavailable_evidence_gate_is_identical_across_aggregation_methods():
    """The "any module missing evidence makes the whole aggregate unavailable" gate must not
    depend on which aggregation method was requested -- never a policy-dependent fabrication
    of a partial score for ``WEIGHTED_MEAN``/``LOWER_QUANTILE``/``FRACTION_ABOVE_THRESHOLD``
    just because they *could* mathematically ignore the missing module."""
    evidence = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-b": _evaluation(
            module_id="mod-b", status=ModuleCalibrationStatus.INSUFFICIENT_DATA
        ),
    }
    module_ids = ("mod-a", "mod-b")
    for policy in (
        DEFAULT_CALIBRATION_AGGREGATION_POLICY,
        MINIMUM_CALIBRATION_AGGREGATION_POLICY,
        CalibrationAggregationPolicy(
            method=CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD,
            threshold=Decimal("0.5"),
            policy_version="v1",
        ),
    ):
        result = score_calibration_independence(module_ids, evidence, policy=policy)
        assert result.available is False
        assert result.raw_score is None


def test_mean_aggregation_can_increase_unlike_minimum_which_never_can():
    """The module-count-bias-relevant structural distinction (task instructions §3): adding a
    new, above-average module to ``WEIGHTED_MEAN`` *can* raise the aggregate -- a capability
    ``MINIMUM`` structurally lacks (proven elsewhere:
    ``test_calibration_independence_weakest_link_aggregation_is_monotonically_non_increasing``
    in ``tests/agent2/test_resolution_audit.py`` -- adding a module can only ever keep ``MINIMUM``
    the same or lower it, never raise it). This is the concrete reason ``WEIGHTED_MEAN`` carries
    no inherent module-count bias while ``MINIMUM`` does."""
    evaluations = {
        "m1": _evaluation(module_id="m1", status=ModuleCalibrationStatus.UNIDENTIFIABLE),
        "m2": _evaluation(module_id="m2", status=ModuleCalibrationStatus.UNIDENTIFIABLE),
        "m3": _evaluation(module_id="m3", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED),
    }
    two_ids = ("m1", "m2")
    three_ids = ("m1", "m2", "m3")

    mean_before = score_calibration_independence(two_ids, evaluations).raw_score
    mean_after = score_calibration_independence(three_ids, evaluations).raw_score
    assert mean_after > mean_before  # adding the above-average module raised the mean

    min_before = score_calibration_independence(
        two_ids, evaluations, policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY
    ).raw_score
    min_after = score_calibration_independence(
        three_ids, evaluations, policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY
    ).raw_score
    assert min_after <= min_before  # MINIMUM can never rise, by construction


def test_evaluate_modularization_threads_calibration_aggregation_policy():
    """End-to-end (not just the adapter function alone): ``evaluate_modularization`` itself
    produces a different ``overall_score`` for the identical evidence depending on which
    ``calibration_aggregation_policy`` is passed."""
    network = _network()
    model = ModelSpecification(
        model_id="m1",
        name="m1",
        full_network=network,
        kinetic_laws=(_kinetic_law(),),
        parameters=(_parameter(),),
        modularizations=(
            ModelModularization(
                modularization_id="mz-1",
                name="mz-1",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("mod-a", "mod-b"),
            ),
        ),
        model_modules=(
            ModelModule(module_id="mod-a", name="a"),
            ModelModule(module_id="mod-b", name="b"),
        ),
        module_memberships=(
            ModuleMembership(
                membership_id="mem-a",
                modularization_id="mz-1",
                module_id="mod-a",
                component_type=ModuleComponentType.REACTION,
                component_id="r1",
            ),
            ModuleMembership(
                membership_id="mem-b",
                modularization_id="mz-1",
                module_id="mod-b",
                component_type=ModuleComponentType.REACTION,
                component_id="r1",
            ),
        ),
    )
    evidence = {
        "mod-a": _evaluation(
            module_id="mod-a", status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED
        ),
        "mod-b": _evaluation(
            module_id="mod-b", status=ModuleCalibrationStatus.UNIDENTIFIABLE
        ),
    }
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.CALIBRATION_INDEPENDENCE, Decimal("1")),),
        policy_version="test-v1",
    )
    default_eval = evaluate_modularization(model, "mz-1", weights, calibration_evidence=evidence)
    min_eval = evaluate_modularization(
        model,
        "mz-1",
        weights,
        calibration_evidence=evidence,
        calibration_aggregation_policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY,
    )
    assert default_eval.overall_score == Decimal("0.5")  # mean(1, 0)
    assert min_eval.overall_score == Decimal("0")  # min(1, 0)
    assert default_eval.overall_score != min_eval.overall_score
