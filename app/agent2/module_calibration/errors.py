"""Recursive Module Evaluation Orchestration's own error hierarchy.

Mirrors ``app.agent2.module_evaluation.errors``'s identical convention: all subclass
``ValueError``, and exist only for a genuine structural/programming inconsistency -- never for
an evaluation outcome. ``INSUFFICIENT_DATA``/``UNIDENTIFIABLE``/``CALIBRATION_FAILED``/
``BOUNDARY_INADEQUATE`` are all normal, disclosed ``ModuleCalibrationEvaluation.status`` values,
never raised exceptions.
"""

from __future__ import annotations


class ModuleCalibrationError(ValueError):
    """Base class for every Recursive Module Evaluation Orchestration failure."""


class ModuleCalibrationReferenceError(ModuleCalibrationError):
    """A cross-reference needed to build a module calibration request did not resolve (an
    unknown ``modularization_id``/``module_id``, or a ``model`` that is not a real
    ``ModelSpecification``)."""


class ModuleCalibrationContractError(ModuleCalibrationError):
    """A ``ModuleCalibrationEvaluation`` dict returned by the Harness was structurally
    malformed (a missing required field, a field of the wrong type, an unknown status) --
    never raised for a genuine, well-formed negative outcome."""


__all__ = [
    "ModuleCalibrationContractError",
    "ModuleCalibrationError",
    "ModuleCalibrationReferenceError",
]
