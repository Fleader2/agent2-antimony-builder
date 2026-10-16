"""Canonical Submodel Materialization for Recursive Modularization: domain errors."""

from __future__ import annotations


class SubmodelMaterializationError(ValueError):
    """Base error for this package -- a malformed request or an unresolved *structural*
    dependency a retained reaction genuinely cannot do without (never a disclosed scientific
    outcome, which is always a typed result -- see ``UnresolvedDependencyDisclosure`` for the
    optional rules/events/observables case, which is disclosed, never raised)."""


class SubmodelMaterializationReferenceError(SubmodelMaterializationError):
    """Raised for a reference to something that does not exist: an unknown
    ``modularization_id``/``module_id``, or a module with zero retained reactions (nothing to
    materialize)."""


__all__ = ["SubmodelMaterializationError", "SubmodelMaterializationReferenceError"]
