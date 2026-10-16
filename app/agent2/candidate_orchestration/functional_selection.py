"""The functional-evaluation-selection gate: which of a round's own retained candidates'
modules are worth a real Agent 3 functional-evaluation round trip (Automatic Functional-
Evaluation Selection and Caching increment, task instructions §2).

Mirrors ``selection.py``'s own ``select_candidates_for_calibration`` exactly, with one
functional-evaluation-specific addition: a single, up-front check that short-circuits every
decision this round to ``SKIP_ZERO_FUNCTIONAL_WEIGHT`` when both ``DYNAMIC_ISOLATION`` and
``SENSITIVITY_COHERENCE`` have zero (or omitted) weight -- functional evidence could not move
``overall_score`` at all in that case, so no Agent 3 call is ever worth making (task
instructions §2/§8: "zero functional weights -> no Agent 3 calls").

Operates purely on already-computed structural scores -- never recomputes or second-guesses
``evaluate_modularization``'s own scoring -- and never raises for an empty/fully-gated result;
every ``(candidate_id, module_id)`` pair considered produces exactly one disclosed
``FunctionalEvaluationDecision``, never a silent omission.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.candidate_orchestration.selection import could_change_ordering
from app.agent2.candidate_orchestration.types import (
    FunctionalEvaluationDecision,
    FunctionalEvaluationDecisionOutcome,
    FunctionalEvaluationSelectionPolicy,
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

#: The two criteria one piece of functional-evaluation evidence can ever affect -- both derived
#: from the identical underlying ``ModuleFunctionalEvaluationResult`` per module (see
#: ``app.agent2.module_evaluation.functional_adapter``).
_FUNCTIONAL_CRITERIA = (
    ModularizationCriterion.DYNAMIC_ISOLATION,
    ModularizationCriterion.SENSITIVITY_COHERENCE,
)


def _rank_key(evaluation: ModularizationEvaluation, candidate_id: str) -> tuple:
    """Identical ordering convention to ``selection.py``'s/``search.py``'s own sort."""
    return (
        evaluation.overall_score is None,
        -(evaluation.overall_score) if evaluation.overall_score is not None else Decimal(0),
        candidate_id,
    )


def total_functional_weight(weights: CriteriaWeights) -> Decimal:
    """The sum of ``DYNAMIC_ISOLATION``'s and ``SENSITIVITY_COHERENCE``'s own normalized
    weights -- ``0`` means functional evidence could never move ``overall_score`` at all."""
    return sum(
        (weights.normalized_weight(criterion) for criterion in _FUNCTIONAL_CRITERIA), Decimal(0)
    )


def select_modules_for_functional_evaluation(
    search_result: CandidateModularizationSearchResult,
    weights: CriteriaWeights,
    policy: FunctionalEvaluationSelectionPolicy,
    *,
    already_evidenced_module_ids: frozenset[str] = frozenset(),
    functional_evaluations_used_so_far: int = 0,
) -> tuple[FunctionalEvaluationDecision, ...]:
    """Decide, for every module of every retained candidate this round, whether it is selected
    for a real Agent 3 functional-evaluation round trip -- never for a degenerate candidate's
    own modules, and never at all when both functional criteria have zero weight.

    ``already_evidenced_module_ids`` (content-addressed module id strings) are modules that
    already have available functional evidence from an earlier round or a cache hit; never
    re-evaluated here.
    """
    if not isinstance(policy, FunctionalEvaluationSelectionPolicy):
        raise TypeError(
            "select_modules_for_functional_evaluation requires a "
            f"FunctionalEvaluationSelectionPolicy, got {policy!r}"
        )
    paired: list[tuple[CandidateModularizationBundle, ModularizationEvaluation]] = sorted(
        zip(search_result.retained, search_result.evaluations, strict=True),
        key=lambda item: _rank_key(item[1], item[0].modularization.modularization_id),
    )

    remaining_weight = total_functional_weight(weights)
    if remaining_weight <= 0:
        decisions: list[FunctionalEvaluationDecision] = []
        for index, (bundle, evaluation) in enumerate(paired):
            rank = index + 1
            candidate_id = bundle.modularization.modularization_id
            for module in bundle.modules:
                decisions.append(
                    FunctionalEvaluationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=FunctionalEvaluationDecisionOutcome.SKIP_ZERO_FUNCTIONAL_WEIGHT,
                        reason=(
                            "DYNAMIC_ISOLATION and SENSITIVITY_COHERENCE both have zero "
                            "(or omitted) weight -- functional evidence could not change "
                            "overall_score, so no Agent 3 call is ever worth making"
                        ),
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
        return tuple(decisions)

    scores_by_rank: tuple[Decimal | None, ...] = tuple(ev.overall_score for _b, ev in paired)

    decisions = []
    candidates_evaluated = 0
    budget_remaining = (
        policy.total_functional_evaluation_budget - functional_evaluations_used_so_far
    )

    for index, (bundle, evaluation) in enumerate(paired):
        rank = index + 1
        candidate_id = bundle.modularization.modularization_id
        module_count = len(bundle.modules)

        candidate_outcome: FunctionalEvaluationDecisionOutcome | None = None
        candidate_reason = ""
        if module_count <= 1:
            candidate_outcome = FunctionalEvaluationDecisionOutcome.SKIP_DEGENERATE_CANDIDATE
            candidate_reason = (
                "a one-module decomposition has no internal boundary to optimize and is "
                "excluded from ranking by default -- evaluating it could never change a "
                "ranking it is not eligible to win"
            )
        elif policy.rank_threshold is not None and rank > policy.rank_threshold:
            candidate_outcome = FunctionalEvaluationDecisionOutcome.SKIP_BELOW_RANK_THRESHOLD
            candidate_reason = f"rank {rank} exceeds rank_threshold={policy.rank_threshold}"
        elif policy.score_threshold is not None and (
            evaluation.overall_score is None or evaluation.overall_score < policy.score_threshold
        ):
            candidate_outcome = FunctionalEvaluationDecisionOutcome.SKIP_BELOW_SCORE_THRESHOLD
            candidate_reason = (
                f"overall_score={evaluation.overall_score!r} is below "
                f"score_threshold={policy.score_threshold!r}"
            )
        elif candidates_evaluated >= policy.max_candidates_per_generation:
            candidate_outcome = FunctionalEvaluationDecisionOutcome.SKIP_CANDIDATE_BUDGET_EXHAUSTED
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
                candidate_outcome = (
                    FunctionalEvaluationDecisionOutcome.SKIP_COULD_NOT_CHANGE_ORDERING
                )
                candidate_reason = (
                    f"best-case score (overall_score + remaining functional weight "
                    f"{remaining_weight!r}) could not plausibly cross either immediate "
                    "rank-neighbor"
                )

        if candidate_outcome is not None:
            for module in bundle.modules:
                decisions.append(
                    FunctionalEvaluationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=candidate_outcome,
                        reason=candidate_reason,
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
            continue

        modules_evaluated_for_candidate = 0
        candidate_got_at_least_one = False
        for module in bundle.modules:
            if module.module_id in already_evidenced_module_ids:
                decisions.append(
                    FunctionalEvaluationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=FunctionalEvaluationDecisionOutcome.SKIP_ALREADY_EVIDENCED,
                        reason=(
                            "this exact module content already has available functional evidence"
                        ),
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
                continue
            if (
                policy.max_modules_per_candidate is not None
                and modules_evaluated_for_candidate >= policy.max_modules_per_candidate
            ):
                decisions.append(
                    FunctionalEvaluationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=FunctionalEvaluationDecisionOutcome.SKIP_MODULE_LIMIT_REACHED,
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
                    FunctionalEvaluationDecision(
                        candidate_id=candidate_id,
                        module_id=module.module_id,
                        outcome=FunctionalEvaluationDecisionOutcome.SKIP_TOTAL_BUDGET_EXHAUSTED,
                        reason=(
                            "total_functional_evaluation_budget="
                            f"{policy.total_functional_evaluation_budget} already consumed "
                            "across this orchestration"
                        ),
                        structural_score=evaluation.overall_score,
                        rank=rank,
                    )
                )
                continue
            decisions.append(
                FunctionalEvaluationDecision(
                    candidate_id=candidate_id,
                    module_id=module.module_id,
                    outcome=FunctionalEvaluationDecisionOutcome.EVALUATE,
                    reason=(
                        f"survived structural gating at rank {rank} "
                        f"(overall_score={evaluation.overall_score!r})"
                    ),
                    structural_score=evaluation.overall_score,
                    rank=rank,
                )
            )
            modules_evaluated_for_candidate += 1
            budget_remaining -= 1
            candidate_got_at_least_one = True
        if candidate_got_at_least_one:
            candidates_evaluated += 1

    return tuple(decisions)


__all__ = ["select_modules_for_functional_evaluation", "total_functional_weight"]
