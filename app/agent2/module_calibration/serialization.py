"""Plain-dict (de)serialization for ``ModuleCalibrationRequest``/``ModuleCalibrationEvaluation``
-- the decoupling boundary between Agent 2 and the Harness, mirroring the established
Agent2->Agent3/Agent2+Agent3->Agent4 handoff convention exactly: Agent 2 never imports the
Harness's own Python package, and the Harness never imports Agent 2's. Only this one, documented
plain-dict shape is shared, by convention, exactly as every other cross-repo boundary in this
pipeline already is.

``serialize_module_calibration_request`` is this package's own outgoing half (Agent 2 ->
Harness); ``parse_module_calibration_evaluation`` is the incoming half (Harness -> Agent 2) --
whatever the Harness returns after routing the request through Agent 3 then Agent 4.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent2.module_calibration.errors import ModuleCalibrationContractError
from app.agent2.module_calibration.types import (
    BoundarySensitivityFinding,
    CalibrationDatasetReference,
    FitQualitySummary,
    IdentifiabilityFindingSummary,
    ModuleBoundaryPortRef,
    ModuleCalibrationEvaluation,
    ModuleCalibrationRequest,
    ModuleCalibrationStatus,
    ParameterCorrelationEstimate,
    ParameterStabilitySummary,
    ParameterUncertaintyEstimate,
)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _require_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModuleCalibrationContractError(f"{field} must be a non-empty string, got {value!r}")
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModuleCalibrationContractError(f"{field} must be a string or null, got {value!r}")
    return value or None


def _optional_decimal(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ModuleCalibrationContractError(f"{field} must be numeric, got a bool ({value!r})")
    if isinstance(value, (int, float, str, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ModuleCalibrationContractError(
                f"{field} is not a valid decimal: {value!r}"
            ) from exc
    raise ModuleCalibrationContractError(f"{field} must be numeric or null, got {value!r}")


def _require_decimal(value: object, *, field: str) -> Decimal:
    result = _optional_decimal(value, field=field)
    if result is None:
        raise ModuleCalibrationContractError(f"{field} must not be null")
    return result


def _str_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise ModuleCalibrationContractError(f"{field} must be a list of strings, got {value!r}")
    return tuple(value)


def _require_dict(value: object, *, field: str) -> dict:
    if not isinstance(value, dict):
        raise ModuleCalibrationContractError(f"{field} must be an object, got {value!r}")
    return value


def _dict_list(value: object, *, field: str) -> tuple[dict, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, dict) for v in value):
        raise ModuleCalibrationContractError(f"{field} must be a list of objects, got {value!r}")
    return tuple(value)


def serialize_module_calibration_request(request: ModuleCalibrationRequest) -> dict[str, Any]:
    """``ModuleCalibrationRequest`` -> the one plain dict shape the Harness consumes."""
    return {
        "request_id": request.request_id,
        "correlation_id": request.correlation_id,
        "run_id": request.run_id,
        "parent_model_id": request.parent_model_id,
        "modularization_id": request.modularization_id,
        "module_id": request.module_id,
        "module_handoff": request.module_handoff,
        "boundary_ports": [
            {
                "port_id": p.port_id,
                "species_id": p.species_id,
                "direction": p.direction,
                "externally_controlled": p.externally_controlled,
                "initial_value": _decimal_str(p.initial_value),
                "unit": p.unit,
            }
            for p in request.boundary_ports
        ],
        "calibration_dataset_references": [
            {"dataset_id": d.dataset_id, "description": d.description, "source": d.source}
            for d in request.calibration_dataset_references
        ],
        "requested_at": request.requested_at,
    }


def serialize_module_calibration_evaluation(
    evaluation: ModuleCalibrationEvaluation,
) -> dict[str, Any]:
    """``ModuleCalibrationEvaluation`` -> the one plain dict shape ``parse_module_calibration
    _evaluation`` (below) reads back -- the exact inverse, field for field. Added for the
    Recursive Agent-4-Assisted Candidate Search Orchestration increment: a module Agent 2
    itself resolves locally (``BOUNDARY_INADEQUATE``, no Harness round trip needed at all)
    must still be reported to the caller in the identical dict shape a real Harness-routed
    result would use, so a caller never needs two different parsers for "evidence that came
    from a round trip" versus "evidence resolved locally."
    """
    return {
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
            {
                "objective_before": _decimal_str(evaluation.fit_quality.objective_before),
                "objective_after": _decimal_str(evaluation.fit_quality.objective_after),
                "total_sum_squared_residual": _decimal_str(
                    evaluation.fit_quality.total_sum_squared_residual
                ),
                "validation_sum_squared_residual": _decimal_str(
                    evaluation.fit_quality.validation_sum_squared_residual
                ),
            }
            if evaluation.fit_quality is not None
            else None
        ),
        "identifiability_findings": [
            {
                "finding_id": f.finding_id,
                "category": f.category,
                "severity": f.severity,
                "summary": f.summary,
                "related_target_ids": list(f.related_target_ids),
            }
            for f in evaluation.identifiability_findings
        ],
        "parameter_uncertainty": [
            {
                "target_id": u.target_id,
                "fitted_value": _decimal_str(u.fitted_value),
                "standard_error": _decimal_str(u.standard_error),
            }
            for u in evaluation.parameter_uncertainty
        ],
        "parameter_correlations": [
            {
                "target_id_a": c.target_id_a,
                "target_id_b": c.target_id_b,
                "correlation": _decimal_str(c.correlation),
            }
            for c in evaluation.parameter_correlations
        ],
        "boundary_sensitivity_findings": [
            {"target_id": b.target_id, "category": b.category, "summary": b.summary}
            for b in evaluation.boundary_sensitivity_findings
        ],
        "parameters_requiring_external_context": list(
            evaluation.parameters_requiring_external_context
        ),
        "parameter_stability": [
            {
                "target_id": s.target_id,
                "max_relative_difference": _decimal_str(s.max_relative_difference),
                "compared_run_count": s.compared_run_count,
            }
            for s in evaluation.parameter_stability
        ],
        "warnings": list(evaluation.warnings),
        "provenance_refs": list(evaluation.provenance_refs),
    }


def parse_module_calibration_request(data: dict) -> ModuleCalibrationRequest:
    """The reverse of ``serialize_module_calibration_request`` -- used by the Harness side to
    parse what Agent 2 sent without importing Agent 2's own Python package."""
    if not isinstance(data, dict):
        raise ModuleCalibrationContractError(
            f"ModuleCalibrationRequest dict must be a dict, got {type(data)!r}"
        )
    return ModuleCalibrationRequest(
        request_id=_require_str(data.get("request_id"), field="request_id"),
        correlation_id=_require_str(data.get("correlation_id"), field="correlation_id"),
        run_id=_require_str(data.get("run_id"), field="run_id"),
        parent_model_id=_require_str(data.get("parent_model_id"), field="parent_model_id"),
        modularization_id=_require_str(
            data.get("modularization_id"), field="modularization_id"
        ),
        module_id=_require_str(data.get("module_id"), field="module_id"),
        module_handoff=_require_dict(data.get("module_handoff"), field="module_handoff"),
        boundary_ports=tuple(
            ModuleBoundaryPortRef(
                port_id=_require_str(p.get("port_id"), field="boundary_ports[].port_id"),
                species_id=_require_str(
                    p.get("species_id"), field="boundary_ports[].species_id"
                ),
                direction=_require_str(p.get("direction"), field="boundary_ports[].direction"),
                externally_controlled=bool(p.get("externally_controlled", False)),
                initial_value=_optional_decimal(
                    p.get("initial_value"), field="boundary_ports[].initial_value"
                ),
                unit=_optional_str(p.get("unit"), field="boundary_ports[].unit"),
            )
            for p in _dict_list(data.get("boundary_ports"), field="boundary_ports")
        ),
        calibration_dataset_references=tuple(
            CalibrationDatasetReference(
                dataset_id=_require_str(
                    d.get("dataset_id"),
                    field="calibration_dataset_references[].dataset_id",
                ),
                description=_optional_str(
                    d.get("description"),
                    field="calibration_dataset_references[].description",
                ),
                source=_optional_str(
                    d.get("source"), field="calibration_dataset_references[].source"
                ),
            )
            for d in _dict_list(
                data.get("calibration_dataset_references"),
                field="calibration_dataset_references",
            )
        ),
        requested_at=_optional_str(data.get("requested_at"), field="requested_at"),
    )


