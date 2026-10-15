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
whenever any supplied module's own evidence is unavailable (``INSUFFICIENT_DATA``/
``BOUNDARY_INADEQUATE``) -- a weakest-link policy, never a fabricated partial average over
fewer modules than were actually asked about.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.agent2.module_calibration.types import (
    UNAVAILABLE_EVIDENCE_STATUSES,
    ModuleCalibrationEvaluation,
    ModuleCalibrationStatus,
)
from app.agent2.module_evaluation.criteria import CriterionResult
from app.agent2.module_evaluation.types import CalibrationIndependenceDetail

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


def score_calibration_independence(
    evaluations: Mapping[str, ModuleCalibrationEvaluation],
) -> CriterionResult:
    """Aggregate every supplied module's own ``ModuleCalibrationEvaluation`` (keyed by
    ``module_id``) into one ``CALIBRATION_INDEPENDENCE`` result for a modularization.

    Weakest-link policy: ``available=True`` only when *every* supplied evaluation itself has
    available evidence; otherwise ``available=False`` (never a fabricated score, never a
    partial average silently dropping an unevidenced module). When available, ``raw_score`` is
    the *minimum* per-module contribution -- a modularization's own calibration independence is
    only as trustworthy as its least-evidenced module.

    ``evaluations`` is caller-supplied (always produced by routing one
    ``ModuleCalibrationRequest`` per module through the Harness, never computed here) -- an
    empty mapping (no evidence supplied for any module) is itself just one more "unavailable"
    case, never an error.
    """
    if not evaluations:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "no calibration evidence supplied for any module of this modularization -- "
                "CALIBRATION_INDEPENDENCE requires at least one module's own "
                "ModuleCalibrationEvaluation"
            ),
            detail=CalibrationIndependenceDetail(),
        )

    with_evidence: list[tuple[str, Decimal]] = []
    missing: list[str] = []
    statuses: list[tuple[str, str]] = []
    for module_id, evaluation in evaluations.items():
        statuses.append((module_id, evaluation.status.value))
        score = _module_raw_score(evaluation)
        if score is None:
            missing.append(module_id)
        else:
            with_evidence.append((module_id, score))

    detail = CalibrationIndependenceDetail(
        module_ids_with_evidence=tuple(sorted(module_id for module_id, _ in with_evidence)),
        module_ids_missing_evidence=tuple(sorted(missing)),
        statuses_by_module_id=tuple(sorted(statuses)),
    )

    if missing:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                f"calibration evidence unavailable for module(s) {sorted(missing)} -- "
                "CALIBRATION_INDEPENDENCE requires every module of this modularization to "
                "have available evidence (weakest-link policy), never a fabricated partial "
                "score over fewer modules than were asked about"
            ),
            warnings=tuple(
                f"module {module_id!r}: {evaluations[module_id].status.value}"
                for module_id in missing
            ),
            detail=detail,
        )

    raw_score = min(score for _, score in with_evidence)
    return CriterionResult(
        available=True,
        raw_score=raw_score,
        explanation=(
            f"minimum CALIBRATION_INDEPENDENCE contribution across {len(with_evidence)} "
            "module(s) with available calibration evidence (weakest-link aggregation)"
        ),
        detail=detail,
    )


__all__ = ["score_calibration_independence"]
