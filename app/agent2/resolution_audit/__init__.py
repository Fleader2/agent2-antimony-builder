"""Module-Count / Resolution Bias Audit.

Determines whether any modularization criterion (``app.agent2.module_evaluation.criteria``)
systematically rewards coarse or fine partitions merely because of module count/size, rather
than because the claimed biological property is genuinely stronger -- by scoring a
deterministic, structure-blind null partition (``null_partition.build_null_partition``) at
each tested resolution and classifying bias entirely from how *that* partition's own score
varies. See ``docs/34_module_count_resolution_bias_audit.md`` for the full design, findings,
and the corrective policy this increment implemented.

Public API: ``audit_criterion_resolution`` (``audit``); ``build_null_partition``
(``null_partition``); ``BiasSeverity``, ``CriterionResolutionAudit``, ``ResolutionAuditEntry``
(``types``); ``ResolutionAuditError``, ``ResolutionAuditReferenceError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.resolution_audit.audit import audit_criterion_resolution
from app.agent2.resolution_audit.errors import (
    ResolutionAuditError,
    ResolutionAuditReferenceError,
)
from app.agent2.resolution_audit.null_partition import build_null_partition
from app.agent2.resolution_audit.types import (
    BiasSeverity,
    CriterionResolutionAudit,
    ResolutionAuditEntry,
)

__all__ = [
    "BiasSeverity",
    "CriterionResolutionAudit",
    "ResolutionAuditEntry",
    "ResolutionAuditError",
    "ResolutionAuditReferenceError",
    "audit_criterion_resolution",
    "build_null_partition",
]
