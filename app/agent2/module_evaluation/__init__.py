"""Module Boundary Evaluation Framework.

Scores an already-existing ``ModelModularization`` against multiple, independently-
inspectable evidence criteria, weighted explicitly by the caller -- rather than defining
modularity by one mechanism such as topology. See ``docs/
27_module_boundary_evaluation_framework.md``/``docs/28_topology_hub_currency_component_
filtering.md`` for the full design, and this package's own ``types``/``criteria``/
``evaluator`` module docstrings for the scientific principle this framework operationalizes:
*module mechanisms are evidence; functional/contextual independence is the eventual target
property.*

Public API: ``evaluate_modularization``, ``evaluate_modularization_under_weights``,
``compare_modularizations`` (``evaluator``); ``score_calibration_independence``
(``calibration_adapter``, Recursive Module Evaluation Orchestration increment);
``CriteriaWeights``, ``CriterionWeight``, ``ModularizationCriterion``,
``ModularizationCriterionScore``, ``ModularizationEvaluation``, ``TopologyRole``,
``TopologyRoleOverride``, ``TopologyFilteringPolicy``, ``TopologyComponentFilter``,
``TopologySeparationDetail``, ``CalibrationIndependenceDetail`` (``types``);
``ModuleEvaluationError``, ``ModuleEvaluationReferenceError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.module_evaluation.calibration_adapter import score_calibration_independence
from app.agent2.module_evaluation.errors import (
    ModuleEvaluationError,
    ModuleEvaluationReferenceError,
)
from app.agent2.module_evaluation.evaluator import (
    compare_modularizations,
    evaluate_modularization,
    evaluate_modularization_under_weights,
)
from app.agent2.module_evaluation.types import (
    CalibrationIndependenceDetail,
    CriteriaWeights,
    CriterionWeight,
    ModularizationCriterion,
    ModularizationCriterionScore,
    ModularizationEvaluation,
    TopologyComponentFilter,
    TopologyFilteringPolicy,
    TopologyRole,
    TopologyRoleOverride,
    TopologySeparationDetail,
)

__all__ = [
    "CalibrationIndependenceDetail",
    "CriteriaWeights",
    "CriterionWeight",
    "ModularizationCriterion",
    "ModularizationCriterionScore",
    "ModularizationEvaluation",
    "ModuleEvaluationError",
    "ModuleEvaluationReferenceError",
    "TopologyComponentFilter",
    "TopologyFilteringPolicy",
    "TopologyRole",
    "TopologyRoleOverride",
    "TopologySeparationDetail",
    "compare_modularizations",
    "evaluate_modularization",
    "evaluate_modularization_under_weights",
    "score_calibration_independence",
]
