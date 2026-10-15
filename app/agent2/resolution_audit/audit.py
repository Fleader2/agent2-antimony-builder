"""Module-Count / Resolution Bias Audit: the public, read-only audit API.

``audit_criterion_resolution`` is this package's one core entry point: scores one criterion
across every supplied (already-existing) modularization, builds and scores a matched,
deterministic, structure-blind null partition at each one's own module count, and classifies
the criterion's own bias severity entirely from how the *null* partition's own score varies
across resolutions -- never from the real partition's own score, which can legitimately vary
for genuine biological reasons. Never mutates ``model``.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, evaluate_modularization
from app.agent2.module_evaluation.types import ModularizationCriterion, TopologyFilteringPolicy
from app.agent2.resolution_audit.errors import ResolutionAuditReferenceError
from app.agent2.resolution_audit.null_partition import build_null_partition
from app.agent2.resolution_audit.types import (
    BiasSeverity,
    CriterionResolutionAudit,
    ResolutionAuditEntry,
)
from app.agent2.types import ModelSpecification, ModuleComponentType
from app.agent2.version import RESOLUTION_AUDIT_POLICY_VERSION

#: Thresholds on how much a structure-blind null partition's own score may swing across the
#: tested resolutions before the underlying criterion is classified as biased -- disclosed,
#: fixed policy constants, never hidden defaults.
_MILD_SWING_THRESHOLD = Decimal("0.15")
_STRONG_SWING_THRESHOLD = Decimal("0.5")


def _score_one_criterion(
    model: ModelSpecification,
    modularization_id: str,
    criterion: ModularizationCriterion,
    *,
    topology_filtering: TopologyFilteringPolicy | None,
) -> tuple[bool, Decimal | None]:
    weights = CriteriaWeights(
        weights=(CriterionWeight(criterion, Decimal("1")),),
        policy_version=RESOLUTION_AUDIT_POLICY_VERSION,
    )
    evaluation = evaluate_modularization(
        model, modularization_id, weights, topology_filtering=topology_filtering
    )
    score = next(
        (cs for cs in evaluation.criterion_scores if cs.criterion is criterion), None
    )
    if score is None:
        return False, None
    return score.available, score.raw_score


def audit_criterion_resolution(
    model: ModelSpecification,
    criterion: ModularizationCriterion,
    modularization_ids: tuple[str, ...],
    *,
    topology_filtering: TopologyFilteringPolicy | None = None,
    policy_version: str = RESOLUTION_AUDIT_POLICY_VERSION,
) -> CriterionResolutionAudit:
    """Audit ``criterion``'s own resolution dependence across every modularization named in
    ``modularization_ids`` (already attached to ``model`` -- built by the caller at whichever
    resolutions it wants audited: 1 module, 2, 3-5, the model's own existing heuristic
    decomposition, ...).

    Raises ``ResolutionAuditReferenceError`` for a malformed ``model``, an empty
    ``modularization_ids``, or an unknown modularization id. Never raises for an unavailable
    criterion at some resolution -- that is a normal, disclosed ``ResolutionAuditEntry
    .available=False``, folded honestly into the final classification.
    """
    if not isinstance(model, ModelSpecification):
        raise ResolutionAuditReferenceError(
            f"audit_criterion_resolution requires a ModelSpecification, got {model!r}"
        )
    if not isinstance(modularization_ids, tuple) or not modularization_ids:
        raise ResolutionAuditReferenceError(
            "audit_criterion_resolution requires a non-empty tuple of modularization_id, got "
            f"{modularization_ids!r}"
        )
    modularizations_by_id = {m.modularization_id: m for m in model.modularizations}

    entries: list[ResolutionAuditEntry] = []
    for index, modularization_id in enumerate(modularization_ids):
        modularization = modularizations_by_id.get(modularization_id)
        if modularization is None:
            raise ResolutionAuditReferenceError(
                f"audit_criterion_resolution: modularization_id {modularization_id!r} does "
                f"not exist in model.modularizations (known: {sorted(modularizations_by_id)})"
            )
        memberships = [
            m for m in model.module_memberships if m.modularization_id == modularization_id
        ]
        module_count = len(modularization.module_ids)
        size_distribution = tuple(
            sorted(
                sum(
                    1
                    for m in memberships
                    if m.module_id == module_id
                    and m.component_type is ModuleComponentType.REACTION
                )
                for module_id in modularization.module_ids
            )
        )

        available, raw_score = _score_one_criterion(
            model, modularization_id, criterion, topology_filtering=topology_filtering
        )

        null_id = f"null::{criterion.value}::{module_count}::{index:03d}"
        null_modularization, null_modules, null_memberships = build_null_partition(
            model.full_network, module_count, modularization_id=null_id
        )
        null_model = replace(
            model,
            modularizations=(null_modularization,),
            model_modules=null_modules,
            module_memberships=null_memberships,
            module_ports=(),
        )
        null_available, null_score = _score_one_criterion(
            null_model, null_id, criterion, topology_filtering=topology_filtering
        )

        corrected_score = None
        if available and null_available and null_score is not None and null_score < 1:
            corrected_score = (raw_score - null_score) / (Decimal(1) - null_score)

        entries.append(
            ResolutionAuditEntry(
                modularization_id=modularization_id,
                module_count=module_count,
                module_size_distribution=size_distribution,
                available=available,
                raw_score=raw_score,
                null_modularization_id=null_id,
                null_available=null_available,
                null_reference_score=null_score,
                corrected_score=corrected_score,
            )
        )

    bias_severity, explanation = _classify_bias(entries)
    return CriterionResolutionAudit(
        criterion=criterion,
        entries=tuple(entries),
        bias_severity=bias_severity,
        explanation=explanation,
        policy_version=policy_version,
    )


def _classify_bias(entries: list[ResolutionAuditEntry]) -> tuple[BiasSeverity, str]:
    null_points = sorted(
        (e.module_count, e.null_reference_score)
        for e in entries
        if e.null_available and e.null_reference_score is not None
    )
    # More than one entry can share a module count (e.g. two differently-structured real
    # modularizations both have 2 modules) -- their null scores are identical by construction
    # (the null partition depends only on module_count), so deduplicating by count changes
    # nothing about the swing computed below, but keeps the "two distinct resolutions" check
    # honest rather than double-counting the same resolution.
    distinct_counts = sorted({count for count, _ in null_points})
    if len(distinct_counts) < 2:
        return (
            BiasSeverity.INSUFFICIENT_EVIDENCE,
            "fewer than two distinct module counts had an available null-partition score to "
            "compare -- cannot assess resolution dependence from a single data point.",
        )
    scores_by_count = dict(null_points)
    scores = [scores_by_count[c] for c in distinct_counts]
    swing = max(scores) - min(scores)
    direction = scores_by_count[distinct_counts[-1]] - scores_by_count[distinct_counts[0]]

    if swing < _MILD_SWING_THRESHOLD:
        return (
            BiasSeverity.NO_MATERIAL_BIAS,
            f"the structure-blind null partition's own score varies by only {swing} across "
            f"module counts {distinct_counts} -- no material module-count/size dependence "
            "detected.",
        )
    if swing < _STRONG_SWING_THRESHOLD:
        trend = "decreasing" if direction < 0 else "increasing"
        return (
            BiasSeverity.MILD_RESOLUTION_DEPENDENCE,
            f"the null partition's own score varies by {swing} across module counts "
            f"{distinct_counts} ({trend} as module count grows) -- a real but modest "
            "resolution dependence.",
        )
    if direction < 0:
        return (
            BiasSeverity.STRONG_COARSE_BIAS,
            f"the null partition's own score drops by {swing} from the lowest "
            f"({distinct_counts[0]} modules) to the highest ({distinct_counts[-1]} modules) "
            "tested module count -- fewer, larger modules are mathematically favored by this "
            "criterion's own formula, regardless of biology.",
        )
    return (
        BiasSeverity.STRONG_FINE_BIAS,
        f"the null partition's own score rises by {swing} from the lowest "
        f"({distinct_counts[0]} modules) to the highest ({distinct_counts[-1]} modules) "
        "tested module count -- more, smaller modules are mathematically favored by this "
        "criterion's own formula, regardless of biology.",
    )


__all__ = ["audit_criterion_resolution"]
