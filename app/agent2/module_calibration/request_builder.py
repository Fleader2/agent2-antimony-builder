"""Building one ``ModuleCalibrationRequest`` from an existing ``ModelModularization`` module --
the sole producer-side entry point this package exposes (task instructions §2: "Use the
existing standalone-module generation path").

Works identically for a ``GENERATED`` or an ``IMPORTED`` ``model`` (``ModelSpecification``),
and identically whether ``model`` is itself a previously-derived module/submodel re-assembled
as its own ``ModelSpecification`` (recursive readiness, task instructions §5) -- every value
read here comes from ``model.modularizations``/``.module_memberships``/``.module_ports`` and
``app.agent2.antimony.generate_module_artifacts``'s own output alone, never from anything
origin-specific or "whole-model-only."
"""

from __future__ import annotations

import uuid

from app.agent2.antimony import generate_antimony, generate_module_artifacts
from app.agent2.module_calibration.errors import ModuleCalibrationReferenceError
from app.agent2.module_calibration.types import (
    CalibrationDatasetReference,
    ModuleBoundaryPortRef,
    ModuleCalibrationEvaluation,
    ModuleCalibrationRequest,
    ModuleCalibrationStatus,
)
from app.agent2.pipeline import build_module_downstream_handoff
from app.agent2.types import ModelSpecification
from app.agent2.version import MODULE_CALIBRATION_POLICY_VERSION


def build_module_calibration_request(
    model: ModelSpecification,
    modularization_id: str,
    module_id: str,
    *,
    correlation_id: str,
    run_id: str,
    calibration_dataset_references: tuple[CalibrationDatasetReference, ...] = (),
    request_id: str | None = None,
    requested_at: str | None = None,
) -> ModuleCalibrationRequest:
    """Build one ``ModuleCalibrationRequest`` for ``module_id`` of ``modularization_id``.

    Calls ``app.agent2.antimony.generate_module_artifacts`` (unchanged) to obtain that
    module's own ``ModuleAntimonyArtifact``. Raises ``ModuleCalibrationReferenceError`` when
    the module has no eligible standalone artifact (``standalone_antimony is None`` --
    ``readiness`` is ``VIEW_ONLY`` or ``NON_EXECUTABLE_UNRESOLVED_KINETICS``): that is a real,
    disclosed ``BOUNDARY_INADEQUATE`` outcome (see ``boundary_inadequate_evaluation`` below),
    never silently built into a request that could not actually be simulated.
    """
    if not isinstance(model, ModelSpecification):
        raise ModuleCalibrationReferenceError(
            f"build_module_calibration_request requires a ModelSpecification, got {model!r}"
        )
    (artifact,) = generate_module_artifacts(model, modularization_id, module_ids=(module_id,))
    if artifact.standalone_antimony is None:
        raise ModuleCalibrationReferenceError(
            f"module_id {module_id!r} of modularization {modularization_id!r} has no eligible "
            f"standalone artifact (readiness={artifact.readiness.value!r}) -- use "
            "boundary_inadequate_evaluation instead of building a request for it"
        )
    package = generate_antimony(model)
    module_handoff = build_module_downstream_handoff(
        model, package, modularization_id, module_id, artifact
    )
    boundary_ports = tuple(
        ModuleBoundaryPortRef(
            port_id=p.port_id,
            species_id=p.species_id,
            direction=p.direction.value,
            externally_controlled=p.externally_controlled,
            initial_value=p.initial_value,
            unit=p.unit,
        )
        for p in artifact.boundary_ports
    )
    return ModuleCalibrationRequest(
        request_id=request_id or f"module-calibration-request::{uuid.uuid4()}",
        correlation_id=correlation_id,
        run_id=run_id,
        parent_model_id=model.model_id,
        modularization_id=modularization_id,
        module_id=module_id,
        module_handoff=module_handoff,
        boundary_ports=boundary_ports,
        calibration_dataset_references=calibration_dataset_references,
        requested_at=requested_at,
    )


def boundary_inadequate_evaluation(
    *,
    parent_model_id: str,
    modularization_id: str,
    module_id: str,
    reason: str,
    request_id: str,
    correlation_id: str,
    run_id: str,
) -> ModuleCalibrationEvaluation:
    """The disclosed ``BOUNDARY_INADEQUATE`` result for a module with no eligible standalone
    artifact -- decided entirely locally (no Harness round trip, no Agent 3/Agent 4 call), so a
    caller never pays for, or waits on, an orchestration that could not possibly succeed."""
    return ModuleCalibrationEvaluation(
        evaluation_id=f"module-calibration::{modularization_id}::{module_id}::boundary-inadequate",
        request_id=request_id,
        correlation_id=correlation_id,
        run_id=run_id,
        parent_model_id=parent_model_id,
        modularization_id=modularization_id,
        module_id=module_id,
        status=ModuleCalibrationStatus.BOUNDARY_INADEQUATE,
        policy_version=MODULE_CALIBRATION_POLICY_VERSION,
        warnings=(reason,),
        provenance_refs=(f"modularization::{modularization_id}", f"module::{module_id}"),
    )


__all__ = ["boundary_inadequate_evaluation", "build_module_calibration_request"]
