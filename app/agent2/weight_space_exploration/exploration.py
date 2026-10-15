"""Weight-Space Exploration and Stable Boundary Discovery: the public, read-only API.

``explore_weight_space`` is this package's one core entry point: evaluates every supplied
candidate modularization under every supplied weight vector (reusing
``app.agent2.module_evaluation.evaluate_modularization`` unchanged), selects the high-scoring
subset under an explicit, documented policy, and derives the stability measures task
instructions §4 names. Never mutates ``model`` or anything reachable from it, never alters
canonical model semantics, and never declares one solution "correct" (task instructions §6).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.agent2.module_calibration.types import ModuleCalibrationEvaluation
from app.agent2.module_evaluation import CriteriaWeights, evaluate_modularization
from app.agent2.module_evaluation.types import (
    CalibrationAggregationPolicy,
    TopologyFilteringPolicy,
)
from app.agent2.module_functional_evaluation.types import ModuleFunctionalEvaluationResult
from app.agent2.types import ModelSpecification, ModuleComponentType
from app.agent2.version import WEIGHT_SPACE_EXPLORATION_POLICY_VERSION
from app.agent2.weight_space_exploration.errors import WeightSpaceExplorationReferenceError
from app.agent2.weight_space_exploration.stability import (
    compute_boundary_stability,
    compute_co_membership_stability,
    compute_modularization_recurrence,
    select_high_scoring_solutions,
)
from app.agent2.weight_space_exploration.types import (
    HighScoringSolutionPolicy,
    ModuleCountStabilityGroup,
    WeightSpaceExplorationResult,
)

#: Mirrors ``WeightSpaceExplorationResult``'s own field defaults exactly -- the one place
#: both this module and that type agree on what "ambiguous" means when a caller does not
#: say otherwise.
_DEFAULT_AMBIGUOUS_BAND_LOW = Decimal("0.25")
_DEFAULT_AMBIGUOUS_BAND_HIGH = Decimal("0.75")


def explore_weight_space(
    model: ModelSpecification,
    modularization_ids: tuple[str, ...],
    weight_vectors: tuple[CriteriaWeights, ...],
    high_scoring_policy: HighScoringSolutionPolicy,
    *,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[str, Mapping[str, ModuleCalibrationEvaluation]] | None = None,
    calibration_aggregation_policy: CalibrationAggregationPolicy | None = None,
    functional_evaluation_evidence: (
        Mapping[str, Mapping[str, ModuleFunctionalEvaluationResult]] | None
    ) = None,
    ambiguous_band_low: Decimal = _DEFAULT_AMBIGUOUS_BAND_LOW,
    ambiguous_band_high: Decimal = _DEFAULT_AMBIGUOUS_BAND_HIGH,
    policy_version: str = WEIGHT_SPACE_EXPLORATION_POLICY_VERSION,
) -> WeightSpaceExplorationResult:
    """Evaluate every ``(modularization_id, weight_vector)`` pair, then derive the stability
    analysis task instructions §4 names, over whichever subset ``high_scoring_policy``
    selects (§5).

    Each of ``modularization_ids``/``weight_vectors`` is evaluated against every one of the
    other -- the full cartesian product, exactly like ``compare_modularizations``/
    ``evaluate_modularization_under_weights`` already evaluate one axis each; this function
    simply varies both at once. Never assumes one module count is preferred (task
    instructions §3): every evaluation, across every modularization and module count
    actually supplied, is preserved in ``.evaluations``, and ``.by_module_count`` reports
    stability separately per distinct module count in addition to the combined, overall
    measures.

    ``calibration_evidence`` (Calibration Evidence Integration into Weight-Space Exploration
    increment, optional, defaults to ``None``) is keyed by ``modularization_id`` ->
    ``{module_id: ModuleCalibrationEvaluation}`` -- each modularization's own evidence (if
    supplied) is held fixed across every weight vector it is evaluated under (the evidence
    itself never changes per weight vector, only its weighted *contribution* does), and is
    never computed here: it must already have been obtained by routing a
    ``ModuleCalibrationRequest`` per module through the Harness/Agent 3/Agent 4
    (``app.agent2.module_calibration``) before calling this function. Omitting it (the
    default) reproduces this function's exact pre-existing behavior with no change
    whatsoever -- ``CALIBRATION_INDEPENDENCE`` simply never appears in any evaluation's own
    ``criterion_scores``, exactly as before this increment.

    ``calibration_aggregation_policy`` (Calibration-Independence Aggregation increment,
    optional, defaults to ``None`` -> ``evaluate_modularization``'s own default,
    ``WEIGHTED_MEAN``) is held fixed across every ``(modularization_id, weight_vector)`` pair
    evaluated -- the same aggregation method is applied everywhere evidence exists.

    ``functional_evaluation_evidence`` (Functional Modularity Criteria from Agents 3 and 4
    increment, optional, defaults to ``None``) follows the identical per-modularization
    lookup convention as ``calibration_evidence`` -- held fixed across every weight vector,
    never computed here (obtained by routing a ``ModuleFunctionalEvaluationRequest`` per
    module through the Harness/Agent 3, ``app.agent2.module_functional_evaluation``, before
    calling this function). Omitting it (the default) reproduces this function's exact
    pre-existing behavior with no change whatsoever.

    ``ambiguous_band_low``/``ambiguous_band_high`` name the open interval a boundary/
    co-membership frequency must fall strictly inside to be reported among
    ``.ambiguous_boundaries``/``.ambiguous_co_memberships`` (task instructions §6,
    "unresolved/ambiguous boundaries").

    Raises ``WeightSpaceExplorationReferenceError`` for a malformed input. Never raises for an
    empty high-scoring set, a genuinely unstable boundary, or an unavailable criterion -- all
    three are normal, disclosed outcomes reported in the result, never exceptions.
    """
    if not isinstance(model, ModelSpecification):
        raise WeightSpaceExplorationReferenceError(
            f"explore_weight_space requires a ModelSpecification, got {model!r}"
        )
    if not isinstance(modularization_ids, tuple) or not modularization_ids:
        raise WeightSpaceExplorationReferenceError(
            "explore_weight_space requires a non-empty tuple of modularization_id, got "
            f"{modularization_ids!r}"
        )
    if not isinstance(weight_vectors, tuple) or not weight_vectors:
        raise WeightSpaceExplorationReferenceError(
            "explore_weight_space requires a non-empty tuple of CriteriaWeights, got "
            f"{weight_vectors!r}"
        )

    evaluations = tuple(
        evaluate_modularization(
            model,
            modularization_id,
            weights,
            topology_filtering=topology_filtering,
            calibration_evidence=(
                calibration_evidence.get(modularization_id)
                if calibration_evidence is not None
                else None
            ),
            calibration_aggregation_policy=calibration_aggregation_policy,
            functional_evaluation_evidence=(
                functional_evaluation_evidence.get(modularization_id)
                if functional_evaluation_evidence is not None
                else None
            ),
        )
        for modularization_id in modularization_ids
        for weights in weight_vectors
    )

    high_scoring = select_high_scoring_solutions(evaluations, high_scoring_policy)
    high_scoring_ids = frozenset(e.evaluation_id for e in high_scoring)

    modularization_recurrence = compute_modularization_recurrence(evaluations, high_scoring_ids)
    boundary_stability = compute_boundary_stability(model, high_scoring)
    co_membership_stability = compute_co_membership_stability(
        model, high_scoring, ModuleComponentType.SPECIES
    )

    ambiguous_boundaries = tuple(
        b for b in boundary_stability if ambiguous_band_low < b.cut_frequency < ambiguous_band_high
    )
    ambiguous_co_memberships = tuple(
        c
        for c in co_membership_stability
        if ambiguous_band_low < c.co_membership_frequency < ambiguous_band_high
    )

    module_counts = sorted({e.module_count for e in evaluations})
    module_count_groups = []
    for module_count in module_counts:
        scoped_high_scoring = tuple(e for e in high_scoring if e.module_count == module_count)
        module_count_groups.append(
            ModuleCountStabilityGroup(
                module_count=module_count,
                high_scoring_solution_count=len(scoped_high_scoring),
                boundary_stability=compute_boundary_stability(model, scoped_high_scoring),
                co_membership_stability=compute_co_membership_stability(
                    model, scoped_high_scoring, ModuleComponentType.SPECIES
                ),
            )
        )

    warnings: tuple[str, ...] = ()
    if not high_scoring:
        warnings = (
            "No evaluation had an available overall_score -- the high-scoring solution set "
            "is empty, so every stability measure below is also empty. Never fabricated.",
        )

    return WeightSpaceExplorationResult(
        exploration_id=f"exploration::{model.model_id}::{len(modularization_ids)}-modularizations::{len(weight_vectors)}-vectors",
        model_id=model.model_id,
        weight_vectors=weight_vectors,
        evaluations=evaluations,
        high_scoring_policy=high_scoring_policy,
        high_scoring_evaluation_ids=tuple(sorted(high_scoring_ids)),
        modularization_recurrence=modularization_recurrence,
        boundary_stability=boundary_stability,
        co_membership_stability=co_membership_stability,
        ambiguous_boundaries=ambiguous_boundaries,
        ambiguous_co_memberships=ambiguous_co_memberships,
        ambiguous_band_low=ambiguous_band_low,
        ambiguous_band_high=ambiguous_band_high,
        by_module_count=tuple(module_count_groups),
        policy_version=policy_version,
        warnings=warnings,
        provenance_refs=tuple(f"modularization::{mid}" for mid in modularization_ids),
    )


__all__ = ["explore_weight_space"]
