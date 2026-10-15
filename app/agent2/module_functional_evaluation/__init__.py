"""Functional Modularity Criteria from Agents 3 and 4.

Converts one candidate module into a ``ModuleFunctionalEvaluationRequest`` -- a deterministic
battery of perturbations spanning both inside and outside that module, run against the whole
canonical network -- for some other caller (always the Harness, never Agent 2 itself) to route
through Agent 3 and return a structured ``ModuleFunctionalEvaluationResult``. The companion
adapters converting a valid result into the module-evaluation framework's own
``DYNAMIC_ISOLATION``/``SENSITIVITY_COHERENCE`` criteria live in
``app.agent2.module_evaluation.functional_adapter`` (kept there, not here, since it is this
package's one and only caller, not the other way around -- mirrors ``app.agent2
.module_calibration``'s own identical split with ``calibration_adapter``).

Public API: ``build_module_functional_evaluation_request``, ``select_functional_evaluation
_targets``, ``unsupported_analysis_evaluation``, ``insufficient_targets_evaluation``
(``request_builder``); ``serialize_module_functional_evaluation_request``,
``parse_module_functional_evaluation_request``, ``serialize_module_functional_evaluation
_result``, ``parse_module_functional_evaluation_result`` (``serialization``); every type
(``types``); ``ModuleFunctionalEvaluationError``, ``ModuleFunctionalEvaluationReferenceError``,
``ModuleFunctionalEvaluationContractError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.module_functional_evaluation.errors import (
    ModuleFunctionalEvaluationContractError,
    ModuleFunctionalEvaluationError,
    ModuleFunctionalEvaluationReferenceError,
)
from app.agent2.module_functional_evaluation.request_builder import (
    build_module_functional_evaluation_request,
    insufficient_targets_evaluation,
    select_functional_evaluation_targets,
    unsupported_analysis_evaluation,
)
from app.agent2.module_functional_evaluation.serialization import (
    parse_module_functional_evaluation_request,
    parse_module_functional_evaluation_result,
    serialize_module_functional_evaluation_request,
    serialize_module_functional_evaluation_result,
)
from app.agent2.module_functional_evaluation.types import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationRequest,
    ModuleFunctionalEvaluationResult,
    PerturbationEffectRecord,
    PerturbationTargetSpec,
)

__all__ = [
    "FunctionalEvaluationStatus",
    "ModuleFunctionalEvaluationContractError",
    "ModuleFunctionalEvaluationError",
    "ModuleFunctionalEvaluationReferenceError",
    "ModuleFunctionalEvaluationRequest",
    "ModuleFunctionalEvaluationResult",
    "PerturbationEffectRecord",
    "PerturbationTargetSpec",
    "build_module_functional_evaluation_request",
    "insufficient_targets_evaluation",
    "parse_module_functional_evaluation_request",
    "parse_module_functional_evaluation_result",
    "select_functional_evaluation_targets",
    "serialize_module_functional_evaluation_request",
    "serialize_module_functional_evaluation_result",
    "unsupported_analysis_evaluation",
]
