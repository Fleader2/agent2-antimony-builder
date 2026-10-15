"""Module-Count / Resolution Bias Audit's own error hierarchy.

Mirrors every sibling package's identical convention: all subclass ``ValueError``, and exist
only for a genuine structural/programming inconsistency -- never for an audit outcome (a
criterion classified as biased is a normal, disclosed result, never a raised error).
"""

from __future__ import annotations


class ResolutionAuditError(ValueError):
    """Base class for every Module-Count / Resolution Bias Audit failure."""


class ResolutionAuditReferenceError(ResolutionAuditError):
    """A cross-reference needed to run the audit did not resolve (an unknown
    ``modularization_id``, a network with no reactions to build a null partition from, or a
    ``model`` that is not a real ``ModelSpecification``)."""


__all__ = ["ResolutionAuditError", "ResolutionAuditReferenceError"]
