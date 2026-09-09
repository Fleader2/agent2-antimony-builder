"""Heuristic Boundary Assessment's own error hierarchy (Increment 6).

**Missing or incomplete curated/kinetic/parameter information is never an
exception.** A candidate interface with no distinguishing evidence
either way simply receives fewer supporting/opposing reason codes and a
conservative (`LOW`) likelihood -- never a raised error. These errors
exist only for a genuine structural/programming inconsistency: a caller
passing the wrong type, inputs that do not describe the same network, or
a produced assessment that fails to reference real network/law/parameter
ids.

All subclass `ValueError`, mirroring
`app.agent2.parameters.errors.ParameterDeclarationError`'s identical
convention.
"""

from __future__ import annotations


class BoundaryAssessmentError(ValueError):
    """Base class for every Heuristic Boundary Assessment failure."""


class BoundaryReferenceError(BoundaryAssessmentError):
    """A cross-reference needed to assess or validate a boundary did not resolve.

    Includes input pairs whose `network_id`s disagree, and the defensive
    post-assessment check that every assessment's referenced reaction/
    species/kinetic-law/parameter ids actually exist. Should not normally
    occur -- all four inputs already validate their own internal
    references.
    """


class UnsupportedBoundaryInputError(BoundaryAssessmentError):
    """`assess_boundaries` (or an internal helper) received the wrong type."""


__all__ = [
    "BoundaryAssessmentError",
    "BoundaryReferenceError",
    "UnsupportedBoundaryInputError",
]
