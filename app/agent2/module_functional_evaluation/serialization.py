"""Plain-dict (de)serialization for ``ModuleFunctionalEvaluationRequest``/``ModuleFunctional
EvaluationResult`` -- the decoupling boundary between Agent 2 and the Harness, mirroring
``app.agent2.module_calibration.serialization``'s own identical convention exactly.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent2.module_functional_evaluation.errors import ModuleFunctionalEvaluationContractError
from app.agent2.module_functional_evaluation.types import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationRequest,
    ModuleFunctionalEvaluationResult,
    PerturbationEffectRecord,
    PerturbationTargetSpec,
)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _require_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModuleFunctionalEvaluationContractError(
            f"{field} must be a non-empty string, got {value!r}"
        )
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModuleFunctionalEvaluationContractError(
            f"{field} must be a string or null, got {value!r}"
        )
    return value or None


def _require_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ModuleFunctionalEvaluationContractError(f"{field} must be numeric, got {value!r}")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ModuleFunctionalEvaluationContractError(
            f"{field} is not a valid decimal: {value!r}"
        ) from exc


def _require_dict(value: object, *, field: str) -> dict:
    if not isinstance(value, dict):
        raise ModuleFunctionalEvaluationContractError(f"{field} must be an object, got {value!r}")
    return value


def _str_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise ModuleFunctionalEvaluationContractError(
            f"{field} must be a list of strings, got {value!r}"
        )
    return tuple(value)


def _dict_list(value: object, *, field: str) -> tuple[dict, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, dict) for v in value):
        raise ModuleFunctionalEvaluationContractError(
            f"{field} must be a list of objects, got {value!r}"
        )
    return tuple(value)


def serialize_module_functional_evaluation_request(
    request: ModuleFunctionalEvaluationRequest,
) -> dict[str, Any]:
    """``ModuleFunctionalEvaluationRequest`` -> the one plain dict shape the Harness consumes."""
    return {
        "request_id": request.request_id,
        "correlation_id": request.correlation_id,
        "run_id": request.run_id,
        "parent_model_id": request.parent_model_id,
        "modularization_id": request.modularization_id,
        "module_id": request.module_id,
        "whole_network_handoff": request.whole_network_handoff,
        "baseline_request": request.baseline_request,
        "perturbation_targets": [
            {
                "target_kind": t.target_kind,
                "target_id": t.target_id,
                "fraction": _decimal_str(t.fraction),
                "is_internal": t.is_internal,
            }
            for t in request.perturbation_targets
        ],
        "internal_species_ids": list(request.internal_species_ids),
        "boundary_species_ids": list(request.boundary_species_ids),
        "requested_at": request.requested_at,
    }


def parse_module_functional_evaluation_request(data: dict) -> ModuleFunctionalEvaluationRequest:
    """The reverse of ``serialize_module_functional_evaluation_request`` -- used by the
    Harness side to parse what Agent 2 sent without importing Agent 2's own Python package."""
    if not isinstance(data, dict):
        raise ModuleFunctionalEvaluationContractError(
            f"ModuleFunctionalEvaluationRequest dict must be a dict, got {type(data)!r}"
        )
    return ModuleFunctionalEvaluationRequest(
        request_id=_require_str(data.get("request_id"), field="request_id"),
        correlation_id=_require_str(data.get("correlation_id"), field="correlation_id"),
        run_id=_require_str(data.get("run_id"), field="run_id"),
        parent_model_id=_require_str(data.get("parent_model_id"), field="parent_model_id"),
        modularization_id=_require_str(data.get("modularization_id"), field="modularization_id"),
        module_id=_require_str(data.get("module_id"), field="module_id"),
        whole_network_handoff=_require_dict(
            data.get("whole_network_handoff"), field="whole_network_handoff"
        ),
        baseline_request=_require_dict(data.get("baseline_request"), field="baseline_request"),
        perturbation_targets=tuple(
            PerturbationTargetSpec(
                target_kind=_require_str(
                    t.get("target_kind"), field="perturbation_targets[].target_kind"
                ),
                target_id=_require_str(
                    t.get("target_id"), field="perturbation_targets[].target_id"
                ),
                fraction=_require_decimal(
                    t.get("fraction"), field="perturbation_targets[].fraction"
                ),
                is_internal=bool(t.get("is_internal", False)),
            )
            for t in _dict_list(data.get("perturbation_targets"), field="perturbation_targets")
        ),
        internal_species_ids=_str_tuple(
            data.get("internal_species_ids"), field="internal_species_ids"
        ),
        boundary_species_ids=_str_tuple(
            data.get("boundary_species_ids"), field="boundary_species_ids"
        ),
        requested_at=_optional_str(data.get("requested_at"), field="requested_at"),
    )


