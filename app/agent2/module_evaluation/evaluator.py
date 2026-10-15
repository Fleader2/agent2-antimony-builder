"""Module Boundary Evaluation Framework: the public, read-only evaluation API.

``evaluate_modularization`` is this package's one core entry point: given an already-assembled
``ModelSpecification`` (``GENERATED`` or ``IMPORTED`` -- no origin-specific branch exists
anywhere in this module) and one of its own ``modularization_id``s, scores it under an
explicit ``CriteriaWeights`` vector and returns a ``ModularizationEvaluation``. Never mutates
``model`` (or anything reachable from it), never alters executable whole-network semantics or
standalone-module generation (``app.agent2.antimony`` is never imported here), and never picks
a "winner" among alternatives -- every function here returns individual, inspectable results
for the caller (today) or a future Workbench UI (task instructions §5) to compare.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.agent2.module_calibration.types import ModuleCalibrationEvaluation
from app.agent2.module_evaluation.calibration_adapter import (
    DEFAULT_CALIBRATION_AGGREGATION_POLICY,
    score_calibration_independence,
)
from app.agent2.module_evaluation.criteria import (
    IMPLEMENTED_CRITERIA,
    score_boundary_sparsity,
    score_compartment_coherence,
    score_ec_class_coherence,
    score_topological_separation,
)
from app.agent2.module_evaluation.errors import ModuleEvaluationReferenceError
from app.agent2.module_evaluation.types import (
    CalibrationAggregationPolicy,
    CriteriaWeights,
    ModularizationCriterion,
    ModularizationCriterionScore,
    ModularizationEvaluation,
    TopologyFilteringPolicy,
)
from app.agent2.types import ModelSpecification, ModuleMembership, ModulePort
from app.agent2.version import MODULE_EVALUATION_POLICY_VERSION


def _require_model_specification(model: ModelSpecification) -> ModelSpecification:
    if not isinstance(model, ModelSpecification):
        raise ModuleEvaluationReferenceError(
            f"evaluate_modularization requires a ModelSpecification, got {model!r}"
        )
    return model


def _require_criteria_weights(weights: CriteriaWeights) -> CriteriaWeights:
    if not isinstance(weights, CriteriaWeights):
        raise ModuleEvaluationReferenceError(
            f"evaluate_modularization requires a CriteriaWeights, got {weights!r}"
        )
    return weights


def _weight_tag(
    weights: CriteriaWeights, criteria: tuple[ModularizationCriterion, ...]
) -> str:
    """A deterministic, human-inspectable fragment of ``evaluation_id`` naming every positive
    weight actually in effect -- never an opaque hash, consistent with every other id in this
    codebase being a meaningful, debuggable string."""
    parts = [
        f"{criterion.value}-{weights.raw_weight(criterion)}"
        for criterion in criteria
        if weights.raw_weight(criterion) > 0
    ]
    return "_".join(parts) if parts else "none"


def evaluate_modularization(
    model: ModelSpecification,
    modularization_id: str,
    weights: CriteriaWeights,
    *,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[str, ModuleCalibrationEvaluation] | None = None,
    calibration_aggregation_policy: CalibrationAggregationPolicy | None = None,
    null_reference_scores: Mapping[ModularizationCriterion, Decimal] | None = None,
    policy_version: str = MODULE_EVALUATION_POLICY_VERSION,
) -> ModularizationEvaluation:
    """Score one ``model.modularizations`` entry under ``weights``.

    Every criterion ``app.agent2.module_evaluation.criteria`` currently implements is always
    computed and reported in ``ModularizationEvaluation.criterion_scores`` -- regardless of
    that criterion's own weight (task instructions: "each criterion must remain separately
    inspectable"). ``weights`` only ever gates each criterion's own *weighted contribution* to
    ``overall_score``, never whether its raw score is computed at all.

    ``topology_filtering`` (Topology Hub/Currency Component Filtering increment, optional,
    defaults to ``None`` -- curated name-based defaults only, no per-evaluation overrides, a
    built-in default hub-degree threshold) is threaded through to
    ``TOPOLOGICAL_SEPARATION`` alone; every other criterion is completely unaffected by it.

    ``calibration_evidence`` (Recursive Module Evaluation Orchestration increment, optional,
    defaults to ``None``) is a caller-supplied ``{module_id: ModuleCalibrationEvaluation}``
    mapping -- always obtained by routing one ``ModuleCalibrationRequest`` per module through
    the Harness/Agent 3/Agent 4 (``app.agent2.module_calibration``), **never computed by this
    function itself** (this package still performs no simulation or fitting, and Agent 2 still
    never calls Agent 3/Agent 4 directly). Only when given is ``CALIBRATION_INDEPENDENCE``
    computed and added to ``criterion_scores`` at all -- omitting it (the default) reproduces
    this function's exact pre-existing behavior with no change whatsoever, and that previously-
    reserved criterion simply does not appear, exactly as before this increment.

    ``calibration_aggregation_policy`` (Calibration-Independence Aggregation increment,
    optional, defaults to ``None`` -> ``DEFAULT_CALIBRATION_AGGREGATION_POLICY``, i.e.
    ``WEIGHTED_MEAN``) is only ever consulted when ``calibration_evidence`` is also given -- it
    selects how several modules' own per-module ``CALIBRATION_INDEPENDENCE`` contributions are
    combined into one aggregate (``app.agent2.module_evaluation.calibration_adapter``;
    ``MINIMUM``/``WEIGHTED_MEAN``/``LOWER_QUANTILE``/``FRACTION_ABOVE_THRESHOLD``), replacing
    the single, previously hard-coded weakest-link policy. Every per-module score is always
    disclosed on ``CalibrationIndependenceDetail.per_module_scores`` regardless of which method
    produced the aggregate.

    ``null_reference_scores`` (Module-Count / Resolution Bias Audit increment, optional,
    defaults to ``None``) is a caller-supplied ``{criterion: Decimal}`` mapping -- each
    criterion's own score for a deterministic, structure-blind partition matched to this
    modularization's own module count (``app.agent2.resolution_audit``, never computed by this
    function itself). When a matching, available entry exists for a criterion,
    ``ModularizationCriterionScore.corrected_score`` is populated (``(raw_score -
    null_reference_score) / (1 - null_reference_score)``, ``None`` when the null score is
    itself ``>= 1``), and that criterion's own *clamped-to-[0, 1]* corrected score -- never the
    raw score -- drives ``weighted_contribution``/``overall_score`` instead. ``raw_score`` is
    always preserved unchanged regardless. Omitting ``null_reference_scores`` (the default)
    reproduces this function's exact pre-existing behavior with no change whatsoever.

    Raises ``ModuleEvaluationReferenceError`` if ``model`` is not a real ``ModelSpecification``,
    ``weights`` is not a real ``CriteriaWeights``, or ``modularization_id`` does not name a real
    entry in ``model.modularizations``. Never raises for missing *evidence* -- that is always a
    disclosed ``ModularizationCriterionScore.available=False``, never an exception.
    """
    _require_model_specification(model)
    _require_criteria_weights(weights)
    modularizations_by_id = {m.modularization_id: m for m in model.modularizations}
    modularization = modularizations_by_id.get(modularization_id)
    if modularization is None:
        raise ModuleEvaluationReferenceError(
            f"evaluate_modularization: modularization_id {modularization_id!r} does not "
            f"exist in model.modularizations (known: {sorted(modularizations_by_id)})"
        )

    memberships: tuple[ModuleMembership, ...] = tuple(
        m for m in model.module_memberships if m.modularization_id == modularization_id
    )
    ports: tuple[ModulePort, ...] = tuple(
        p for p in model.module_ports if p.modularization_id == modularization_id
    )

    raw_results = {
        ModularizationCriterion.TOPOLOGICAL_SEPARATION: score_topological_separation(
            model.full_network, memberships, topology_filtering
        ),
        ModularizationCriterion.BOUNDARY_SPARSITY: score_boundary_sparsity(memberships, ports),
        ModularizationCriterion.COMPARTMENT_COHERENCE: score_compartment_coherence(
            model.full_network, memberships
        ),
        ModularizationCriterion.EC_CLASS_COHERENCE: score_ec_class_coherence(
            model.full_network, memberships
        ),
    }
    criteria_to_score = list(IMPLEMENTED_CRITERIA)
    if calibration_evidence is not None:
        criteria_to_score.append(ModularizationCriterion.CALIBRATION_INDEPENDENCE)
        raw_results[ModularizationCriterion.CALIBRATION_INDEPENDENCE] = (
            score_calibration_independence(
                modularization.module_ids,
                calibration_evidence,
                policy=calibration_aggregation_policy or DEFAULT_CALIBRATION_AGGREGATION_POLICY,
            )
        )

    criterion_scores: list[ModularizationCriterionScore] = []
    missing_evidence_warnings: list[str] = []
    for criterion in criteria_to_score:
        result = raw_results[criterion]
        raw_weight = weights.raw_weight(criterion)
        normalized_weight = weights.normalized_weight(criterion)

        null_reference_score = None
        corrected_score = None
        effective_score = result.raw_score
        if result.available and null_reference_scores is not None:
            candidate_null = null_reference_scores.get(criterion)
            if candidate_null is not None:
                null_reference_score = candidate_null
                if candidate_null < 1:
                    corrected_score = (result.raw_score - candidate_null) / (
                        Decimal(1) - candidate_null
                    )
                    effective_score = max(Decimal(0), min(Decimal(1), corrected_score))

        weighted_contribution = (
            normalized_weight * effective_score
            if result.available and normalized_weight > 0
            else None
        )
        criterion_scores.append(
            ModularizationCriterionScore(
                criterion=criterion,
                available=result.available,
                raw_score=result.raw_score,
                raw_weight=raw_weight,
                normalized_weight=normalized_weight,
                weighted_contribution=weighted_contribution,
                explanation=result.explanation,
                warnings=result.warnings,
                detail=result.detail,
                null_reference_score=null_reference_score,
                corrected_score=corrected_score,
            )
        )
        if not result.available and raw_weight > 0:
            missing_evidence_warnings.append(
                f"{criterion.value} has a positive weight ({raw_weight}) but is unavailable: "
                f"{result.explanation}"
            )

    evaluated_weight_fraction = sum(
        (cs.normalized_weight for cs in criterion_scores if cs.available), Decimal(0)
    )
    overall_score = (
        sum(
            (
                cs.weighted_contribution
                for cs in criterion_scores
                if cs.weighted_contribution is not None
            ),
            Decimal(0),
        )
        if evaluated_weight_fraction > 0
        else None
    )

    weight_tag = _weight_tag(weights, tuple(criteria_to_score))
    return ModularizationEvaluation(
        evaluation_id=f"evaluation::{modularization_id}::{weight_tag}",
        modularization_id=modularization_id,
        module_count=len(modularization.module_ids),
        criterion_scores=tuple(criterion_scores),
        weights=weights,
        overall_score=overall_score,
        evaluated_weight_fraction=evaluated_weight_fraction,
        policy_version=policy_version,
        warnings=tuple(missing_evidence_warnings),
        provenance_refs=(
            f"modularization::{modularization_id}",
            f"module-evaluation-policy::{policy_version}",
        ),
    )


def evaluate_modularization_under_weights(
    model: ModelSpecification,
    modularization_id: str,
    weight_vectors: tuple[CriteriaWeights, ...],
    *,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[str, ModuleCalibrationEvaluation] | None = None,
    calibration_aggregation_policy: CalibrationAggregationPolicy | None = None,
    policy_version: str = MODULE_EVALUATION_POLICY_VERSION,
) -> tuple[ModularizationEvaluation, ...]:
    """Score the identical modularization once per supplied ``CriteriaWeights`` vector (task
    instructions §5, weight-space exploration) -- a thin, deterministic loop over
    ``evaluate_modularization``, never a UI, never a search over weight space on its own
    (a caller/future Workbench UI supplies every vector to try). ``topology_filtering``/
    ``calibration_evidence``/``calibration_aggregation_policy`` (if given) are each held fixed
    across every weight vector -- weight-space exploration and this evidence are independent
    axes: a module's own calibration-independence evidence does not change depending on which
    weight vector is being scored, only its *contribution* to ``overall_score`` does
    (Calibration Evidence Integration into Weight-Space Exploration increment).

    Returns evaluations in the identical order ``weight_vectors`` was given, one-to-one --
    never reordered, never deduplicated, never ranked.
    """
    if not isinstance(weight_vectors, tuple) or not weight_vectors:
        raise ModuleEvaluationReferenceError(
            "evaluate_modularization_under_weights requires a non-empty tuple of "
            f"CriteriaWeights, got {weight_vectors!r}"
        )
    return tuple(
        evaluate_modularization(
            model,
            modularization_id,
            weights,
            topology_filtering=topology_filtering,
            calibration_evidence=calibration_evidence,
            calibration_aggregation_policy=calibration_aggregation_policy,
            policy_version=policy_version,
        )
        for weights in weight_vectors
    )


def compare_modularizations(
    model: ModelSpecification,
    modularization_ids: tuple[str, ...],
    weights: CriteriaWeights,
    *,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[str, Mapping[str, ModuleCalibrationEvaluation]] | None = None,
    calibration_aggregation_policy: CalibrationAggregationPolicy | None = None,
    policy_version: str = MODULE_EVALUATION_POLICY_VERSION,
) -> tuple[ModularizationEvaluation, ...]:
    """Score several alternative modularizations -- of possibly different module counts --
    under the identical ``weights`` (task instructions §6). Never assumes more or fewer
    modules is intrinsically better, and never picks a winner: returns one evaluation per
    requested id, in the identical order given, for the caller to compare.

    ``calibration_evidence`` (Calibration Evidence Integration into Weight-Space Exploration
    increment), when given, is keyed by ``modularization_id`` -> ``{module_id:
    ModuleCalibrationEvaluation}`` -- each modularization's own evidence (if any) is looked up
    by its own id and passed to its own ``evaluate_modularization`` call alone, never shared
    across different modularizations' own, structurally distinct modules.
    ``calibration_aggregation_policy`` (Calibration-Independence Aggregation increment), when
    given, is held fixed across every modularization compared -- the same aggregation method
    is applied to whichever evidence each one has.
    """
    if not isinstance(modularization_ids, tuple) or not modularization_ids:
        raise ModuleEvaluationReferenceError(
            "compare_modularizations requires a non-empty tuple of modularization_id, got "
            f"{modularization_ids!r}"
        )
    return tuple(
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
            policy_version=policy_version,
        )
        for modularization_id in modularization_ids
    )


__all__ = [
    "compare_modularizations",
    "evaluate_modularization",
    "evaluate_modularization_under_weights",
]