def parse_module_calibration_evaluation(data: dict) -> ModuleCalibrationEvaluation:
    """Parse and validate one plain dict (produced by ``app.harness.module_calibration``, after
    routing a ``ModuleCalibrationRequest`` through Agent 3 then Agent 4) into a
    ``ModuleCalibrationEvaluation``. Raises ``ModuleCalibrationContractError`` for any
    structurally malformed input -- never fills in a missing required value with a guessed
    default, exactly mirroring ``app.agent3.handoff.parse_agent2_handoff``'s own discipline."""
    if not isinstance(data, dict):
        raise ModuleCalibrationContractError(
            f"ModuleCalibrationEvaluation dict must be a dict, got {type(data)!r}"
        )
    status_raw = data.get("status")
    try:
        status = ModuleCalibrationStatus(status_raw)
    except ValueError as exc:
        raise ModuleCalibrationContractError(
            f"status must be one of {[s.value for s in ModuleCalibrationStatus]}, got "
            f"{status_raw!r}"
        ) from exc

    fit_quality_raw = data.get("fit_quality")
    fit_quality = None
    if fit_quality_raw is not None:
        if not isinstance(fit_quality_raw, dict):
            raise ModuleCalibrationContractError(
                f"fit_quality must be an object or null, got {fit_quality_raw!r}"
            )
        fit_quality = FitQualitySummary(
            objective_before=_optional_decimal(
                fit_quality_raw.get("objective_before"), field="fit_quality.objective_before"
            ),
            objective_after=_optional_decimal(
                fit_quality_raw.get("objective_after"), field="fit_quality.objective_after"
            ),
            total_sum_squared_residual=_optional_decimal(
                fit_quality_raw.get("total_sum_squared_residual"),
                field="fit_quality.total_sum_squared_residual",
            ),
            validation_sum_squared_residual=_optional_decimal(
                fit_quality_raw.get("validation_sum_squared_residual"),
                field="fit_quality.validation_sum_squared_residual",
            ),
        )

    return ModuleCalibrationEvaluation(
        evaluation_id=_require_str(data.get("evaluation_id"), field="evaluation_id"),
        request_id=_require_str(data.get("request_id"), field="request_id"),
        correlation_id=_require_str(data.get("correlation_id"), field="correlation_id"),
        run_id=_require_str(data.get("run_id"), field="run_id"),
        parent_model_id=_require_str(data.get("parent_model_id"), field="parent_model_id"),
        modularization_id=_require_str(
            data.get("modularization_id"), field="modularization_id"
        ),
        module_id=_require_str(data.get("module_id"), field="module_id"),
        status=status,
        policy_version=_require_str(data.get("policy_version"), field="policy_version"),
        fit_quality=fit_quality,
        identifiability_findings=tuple(
            IdentifiabilityFindingSummary(
                finding_id=_require_str(
                    f.get("finding_id"), field="identifiability_findings[].finding_id"
                ),
                category=_require_str(
                    f.get("category"), field="identifiability_findings[].category"
                ),
                severity=_require_str(
                    f.get("severity"), field="identifiability_findings[].severity"
                ),
                summary=_require_str(
                    f.get("summary"), field="identifiability_findings[].summary"
                ),
                related_target_ids=_str_tuple(
                    f.get("related_target_ids"),
                    field="identifiability_findings[].related_target_ids",
                ),
            )
            for f in _dict_list(
                data.get("identifiability_findings"), field="identifiability_findings"
            )
        ),
        parameter_uncertainty=tuple(
            ParameterUncertaintyEstimate(
                target_id=_require_str(
                    u.get("target_id"), field="parameter_uncertainty[].target_id"
                ),
                fitted_value=_require_decimal(
                    u.get("fitted_value"), field="parameter_uncertainty[].fitted_value"
                ),
                standard_error=_optional_decimal(
                    u.get("standard_error"), field="parameter_uncertainty[].standard_error"
                ),
            )
            for u in _dict_list(data.get("parameter_uncertainty"), field="parameter_uncertainty")
        ),
        parameter_correlations=tuple(
            ParameterCorrelationEstimate(
                target_id_a=_require_str(
                    c.get("target_id_a"), field="parameter_correlations[].target_id_a"
                ),
                target_id_b=_require_str(
                    c.get("target_id_b"), field="parameter_correlations[].target_id_b"
                ),
                correlation=_require_decimal(
                    c.get("correlation"), field="parameter_correlations[].correlation"
                ),
            )
            for c in _dict_list(
                data.get("parameter_correlations"), field="parameter_correlations"
            )
        ),
        boundary_sensitivity_findings=tuple(
            BoundarySensitivityFinding(
                target_id=_require_str(
                    b.get("target_id"), field="boundary_sensitivity_findings[].target_id"
                ),
                category=_require_str(
                    b.get("category"), field="boundary_sensitivity_findings[].category"
                ),
                summary=_require_str(
                    b.get("summary"), field="boundary_sensitivity_findings[].summary"
                ),
            )
            for b in _dict_list(
                data.get("boundary_sensitivity_findings"),
                field="boundary_sensitivity_findings",
            )
        ),
        parameters_requiring_external_context=_str_tuple(
            data.get("parameters_requiring_external_context"),
            field="parameters_requiring_external_context",
        ),
        parameter_stability=tuple(
            ParameterStabilitySummary(
                target_id=_require_str(
                    s.get("target_id"), field="parameter_stability[].target_id"
                ),
                max_relative_difference=_require_decimal(
                    s.get("max_relative_difference"),
                    field="parameter_stability[].max_relative_difference",
                ),
                compared_run_count=int(s.get("compared_run_count", 0)),
            )
            for s in _dict_list(data.get("parameter_stability"), field="parameter_stability")
        ),
        warnings=_str_tuple(data.get("warnings"), field="warnings"),
        provenance_refs=_str_tuple(data.get("provenance_refs"), field="provenance_refs"),
    )


__all__ = [
    "parse_module_calibration_evaluation",
    "parse_module_calibration_request",
    "serialize_module_calibration_evaluation",
    "serialize_module_calibration_request",
]
