"""Converts externally-obtained ``ModuleCalibrationEvaluation`` evidence (one Harness round
trip through Agent 3 then Agent 4 per module, ``app.agent2.module_calibration``) into the
Module Boundary Evaluation Framework's own, previously-reserved ``CALIBRATION_INDEPENDENCE``
criterion (Recursive Module Evaluation Orchestration increment, task instructions §4).

Deliberately kept separate from ``criteria.py``: every function there computes its own
criterion from ``FullNetwork``/``ModuleMembership``/``ModulePort`` data alone (no simulation, no
fitting, no network access -- see that module's own docstring); this one, by contrast, only ever
*adapts* evidence someone else (the Harness, via Agent 3/Agent 4) already produced. Agent 2
still never calls Agent 3 or Agent 4 directly anywhere in this repository.

**Never fabricates a score.** ``score_calibration_independence`` returns ``available=False``
whenever any of the modularization's own modules has unavailable evidence (``INSUFFICIENT_
DATA``/``BOUNDARY_INADEQUATE``, *or no entry supplied for it at all*) -- this unavailable-
evidence gate is identical and policy-independent for every ``CalibrationAggregationMethod``;
never a fabricated partial average over fewer modules than the modularization actually has.

**Aggregation is pluggable** (Calibration-Independence Aggregation increment): once every
module has available evidence, ``raw_score`` is computed from the per-module scores by whichever
``CalibrationAggregationPolicy`` the caller supplies (default: ``DEFAULT_CALIBRATION_AGGREGATION
_POLICY``, ``WEIGHTED_MEAN``) -- replacing the single, previously hard-coded weakest-link
(``MINIMUM``) policy, which remains available (``MINIMUM_CALIBRATION_AGGREGATION_POLICY``) as an
explicit, strict diagnostic choice. Every per-module score is always disclosed on
``CalibrationIndependenceDetail.per_module_scores`` regardless of which method produced the one
aggregate number -- "never hide a weak module behind the aggregate."
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_CEILING, Decimal

from app.agent2.module_calibration.types import (
    UNAVAILABLE_EVIDENCE_STATUSES,
    ModuleCalibrationEvaluation,
    ModuleCalibrationStatus,
)
from app.agent2.module_evaluation.criteria import CriterionResult
from app.agent2.module_evaluation.types import (
    CalibrationAggregationMethod,
    CalibrationAggregationPolicy,
    CalibrationIndependenceDetail,
)
from app.agent2.version import CALIBRATION_AGGREGATION_POLICY_VERSION

#: Deterministic, disclosed per-finding-severity penalty subtracted from a ``
#: CALIBRATION_SUPPORTED`` module's own starting score of ``1`` -- pure arithmetic over Agent
#: 4's own already-reported ``IdentifiabilityFinding`` severities, never a new calibration
#: algorithm (task instructions §6: "no new calibration algorithms inside Agent 4" -- this
#: package performs no calibration at all, only scores what Agent 4 already found).
_SEVERITY_PENALTY: dict[str, Decimal] = {
    "CRITICAL": Decimal("0.5"),
    "ERROR": Decimal("0.3"),
    "WARNING": Decimal("0.1"),
    "INFO": Decimal("0"),
}

#: Real, available negative evidence: the fit was attempted and did not stand up, or did not
#: pin the module's own parameters down -- scored ``0``, never treated as missing evidence.
_ZERO_EVIDENCE_STATUSES: frozenset[ModuleCalibrationStatus] = frozenset(
    {ModuleCalibrationStatus.CALIBRATION_FAILED, ModuleCalibrationStatus.UNIDENTIFIABLE}
)

#: The new default (Calibration-Independence Aggregation increment): for a fixed per-module
#: quality distribution, ``E[mean(X_1..X_n)]`` is constant in module count ``n``, unlike
#: ``E[min(X_1..X_n)]``, which is provably non-increasing in ``n`` -- so this policy carries no
#: inherent module-count bias, unlike the ``MINIMUM`` policy it replaces as the default.
DEFAULT_CALIBRATION_AGGREGATION_POLICY = CalibrationAggregationPolicy(
    method=CalibrationAggregationMethod.WEIGHTED_MEAN,
    policy_version=CALIBRATION_AGGREGATION_POLICY_VERSION,
)

#: Weakest-link: retained as an explicit, strict diagnostic choice (task instructions §3) --
#: never the default, since it is the policy proven monotonically non-increasing in module
#: count (Module-Count / Resolution Bias Audit increment).
MINIMUM_CALIBRATION_AGGREGATION_POLICY = CalibrationAggregationPolicy(
    method=CalibrationAggregationMethod.MINIMUM,
    policy_version=CALIBRATION_AGGREGATION_POLICY_VERSION,
)


def _module_raw_score(evaluation: ModuleCalibrationEvaluation) -> Decimal | None:
    """One module's own ``[0, 1]`` CALIBRATION_INDEPENDENCE contribution, or ``None`` when its
    evidence is unavailable -- never fabricated."""
    if evaluation.status in UNAVAILABLE_EVIDENCE_STATUSES:
        return None
    if evaluation.status in _ZERO_EVIDENCE_STATUSES:
        return Decimal("0")
    # CALIBRATION_SUPPORTED: start from 1, deduct a disclosed penalty per identifiability
    # finding severity, floor at 0, ceiling at 1 (a module with zero findings scores exactly 1).
    penalty = sum(
        (
            _SEVERITY_PENALTY.get(f.severity, Decimal("0"))
            for f in evaluation.identifiability_findings
        ),
        Decimal("0"),
    )
    return max(Decimal("0"), min(Decimal("1"), Decimal("1") - penalty))


def _aggregate(
    with_evidence: list[tuple[str, Decimal]], policy: CalibrationAggregationPolicy
) -> Decimal:
    """The one aggregate ``[0, 1]`` number ``policy`` produces from every evidence-bearing
    module's own score -- ``with_evidence`` is never empty here (the caller only reaches this
    once every module in the modularization has available evidence)."""
    scores = [score for _, score in with_evidence]
    if policy.method is CalibrationAggregationMethod.MINIMUM:
        return min(scores)
    if policy.method is CalibrationAggregationMethod.WEIGHTED_MEAN:
        weights_by_module = dict(policy.module_weights)
        weighted_total = Decimal("0")
        weight_total = Decimal("0")
        for module_id, score in with_evidence:
            weight = weights_by_module.get(module_id, Decimal("1"))
            weighted_total += weight * score
            weight_total += weight
        return weighted_total / weight_total
    if policy.method is CalibrationAggregationMethod.LOWER_QUANTILE:
        ordered = sorted(scores)
        n = len(ordered)
        assert policy.quantile is not None  # enforced by CalibrationAggregationPolicy
        rank = int((policy.quantile * Decimal(n)).to_integral_value(rounding=ROUND_CEILING))
        index = max(0, min(n - 1, rank - 1))
        return ordered[index]
    if policy.method is CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD:
        assert policy.threshold is not None  # enforced by CalibrationAggregationPolicy
        above = sum(1 for score in scores if score >= policy.threshold)
        return Decimal(above) / Decimal(len(scores))
    raise AssertionError(  # pragma: no cover
        f"unhandled CalibrationAggregationMethod: {policy.method!r}"
    )


def score_calibration_independence(
    module_ids: tuple[str, ...],
    evaluations: Mapping[str, ModuleCalibrationEvaluation],
    *,
    policy: CalibrationAggregationPolicy = DEFAULT_CALIBRATION_AGGREGATION_POLICY,
) -> CriterionResult:
    """Aggregate ``module_ids``' own ``ModuleCalibrationEvaluation``s (looked up in
    ``evaluations`` by ``module_id``) into one ``CALIBRATION_INDEPENDENCE`` result for a
    modularization.

    ``module_ids`` is always the *modularization's own, complete* module-id tuple (task
    instructions §2: "if any **required** module has unavailable calibration evidence,
    preserve the current unavailable-evidence semantics") -- a module named in ``module_ids``
    with **no entry at all** in ``evaluations`` is treated identically to one whose own
    evidence is explicitly unavailable, never silently skipped as though it were never asked
    about. This is why ``module_ids`` is a required, separate argument rather than simply
    iterating ``evaluations.keys()`` -- a mapping missing a key says nothing on its own about
    whether that module was *supposed* to have evidence.

    ``available=True`` only when *every* module in ``module_ids`` itself has available evidence
    (never a fabricated score, never a partial average silently dropping an unevidenced
    module) -- this gate is identical regardless of ``policy``. When available, ``raw_score`` is
    ``policy``'s own aggregate of every per-module contribution (Calibration-Independence
    Aggregation increment; default ``WEIGHTED_MEAN``, replacing the single, previously
    hard-coded weakest-link policy). ``CalibrationIndependenceDetail.per_module_scores`` always
    lists every evidence-bearing module's own individual score, regardless of ``available`` --
    "never hide a weak module behind the aggregate."

    ``evaluations`` is caller-supplied (always produced by routing one
    ``ModuleCalibrationRequest`` per module through the Harness, never computed here).
    """
    if not isinstance(policy, CalibrationAggregationPolicy):
        raise TypeError(
            "score_calibration_independence requires a CalibrationAggregationPolicy, got "
            f"{policy!r}"
        )
    if not module_ids:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "modularization has no modules at all -- CALIBRATION_INDEPENDENCE requires "
                "at least one"
            ),
            detail=CalibrationIndependenceDetail(),
        )

    with_evidence: list[tuple[str, Decimal]] = []
    missing: list[str] = []
    statuses: list[tuple[str, str]] = []
    for module_id in module_ids:
        evaluation = evaluations.get(module_id)
        if evaluation is None:
            missing.append(module_id)
            continue
        statuses.append((module_id, evaluation.status.value))
        score = _module_raw_score(evaluation)
        if score is None:
            missing.append(module_id)
        else:
            with_evidence.append((module_id, score))

    per_module_scores = tuple(sorted(with_evidence))
    scores_only = [score for _, score in with_evidence]
    mean_score = (
        sum(scores_only, Decimal("0")) / Decimal(len(scores_only)) if scores_only else None
    )
    min_score = min(scores_only) if scores_only else None
    max_score = max(scores_only) if scores_only else None

    detail = CalibrationIndependenceDetail(
        module_ids_with_evidence=tuple(sorted(module_id for module_id, _ in with_evidence)),
        module_ids_missing_evidence=tuple(sorted(missing)),
        statuses_by_module_id=tuple(sorted(statuses)),
        aggregation_method=policy.method,
        per_module_scores=per_module_scores,
        mean_score=mean_score,
        min_score=min_score,
        max_score=max_score,
        unavailable_module_count=len(missing),
    )

    if missing:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                f"calibration evidence unavailable for module(s) {sorted(missing)} -- "
                "CALIBRATION_INDEPENDENCE requires every module of this modularization to "
                "have available evidence, never a fabricated partial score over fewer modules "
                "than were asked about (this gate is identical regardless of aggregation "
                "policy)"
            ),
            warnings=tuple(
                f"module {module_id!r}: "
                + (
                    evaluations[module_id].status.value
                    if module_id in evaluations
                    else "no evidence supplied"
                )
                for module_id in missing
            ),
            detail=detail,
        )

    raw_score = _aggregate(with_evidence, policy)
    return CriterionResult(
        available=True,
        raw_score=raw_score,
        explanation=(
            f"{policy.method.value} aggregation of the CALIBRATION_INDEPENDENCE contribution "
            f"across {len(with_evidence)} module(s), every one with available calibration "
            "evidence"
        ),
        detail=detail,
    )


__all__ = [
    "DEFAULT_CALIBRATION_AGGREGATION_POLICY",
    "MINIMUM_CALIBRATION_AGGREGATION_POLICY",
    "score_calibration_independence",
]
