"""The calibration-selection gate: which of a round's own retained candidates' modules are
worth a real Agent 3/Agent 4 round trip (task instructions §2/§3).

Operates purely on already-computed structural scores (``CandidateModularizationSearchResult``
-- never recomputes or second-guesses ``evaluate_modularization``'s own scoring) and never
raises for an empty/fully-gated result; every ``(candidate_id, module_id)`` pair considered
produces exactly one disclosed ``CalibrationDecision``, never a silent omission.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.candidate_orchestration.types import (
    CalibrationDecision,
    CalibrationDecisionOutcome,
    CalibrationSelectionPolicy,
)
from app.agent2.modularization_search.types import (
    CandidateModularizationBundle,
    CandidateModularizationSearchResult,
)
from app.agent2.module_evaluation.types import (
    CriteriaWeights,
    ModularizationCriterion,
    ModularizationEvaluation,
)


def _rank_key(evaluation: ModularizationEvaluation, candidate_id: str) -> tuple:
    """Identical ordering convention to ``search.py``'s own beam-selection sort -- the highest
    ``overall_score`` first, unavailable last, ties broken by candidate id."""
    return (
        evaluation.overall_score is None,
        -(evaluation.overall_score) if evaluation.overall_score is not None else Decimal(0),
        candidate_id,
    )


def could_change_ordering(
    *,
    current_score: Decimal | None,
    neighbor_scores: tuple[Decimal | None, ...],
    remaining_calibration_weight: Decimal,
) -> bool:
    """Deterministic rule for ``CalibrationSelectionPolicy.only_if_could_change_ordering``: a
    candidate's own best possible score, after gaining calibration evidence it does not yet
    have, is ``current_score + remaining_calibration_weight`` (the most ``CALIBRATION_
    INDEPENDENCE`` could ever add, since its own raw score is bounded in ``[0, 1]`` and is
    currently excluded/zero-contributing). Calibrating this candidate could plausibly change its
    own relative order against one immediate rank-neighbor only if that neighbor's own current
    score is within ``remaining_calibration_weight`` of this candidate's current score --
    otherwise even the best case could never cross that neighbor.

    An unavailable ``current_score`` (every weighted criterion unavailable) always returns
    ``True`` -- calibration could only ever help establish a score where none exists yet.
    """
    if current_score is None:
        return True
    for neighbor in neighbor_scores:
        if neighbor is None:
            continue
        if abs(current_score - neighbor) < remaining_calibration_weight:
            return True
    return False


def select_candidates_for_calibration(
    search_result: CandidateModularizationSearchResult,
    weights: CriteriaWeights,
    policy: CalibrationSelectionPolicy,
    *,
    already_evidenced_module_ids: frozenset[str] = frozenset(),
    calibration_runs_used_so_far: int = 0,
) -> tuple[CalibrationDecision, ...]:
    """Decide, for every module of every retained candidate this round, whether it is selected
    for a real calibration round trip -- never for a degenerate (excluded-from-ranking)
    candidate's own modules, which can never win regardless of evidence (task instructions §8).

    ``already_evidenced_module_ids`` (content-addressed module id strings -- see
    ``app.agent2.modularization_search.identity``) are modules that already have available
    evidence from an earlier round or a cache hit; never recalibrated here.
    """
    if not isinstance(policy, CalibrationSelectionPolicy):
        raise TypeError(
            f"select_candidates_for_calibration requires a CalibrationSelectionPolicy, got "
            f"{policy!r}"
        )
    paired: list[tuple[CandidateModularizationBundle, ModularizationEvaluation]] = sorted(
        zip(search_result.retained, search_result.evaluations, strict=True),
        key=lambda item: _rank_key(item[1], item[0].modularization.modularization_id),
    )
    remaining_weight = weights.normalized_weight(ModularizationCriterion.CALIBRATION_INDEPENDENCE)
    scores_by_rank: tuple[Decimal | None, ...] = tuple(ev.overall_score for _b, ev in paired)

    decisions: list[CalibrationDecision] = []
    candidates_calibrated = 0
    budget_remaining = policy.total_calibration_run_budget - calibration_runs_used_so_far

    for index, (bundle, evaluation) in enumerate(paired):
        rank = index + 1
        candidate_id = bundle.modularization.modularization_id
        module_count = len(bundle.modules)

        candidate_outcome: CalibrationDecisionOutcome | None = None
        candidate_reason = ""
        if module_count <= 1:
            candidate_outcome = CalibrationDecisionOutcome.SKIP_DEGENERATE_CANDIDATE
            candidate_reason = (
                "a one-module decomposition has no internal boundary to optimize and is "
                "excluded from ranking by default -- calibrating it could never change a "
                "ranking it is not eligible to win"
            )
        elif policy.rank_threshold is not None and rank > policy.rank_threshold:
            candidate_outcome = CalibrationDecisionOutcome.SKIP_BELOW_RANK_THRESHOLD
            candidate_reason = f"rank {rank} exceeds rank_threshold={policy.rank_threshold}"
        elif policy.score_threshold is not None and (
            evaluation.overall_score is None or evaluation.overall_score < policy.score_threshold
        ):
            candidate_outcome = CalibrationDecisionOutcome.SKIP_BELOW_SCORE_THRESHOLD
            candidate_reason = (
                f"overall_score={evaluation.overall_score!r} is below "
                f"score_threshold={policy.score_threshold!r}"
            )
        elif candidates_calibrated >= policy.max_candidates_per_generation:
            candidate_outcome = CalibrationDecisionOutcome.SKIP_CANDIDATE_BUDGET_EXHAUSTED
            candidate_reason = (
                f"max_candidates_per_generation={policy.max_candidates_per_generation} already "
                "reached by higher-ranked candidates this round"
            )
        elif policy.only_if_could_change_ordering:
            idx = rank - 1
            neighbors = tuple(
                scores_by_rank[j] for j in (idx - 1, idx + 1) if 0 <= j < len(scores_by_rank)
            )
            if not could_change_ordering(
                current_score=evaluation.overall_score,
                neighbor_scores=neighbors,
                remaining_calibration_weight=remaining_weight,
            ):
                candidate_outcome = CalibrationDecisionOutcome.SKIP_COULD_NOT_CHANGE_ORDERING
                candidate_reason = (
                    f"best-case score (overall_score + remaining calibration weight "
                    f"{remaining_weight!r}) could not plausibly cross either immediate "
                    "rank-neighbor"
                )

        if candidate_outcome is not None:
            for module in bundle.modules:
                decisions.append(
                    CalibrationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=candidate_outcome,
                        reason=candidate_reason,
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
            continue

        modules_calibrated_for_candidate = 0
        candidate_got_at_least_one = False
        for module in bundle.modules:
            if module.module_id in already_evidenced_module_ids:
                decisions.append(
                    CalibrationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=CalibrationDecisionOutcome.SKIP_ALREADY_EVIDENCED,
                        reason="this exact module content already has available evidence",
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
                continue
            if (
                policy.max_modules_per_candidate is not None
                and modules_calibrated_for_candidate >= policy.max_modules_per_candidate
            ):
                decisions.append(
                    CalibrationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=CalibrationDecisionOutcome.SKIP_MODULE_LIMIT_REACHED,
                        reason=(
                            "max_modules_per_candidate="
                            f"{policy.max_modules_per_candidate} already reached for this "
                            "candidate"
                        ),
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
                continue
            if budget_remaining <= 0:
                decisions.append(
                    CalibrationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=CalibrationDecisionOutcome.SKIP_TOTAL_BUDGET_EXHAUSTED,
                        reason=(
                            "total_calibration_run_budget="
                            f"{policy.total_calibration_run_budget} already consumed across "
                            "this orchestration"
                        ),
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
                continue
            decisions.append(
                CalibrationDecision(
                    candidate_id=candidate_id,
                    module_id=module.module_id,
                    outcome=CalibrationDecisionOutcome.CALIBRATE,
                    reason=(
                        f"survived structural gating at rank {rank} "
                        f"(overall_score={evaluation.overall_score!r})"
                    ),
                    structural_score=evaluation.overall_score,
                    rank=rank,
                )
            )
            modules_calibrated_for_candidate += 1
            budget_remaining -= 1
            candidate_got_at_least_one = True
        if candidate_got_at_least_one:
            candidates_calibrated += 1

    return tuple(decisions)


__all__ = ["could_change_ordering", "select_candidates_for_calibration"]
