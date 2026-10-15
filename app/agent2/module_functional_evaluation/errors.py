"""Functional Modularity Criteria from Agents 3 and 4: domain errors."""

from __future__ import annotations


class ModuleFunctionalEvaluationError(ValueError):
    """Base error for this package -- a malformed request/result, never a disclosed
    scientific outcome (which is always a typed result, never an exception)."""


class ModuleFunctionalEvaluationReferenceError(ModuleFunctionalEvaluationError):
    """Raised only when a request cannot be built at all: the whole network has no eligible
    executable artifact, or too few internal/external perturbation targets exist to compute a
    meaningful signal. Never raised for a real, disclosed simulation outcome -- use
    ``unsupported_analysis_evaluation``/``insufficient_targets_evaluation`` instead, exactly
    like ``app.agent2.module_calibration``'s own ``boundary_inadequate_evaluation`` pattern."""


class ModuleFunctionalEvaluationContractError(ModuleFunctionalEvaluationError):
    """Raised for a structurally malformed plain-dict request/result at the (de)serialization
    boundary -- never for a real, disclosed outcome."""


__all__ = [
    "ModuleFunctionalEvaluationContractError",
    "ModuleFunctionalEvaluationError",
    "ModuleFunctionalEvaluationReferenceError",
]
