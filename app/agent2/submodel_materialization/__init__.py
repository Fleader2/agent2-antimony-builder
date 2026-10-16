"""Canonical Submodel Materialization for Recursive Modularization.

Public API: ``materialize_submodel`` (the sole entry point) plus its result/lineage/disclosure
types. See ``materialization.py`` for the full behavioral contract.
"""

from __future__ import annotations

from app.agent2.submodel_materialization.closure import (
    DependencyClosureResult,
    compute_dependency_closure,
)
from app.agent2.submodel_materialization.errors import (
    SubmodelMaterializationError,
    SubmodelMaterializationReferenceError,
)
from app.agent2.submodel_materialization.materialization import materialize_submodel
from app.agent2.submodel_materialization.types import (
    BoundaryTreatmentRecord,
    SubmodelMaterializationLineage,
    SubmodelMaterializationResult,
    UnresolvedDependencyDisclosure,
)

__all__ = [
    "BoundaryTreatmentRecord",
    "DependencyClosureResult",
    "SubmodelMaterializationError",
    "SubmodelMaterializationLineage",
    "SubmodelMaterializationReferenceError",
    "SubmodelMaterializationResult",
    "UnresolvedDependencyDisclosure",
    "compute_dependency_closure",
    "materialize_submodel",
]
