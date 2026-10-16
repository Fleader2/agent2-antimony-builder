"""Turning every ``CALIBRATE`` decision into either a real ``ModuleCalibrationRequest`` (for
the caller -- always the Harness, never Agent 2 itself -- to route through Agent 3 then Agent
4) or, when the module itself has no eligible standalone artifact, a disclosed
``BOUNDARY_INADEQUATE`` evaluation resolved entirely locally (task instructions §1: "derive
standalone module handoffs"). Reuses ``app.agent2.module_calibration``'s own existing,
unchanged producer functions -- no new calibration-request-construction logic.
"""

from __future__ import annotations

import uuid

from app.agent2.candidate_orchestration.types import (
    CalibrationDecision,
    CalibrationDecisionOutcome,
    CalibrationRunRequestEnvelope,
)
from app.agent2.modularization_search.assembly import attach_bundle
from app.agent2.modularization_search.types import CandidateModularizationBundle
from app.agent2.module_calibration import (
    ModuleCalibrationEvaluation,
    ModuleCalibrationReferenceError,
    boundary_inadequate_evaluation,
    build_module_calibration_request,
)
from app.agent2.types import ModelSpecification


def build_calibration_requests(
    model: ModelSpecification,
    retained_bundles: tuple[CandidateModularizationBundle, ...],
    decisions: tuple[CalibrationDecision, ...],
    *,
    correlation_id: str,
    run_id: str,
) -> tuple[tuple[CalibrationRunRequestEnvelope, ...], tuple[ModuleCalibrationEvaluation, ...]]:
    """For every ``CALIBRATE`` decision, build its own request (or resolve it locally as
    ``BOUNDARY_INADEQUATE`` when the module has no eligible standalone artifact). Returns
    ``(requests_needing_a_round_trip, locally_resolved_evidence)``.

    ``run_id`` is a shared prefix -- each individual request still gets its own unique,
    deterministic ``run_id`` (``f"{run_id}::{module_id}"``, content-addressed since
    ``module_id`` already is) so a caller can correlate every request back to this one
    orchestration round without any two requests colliding.
    """
    bundles_by_candidate_id = {b.modularization.modularization_id: b for b in retained_bundles}
    requests: list[CalibrationRunRequestEnvelope] = []
    locally_resolved: list[ModuleCalibrationEvaluation] = []
    for decision in decisions:
        if decision.outcome is not CalibrationDecisionOutcome.CALIBRATE:
            continue
        bundle = bundles_by_candidate_id.get(decision.candidate_id)
        if bundle is None:
            raise ValueError(
                f"build_calibration_requests: CALIBRATE decision names unknown "
                f"candidate_id {decision.candidate_id!r} -- not present in retained_bundles"
            )
        eval_model = attach_bundle(model, bundle)
        request_id = (
            f"module-calibration-request::{run_id}::{decision.module_id}::{uuid.uuid4().hex[:8]}"
        )
        module_run_id = f"{run_id}::{decision.module_id}"
        try:
            request = build_module_calibration_request(
                eval_model,
                bundle.modularization.modularization_id,
                decision.module_id,
                correlation_id=correlation_id,
                run_id=module_run_id,
                request_id=request_id,
            )
        except ModuleCalibrationReferenceError as exc:
            locally_resolved.append(
                boundary_inadequate_evaluation(
                    parent_model_id=model.model_id,
                    modularization_id=bundle.modularization.modularization_id,
                    module_id=decision.module_id,
                    reason=str(exc),
                    request_id=request_id,
                    correlation_id=correlation_id,
                    run_id=module_run_id,
                )
            )
            continue
        requests.append(CalibrationRunRequestEnvelope(decision=decision, request=request))
    return tuple(requests), tuple(locally_resolved)


__all__ = ["build_calibration_requests"]
