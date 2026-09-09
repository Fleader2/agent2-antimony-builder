"""Heuristic Boundary Assessment (Increment 6).

Public API: ``assess_boundaries``. See
``docs/09_heuristic_boundary_assessment.md`` for the full contract.
"""

from __future__ import annotations

from app.agent2.boundaries.assessor import assess_boundaries
from app.agent2.boundaries.errors import (
    BoundaryAssessmentError,
    BoundaryReferenceError,
    UnsupportedBoundaryInputError,
)
from app.agent2.boundaries.types import (
    BoundaryAssessmentSet,
    BoundaryReasonCode,
    RuleDirection,
    RuleOutcome,
    RuleStrength,
)

__all__ = [
    "BoundaryAssessmentError",
    "BoundaryAssessmentSet",
    "BoundaryReasonCode",
    "BoundaryReferenceError",
    "RuleDirection",
    "RuleOutcome",
    "RuleStrength",
    "UnsupportedBoundaryInputError",
    "assess_boundaries",
]
