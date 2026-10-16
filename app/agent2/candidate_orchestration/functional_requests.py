"""Turning every ``EVALUATE`` decision into either a real ``ModuleFunctionalEvaluationRequest``
(for the caller -- always the Harness, never Agent 2 itself -- to route through Agent 3) or,
when the whole network/module cannot support the analysis, a disclosed ``UNSUPPORTED_ANALYSIS``/
``INSUFFICIENT_TARGETS`` evaluation resolved entirely locally. Reuses ``app.agent2
.module_functional_evaluation``'s own existing, unchanged producer functions -- no new
functional-evaluation-request-construction logic (mirrors ``requests.py``'s own identical role
for calibration exactly).

Checks readiness/target-count *before* calling ``build_module_functional_evaluation_request``
(rather than catching ``ModuleFunctionalEvaluationReferenceError`` and sniffing its message) so
the local-resolution choice is never guessed from exception text.
"""

from __future__ import annotations

import uuid

from app.agent2.antimony import generate_antimony
from app.agent2.candidate_orchestration.types import (
    FunctionalEvaluationDecision,
    FunctionalEvaluationDecisionOutcome,
    FunctionalEvaluationRunRequestEnvelope,
)
from app.agent2.modularization_search.assembly import attach_bundle
from app.agent2.modularization_search.types import CandidateModularizationBundle
from app.agent2.module_functional_evaluation import (
    ModuleFunctionalEvaluationResult,
    build_module_functional_evaluation_request,
    insufficient_targets_evaluation,
    select_functional_evaluation_targets,
    unsupported_analysis_evaluation,
)
from app.agent2.module_functional_evaluation.request_builder import (
    MIN_EXTERNAL_TARGETS,
    MIN_INTERNAL_TARGETS,
)
from app.agent2.types import AntimonyArtifactReadiness, ModelSpecification


def build_functional_evaluation_requests(
    model: ModelSpecification,
    retained_bundles: tuple[CandidateModularizationBundle, ...],
    decisions: tuple[FunctionalEvaluationDecision, ...],
    *,
    correlation_id: str,
    run_id: str,
) -> tuple[
    tuple[FunctionalEvaluationRunRequestEnvelope, ...], tuple[ModuleFunctionalEvaluationResult, ...]
]:
    """For every ``EVALUATE`` decision, build its own request (or resolve it locally as
    ``UNSUPPORTED_ANALYSIS``/``INSUFFICIENT_TARGETS`` when the whole network/module cannot
    support the analysis). Returns ``(requests_needing_a_round_trip,
    locally_resolved_evidence)``.

    ``run_id`` is a shared prefix -- each individual request still gets its own unique,
    deterministic ``run_id`` (``f"{run_id}::functional::{module_id}"``) so a caller can
    correlate every request back to this one orchestration round without any two requests
    colliding (and without colliding with that same module's own calibration ``run_id``, which
    uses a distinct ``f"{run_id}::{module_id}"`` shape with no ``"functional"`` segment).
    """
    bundles_by_candidate_id = {b.modularization.modularization_id: b for b in retained_bundles}
    requests: list[FunctionalEvaluationRunRequestEnvelope] = []
    locally_resolved: list[ModuleFunctionalEvaluationResult] = []
    for decision in decisions:
        if decision.outcome is not FunctionalEvaluationDecisionOutcome.EVALUATE:
            continue
        bundle = bundles_by_candidate_id.get(decision.candidate_id)
        if bundle is None:
            raise ValueError(
                "build_functional_evaluation_requests: EVALUATE decision names unknown "
                f"candidate_id {decision.candidate_id!r} -- not present in retained_bundles"
            )
        eval_model = attach_bundle(model, bundle)
        modularization_id = bundle.modularization.modularization_id
        module_id = decision.module_id
        request_id = f"functional-evaluation-request::{run_id}::{module_id}::{uuid.uuid4().hex[:8]}"
        module_run_id = f"{run_id}::functional::{module_id}"

        package = generate_antimony(eval_model)
        if package.full_antimony.readiness is not AntimonyArtifactReadiness.EXECUTABLE:
            locally_resolved.append(
                unsupported_analysis_evaluation(
                    parent_model_id=model.model_id,
                    modularization_id=modularization_id,
                    module_id=module_id,
                    reason=(
                        "whole network has no eligible executable artifact (readiness="
                        f"{package.full_antimony.readiness.value!r})"
                    ),
                    request_id=request_id,
                    correlation_id=correlation_id,
                    run_id=module_run_id,
                )
            )
            continue

        targets = select_functional_evaluation_targets(eval_model, modularization_id, module_id)
        internal_count = sum(1 for t in targets if t.is_internal)
        external_count = len(targets) - internal_count
        if internal_count < MIN_INTERNAL_TARGETS or external_count < MIN_EXTERNAL_TARGETS:
            locally_resolved.append(
                insufficient_targets_evaluation(
                    parent_model_id=model.model_id,
                    modularization_id=modularization_id,
                    module_id=module_id,
                    reason=(
                        f"only {internal_count} internal and {external_count} external "
                        f"perturbation targets (need >= {MIN_INTERNAL_TARGETS} internal, "
                        f">= {MIN_EXTERNAL_TARGETS} external)"
                    ),
                    request_id=request_id,
                    correlation_id=correlation_id,
                    run_id=module_run_id,
                )
            )
            continue

        request = build_module_functional_evaluation_request(
            eval_model,
            modularization_id,
            module_id,
            correlation_id=correlation_id,
            run_id=module_run_id,
            request_id=request_id,
        )
        requests.append(FunctionalEvaluationRunRequestEnvelope(decision=decision, request=request))
    return tuple(requests), tuple(locally_resolved)


__all__ = ["build_functional_evaluation_requests"]
