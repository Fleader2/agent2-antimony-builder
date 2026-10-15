"""Recursive Module Evaluation Orchestration.

Converts one candidate module (``ModelModularization``/``ModelModule``) into a
``ModuleCalibrationRequest`` carrying its own already-generated standalone executable Antimony
submodel (``app.agent2.antimony.generate_module_artifacts``, unchanged), for some other caller
-- always the Harness, never Agent 2 itself (task instructions §1) -- to route through Agent 3
then Agent 4 and return a structured, calibration-based ``ModuleCalibrationEvaluation``. See
``docs/31_recursive_module_evaluation_orchestration.md`` for the full design; the companion
adapter converting a valid evaluation into the module-evaluation framework's own
``CALIBRATION_INDEPENDENCE`` criterion lives in
``app.agent2.module_evaluation.calibration_adapter`` (kept there, not here, since it is this
package's one and only caller, not the other way around).

Public API: ``build_module_calibration_request``, ``boundary_inadequate_evaluation``
(``request_builder``); ``serialize_module_calibration_request``,
``parse_module_calibration_request``, ``parse_module_calibration_evaluation``
(``serialization``); every type (``types``); ``ModuleCalibrationError``,
``ModuleCalibrationReferenceError``, ``ModuleCalibrationContractError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.module_calibration.errors import (
    ModuleCalibrationContractError,
    ModuleCalibrationError,
    ModuleCalibrationReferenceError,
)
from app.agent2.module_calibration.request_builder import (
    boundary_inadequate_evaluation,
    build_module_calibration_request,
)
from app.agent2.module_calibration.serialization import (
    parse_module_calibration_evaluation,
    parse_module_calibration_request,
    serialize_module_calibration_evaluation,
    serialize_module_calibration_request,
)
from app.agent2.module_calibration.types import (
    UNAVAILABLE_EVIDENCE_STATUSES,
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

__all__ = [
    "UNAVAILABLE_EVIDENCE_STATUSES",
    "BoundarySensitivityFinding",
    "CalibrationDatasetReference",
    "FitQualitySummary",
    "IdentifiabilityFindingSummary",
    "ModuleBoundaryPortRef",
    "ModuleCalibrationContractError",
    "ModuleCalibrationError",
    "ModuleCalibrationEvaluation",
    "ModuleCalibrationReferenceError",
    "ModuleCalibrationRequest",
    "ModuleCalibrationStatus",
    "ParameterCorrelationEstimate",
    "ParameterStabilitySummary",
    "ParameterUncertaintyEstimate",
    "boundary_inadequate_evaluation",
    "build_module_calibration_request",
    "parse_module_calibration_evaluation",
    "parse_module_calibration_request",
    "serialize_module_calibration_evaluation",
    "serialize_module_calibration_request",
]
