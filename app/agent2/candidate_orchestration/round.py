"""``run_candidate_search_round``: the public, single-round entry point this package exposes --
one bounded search (``search_candidate_modularizations``, unchanged) scored under already-
available evidence, gated for further calibration (``select_candidates_for_calibration``), and
turned into ready-to-route requests (``build_calibration_requests``). A caller (always the
Harness) repeats this call across rounds, feeding each round's own newly-obtained evidence back
in as the next round's ``calibration_evidence`` -- the recursive loop itself lives entirely
outside this package (task instructions §1: Agent 2 never calls Agent 3/Agent 4, and never
decides how many rounds to run or when to stop; it only ever scores and gates one round at a
time).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.agent2.candidate_orchestration.errors import CandidateOrchestrationReferenceError
from app.agent2.candidate_orchestration.functional_requests import (
    build_functional_evaluation_requests,
)
from app.agent2.candidate_orchestration.functional_selection import (
    select_modules_for_functional_evaluation,
)
from app.agent2.candidate_orchestration.requests import build_calibration_requests
from app.agent2.candidate_orchestration.selection import select_candidates_for_calibration
from app.agent2.candidate_orchestration.types import (
    CalibrationSelectionPolicy,
    CandidateSearchRoundResult,
    FunctionalEvaluationSelectionPolicy,
)
from app.agent2.modularization_search.assembly import extract_bundle
from app.agent2.modularization_search.identity import ModuleContentKey, derive_module_id
from app.agent2.modularization_search.search import search_candidate_modularizations
from app.agent2.modularization_search.types import SearchConstraints, SearchPolicy
from app.agent2.module_calibration.types import ModuleCalibrationEvaluation
from app.agent2.module_evaluation.types import (
    CalibrationAggregationPolicy,
    CriteriaWeights,
    TopologyFilteringPolicy,
)
from app.agent2.module_functional_evaluation.types import ModuleFunctionalEvaluationResult
from app.agent2.submodel_materialization.errors import SubmodelMaterializationReferenceError
from app.agent2.submodel_materialization.materialization import materialize_submodel
from app.agent2.types import ModelSpecification
from app.agent2.version import CANDIDATE_ORCHESTRATION_POLICY_VERSION
from app.agent2.weight_space_exploration.types import HighScoringSolutionPolicy


def build_submodel(
    model: ModelSpecification, seed_modularization_id: str, module_id: str
) -> tuple[ModelSpecification, str]:
    """Wrap one already-decomposed module as its own, standalone ``ModelSpecification`` --
    recursive readiness (task instructions §5): the identical ``run_candidate_search_round``
    call below works on this submodel exactly as it does on any other model, with no code path
    change.

    **Canonical Submodel Materialization increment**: delegates to ``app.agent2
    .submodel_materialization.materialize_submodel``, which genuinely scopes
    ``full_network``/``kinetic_laws``/``parameters`` down to the module's own dependency
    closure -- this function's own external signature/return shape
    (``tuple[ModelSpecification, str]``) is unchanged, but it no longer carries the parent's
    entire, untruncated network forward. Before this increment, a cross-boundary edge to a
    reaction *outside* the module was counted as a cut edge by ``TOPOLOGICAL_SEPARATION``
    exactly as any other network edge leaving the current seed was, because the "submodel" was
    only a re-scoped modularization sitting on the full network -- a disclosed, acceptable
    scope limit for "usable" at the time, now fixed.

    Raises ``CandidateOrchestrationReferenceError`` if ``module_id`` is not a real module of
    ``seed_modularization_id``, or if it has zero internal reactions.
    """
    bundle = extract_bundle(model, seed_modularization_id)
    known_module_ids = {m.module_id for m in bundle.modules}
    if module_id not in known_module_ids:
        raise CandidateOrchestrationReferenceError(
            f"build_submodel: module_id {module_id!r} is not a module of "
            f"{seed_modularization_id!r} (known: {sorted(known_module_ids)})"
        )
    try:
        result = materialize_submodel(model, seed_modularization_id, module_id)
    except SubmodelMaterializationReferenceError as exc:
        raise CandidateOrchestrationReferenceError(str(exc)) from exc
    return result.submodel, result.submodel_modularization_id


def run_candidate_search_round(
    model: ModelSpecification,
    seed_modularization_id: str,
    criteria_weights: CriteriaWeights,
    search_policy: SearchPolicy,
    calibration_selection_policy: CalibrationSelectionPolicy,
    *,
    constraints: SearchConstraints | None = None,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[ModuleContentKey, ModuleCalibrationEvaluation] | None = None,
    calibration_aggregation_policy: CalibrationAggregationPolicy | None = None,
    functional_evaluation_evidence: (
        Mapping[ModuleContentKey, ModuleFunctionalEvaluationResult] | None
    ) = None,
    apply_resolution_correction: bool = False,
    exclude_single_module_from_ranking: bool = True,
    stability_weight_vectors: tuple[CriteriaWeights, ...] | None = None,
    high_scoring_policy: HighScoringSolutionPolicy | None = None,
    calibration_runs_used_so_far: int = 0,
    functional_evaluation_selection_policy: FunctionalEvaluationSelectionPolicy | None = None,
    functional_evaluations_used_so_far: int = 0,
    correlation_id: str,
    run_id: str,
    policy_version: str = CANDIDATE_ORCHESTRATION_POLICY_VERSION,
) -> CandidateSearchRoundResult:
    """Run one bounded candidate search (``search_candidate_modularizations``, entirely
    unchanged) under whatever ``calibration_evidence`` already exists, then gate the result
    (``select_candidates_for_calibration``) and build real requests for whatever the gate
    selects (``build_calibration_requests``).

    A module already named by ``calibration_evidence`` (by content -- its own content-addressed
    module id is always ``derive_module_id`` of that same content key, so no separate
    "already evidenced" bookkeeping is ever required from the caller) is never recalibrated,
    regardless of what that evidence disclosed (a real negative/unavailable outcome is still a
    real, already-spent attempt). ``calibration_runs_used_so_far`` is always supplied by the
    caller's own running state across rounds -- this function holds no state of its own between
    calls (task instructions §1: the recursive loop itself lives entirely outside this
    package).

    Never calls Agent 3 or Agent 4 -- ``calibration_requests`` only ever carries already-built,
    not-yet-routed ``ModuleCalibrationRequest``s; ``locally_resolved_evidence`` only ever
    carries a disclosed ``BOUNDARY_INADEQUATE`` outcome decided without any round trip at all.

    ``functional_evaluation_evidence`` (Functional Modularity Criteria from Agents 3 and 4
    increment, optional) threads straight through to ``search_candidate_modularizations``
    unchanged -- the identical content-addressed accumulation convention as
    ``calibration_evidence``.

    ``functional_evaluation_selection_policy`` (Automatic Functional-Evaluation Selection and
    Caching increment, optional): when supplied, mirrors ``calibration_selection_policy``'s own
    role exactly, but gating a real Agent 3 functional-evaluation round trip
    (``select_modules_for_functional_evaluation``/``build_functional_evaluation_requests``)
    instead of an Agent 3/Agent 4 calibration round trip -- a genuinely separate gate with its
    own separate budget (task instructions §5), never required to select the identical
    candidates/modules ``calibration_selection_policy`` does. ``None`` (the default) reproduces
    the exact prior behavior: zero functional-evaluation decisions/requests, never a single
    Agent 3 call Agent 2 initiates on its own.
    """
    search_result = search_candidate_modularizations(
        model,
        seed_modularization_id,
        criteria_weights,
        search_policy,
        constraints=constraints,
        topology_filtering=topology_filtering,
        calibration_evidence=calibration_evidence,
        calibration_aggregation_policy=calibration_aggregation_policy,
        functional_evaluation_evidence=functional_evaluation_evidence,
        apply_resolution_correction=apply_resolution_correction,
        exclude_single_module_from_ranking=exclude_single_module_from_ranking,
        stability_weight_vectors=stability_weight_vectors,
        high_scoring_policy=high_scoring_policy,
    )
    already_evidenced_module_ids = frozenset(
        derive_module_id(key) for key in (calibration_evidence or {})
    )
    decisions = select_candidates_for_calibration(
        search_result,
        criteria_weights,
        calibration_selection_policy,
        already_evidenced_module_ids=already_evidenced_module_ids,
        calibration_runs_used_so_far=calibration_runs_used_so_far,
    )
    requests, locally_resolved = build_calibration_requests(
        model,
        search_result.retained,
        decisions,
        correlation_id=correlation_id,
        run_id=run_id,
    )

    functional_decisions: tuple = ()
    functional_requests: tuple = ()
    locally_resolved_functional: tuple = ()
    if functional_evaluation_selection_policy is not None:
        already_evidenced_functional_module_ids = frozenset(
            derive_module_id(key) for key in (functional_evaluation_evidence or {})
        )
        functional_decisions = select_modules_for_functional_evaluation(
            search_result,
            criteria_weights,
            functional_evaluation_selection_policy,
            already_evidenced_module_ids=already_evidenced_functional_module_ids,
            functional_evaluations_used_so_far=functional_evaluations_used_so_far,
        )
        functional_requests, locally_resolved_functional = build_functional_evaluation_requests(
            model,
            search_result.retained,
            functional_decisions,
            correlation_id=correlation_id,
            run_id=run_id,
        )

    return CandidateSearchRoundResult(
        search_result=search_result,
        calibration_decisions=decisions,
        calibration_requests=requests,
        locally_resolved_evidence=locally_resolved,
        policy_version=policy_version,
        functional_evaluation_decisions=functional_decisions,
        functional_evaluation_requests=functional_requests,
        locally_resolved_functional_evidence=locally_resolved_functional,
    )


__all__ = ["build_submodel", "run_candidate_search_round"]
