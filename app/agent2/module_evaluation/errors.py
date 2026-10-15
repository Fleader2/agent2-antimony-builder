"""Module Boundary Evaluation Framework's own error hierarchy.

Mirrors every sibling package's identical convention (e.g.
``app.agent2.enzyme_concentration_species.errors``): all subclass ``ValueError``, and exist
only for a genuine structural/programming inconsistency -- never for missing or unavailable
evidence, which is a normal, disclosed outcome (``ModularizationCriterionScore.available``),
never a raised error.
"""

from __future__ import annotations


class ModuleEvaluationError(ValueError):
    """Base class for every Module Boundary Evaluation Framework failure."""


class ModuleEvaluationReferenceError(ModuleEvaluationError):
    """A cross-reference needed to evaluate a modularization did not resolve (an unknown
    ``modularization_id``, or a ``model`` that is not a real ``ModelSpecification``)."""


__all__ = ["ModuleEvaluationError", "ModuleEvaluationReferenceError"]