def serialize_module_functional_evaluation_result(
    result: ModuleFunctionalEvaluationResult,
) -> dict[str, Any]:
    """``ModuleFunctionalEvaluationResult`` -> the one plain dict shape ``parse_module
    _functional_evaluation_result`` reads back, the exact inverse, field for field."""
    return {
        "evaluation_id": result.evaluation_id,
        "request_id": result.request_id,
        "correlation_id": result.correlation_id,
        "run_id": result.run_id,
        "parent_model_id": result.parent_model_id,
        "modularization_id": result.modularization_id,
        "module_id": result.module_id,
        "status": result.status.value,
        "policy_version": result.policy_version,
        "perturbation_effects": [
            {
                "target_kind": e.target_kind,
                "target_id": e.target_id,
                "is_internal": e.is_internal,
                "simulation_status": e.simulation_status,
                "remained_numerically_stable": e.remained_numerically_stable,
                "relative_change_by_species": {
                    species_id: _decimal_str(value)
                    for species_id, value in e.relative_change_by_species
                },
            }
            for e in result.perturbation_effects
        ],
        "warnings": list(result.warnings),
        "provenance_refs": list(result.provenance_refs),
    }


def parse_module_functional_evaluation_result(data: dict) -> ModuleFunctionalEvaluationResult:
    """Parse and validate one plain dict (produced by ``app.harness.module_functional
    _evaluation``, after routing a ``ModuleFunctionalEvaluationRequest`` through Agent 3) into
    a ``ModuleFunctionalEvaluationResult``. Raises ``ModuleFunctionalEvaluationContractError``
    for any structurally malformed input -- never fills in a missing required value with a
    guessed default."""
    if not isinstance(data, dict):
        raise ModuleFunctionalEvaluationContractError(
            f"ModuleFunctionalEvaluationResult dict must be a dict, got {type(data)!r}"
        )
    status_raw = data.get("status")
    try:
        status = FunctionalEvaluationStatus(status_raw)
    except ValueError as exc:
        raise ModuleFunctionalEvaluationContractError(
            f"status must be one of {[s.value for s in FunctionalEvaluationStatus]}, got "
            f"{status_raw!r}"
        ) from exc

    effects = []
    for e in _dict_list(data.get("perturbation_effects"), field="perturbation_effects"):
        relative_change = e.get("relative_change_by_species") or {}
        if not isinstance(relative_change, dict):
            raise ModuleFunctionalEvaluationContractError(
                f"perturbation_effects[].relative_change_by_species must be an object, got "
                f"{relative_change!r}"
            )
        effects.append(
            PerturbationEffectRecord(
                target_kind=_require_str(
                    e.get("target_kind"), field="perturbation_effects[].target_kind"
                ),
                target_id=_require_str(
                    e.get("target_id"), field="perturbation_effects[].target_id"
                ),
                is_internal=bool(e.get("is_internal", False)),
                simulation_status=_require_str(
                    e.get("simulation_status"), field="perturbation_effects[].simulation_status"
                ),
                remained_numerically_stable=bool(e.get("remained_numerically_stable", False)),
                relative_change_by_species=tuple(
                    sorted(
                        (species_id, _require_decimal(value, field="relative_change_by_species[]"))
                        for species_id, value in relative_change.items()
                    )
                ),
            )
        )

    return ModuleFunctionalEvaluationResult(
        evaluation_id=_require_str(data.get("evaluation_id"), field="evaluation_id"),
        request_id=_require_str(data.get("request_id"), field="request_id"),
        correlation_id=_require_str(data.get("correlation_id"), field="correlation_id"),
        run_id=_require_str(data.get("run_id"), field="run_id"),
        parent_model_id=_require_str(data.get("parent_model_id"), field="parent_model_id"),
        modularization_id=_require_str(data.get("modularization_id"), field="modularization_id"),
        module_id=_require_str(data.get("module_id"), field="module_id"),
        status=status,
        policy_version=_require_str(data.get("policy_version"), field="policy_version"),
        perturbation_effects=tuple(effects),
        warnings=_str_tuple(data.get("warnings"), field="warnings"),
        provenance_refs=_str_tuple(data.get("provenance_refs"), field="provenance_refs"),
    )


__all__ = [
    "parse_module_functional_evaluation_request",
    "parse_module_functional_evaluation_result",
    "serialize_module_functional_evaluation_request",
    "serialize_module_functional_evaluation_result",
]
