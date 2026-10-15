"""Building one ``ModuleFunctionalEvaluationRequest`` for one candidate module (task
instructions §4: "candidate module -> standalone module handoff -> Harness -> Agent 3"), and
resolving the two cases where no Harness round trip is needed at all: the whole network has no
eligible executable artifact (``unsupported_analysis_evaluation``), or too few internal/
external perturbation targets exist to compute a meaningful signal
(``insufficient_targets_evaluation``).

Works identically for a ``GENERATED`` or ``IMPORTED`` ``model``, and identically whether
``model`` is itself a previously-derived module/submodel re-assembled as its own
``ModelSpecification`` (recursive readiness) -- every value read here comes from
``model.full_network``/``.module_memberships``/``.module_ports``/``.parameters`` alone, never
from anything origin-specific.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.agent2.antimony import generate_antimony
from app.agent2.module_functional_evaluation.errors import ModuleFunctionalEvaluationReferenceError
from app.agent2.module_functional_evaluation.types import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationRequest,
    ModuleFunctionalEvaluationResult,
    PerturbationTargetSpec,
)
from app.agent2.pipeline import build_canonical_downstream_handoff
from app.agent2.types import (
    AntimonyArtifactReadiness,
    ModelSpecification,
    ModuleComponentType,
)
from app.agent2.version import MODULE_FUNCTIONAL_EVALUATION_POLICY_VERSION

#: Deliberately modest, mirroring Agent 3's own Version 1 perturbation-policy defaults
#: (``app.agent3.perturbation.DEFAULT_PERTURBATION_FRACTION``/``DEFAULT_MAX_TARGETS_PER_KIND``
#: on the sibling repository) -- a fixed, small, deterministic battery, never tuned per run.
DEFAULT_MAX_TARGETS_PER_KIND = 5
DEFAULT_PERTURBATION_FRACTION = Decimal("0.1")
#: At least one internal *and* one external target are required for every dynamic-isolation
#: sub-measure (spillover, external dependence, boundary capture) to be computable at all;
#: sensitivity coherence additionally requires at least two internal targets (a "similarity
#: between profiles" needs at least two profiles) -- enforced together here, since both
#: criteria are scored from the identical request/result.
MIN_INTERNAL_TARGETS = 2
MIN_EXTERNAL_TARGETS = 1


def _member_reaction_ids(
    model: ModelSpecification, modularization_id: str, module_id: str
) -> set[str]:
    return {
        m.component_id
        for m in model.module_memberships
        if m.modularization_id == modularization_id
        and m.module_id == module_id
        and m.component_type is ModuleComponentType.REACTION
    }


def _member_species_ids(
    model: ModelSpecification, modularization_id: str, module_id: str
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                m.component_id
                for m in model.module_memberships
                if m.modularization_id == modularization_id
                and m.module_id == module_id
                and m.component_type is ModuleComponentType.SPECIES
            }
        )
    )


def _boundary_species_ids(
    model: ModelSpecification, modularization_id: str, module_id: str
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                p.species_id
                for p in model.module_ports
                if p.modularization_id == modularization_id and p.module_id == module_id
            }
        )
    )


def select_functional_evaluation_targets(
    model: ModelSpecification,
    modularization_id: str,
    module_id: str,
    *,
    max_internal: int = DEFAULT_MAX_TARGETS_PER_KIND,
    max_external: int = DEFAULT_MAX_TARGETS_PER_KIND,
    fraction: Decimal = DEFAULT_PERTURBATION_FRACTION,
) -> tuple[PerturbationTargetSpec, ...]:
    """A fixed, deterministic selection: the first ``max_internal`` parameters (sorted by
    ``parameter_id``) whose own ``reaction_id`` is a member reaction of ``module_id``, and the
    first ``max_external`` parameters whose own ``reaction_id`` names a real reaction that is
    *not* a member of ``module_id`` -- never random, never tuned per run. Species-initial-
    concentration targets are deliberately out of scope for this first increment (a disclosed
    scope limit, not an oversight)."""
    member_reaction_ids = _member_reaction_ids(model, modularization_id, module_id)
    internal_candidates = sorted(
        (
            p
            for p in model.parameters
            if p.value is not None and p.reaction_id in member_reaction_ids
        ),
        key=lambda p: p.parameter_id,
    )
    external_candidates = sorted(
        (
            p
            for p in model.parameters
            if p.value is not None
            and p.reaction_id is not None
            and p.reaction_id not in member_reaction_ids
        ),
        key=lambda p: p.parameter_id,
    )
    internal_targets = tuple(
        PerturbationTargetSpec("PARAMETER", p.parameter_id, fraction, True)
        for p in internal_candidates[:max_internal]
    )
    external_targets = tuple(
        PerturbationTargetSpec("PARAMETER", p.parameter_id, fraction, False)
        for p in external_candidates[:max_external]
    )
    return internal_targets + external_targets


def unsupported_analysis_evaluation(
    *,
    parent_model_id: str,
    modularization_id: str,
    module_id: str,
    reason: str,
    request_id: str,
    correlation_id: str,
    run_id: str,
) -> ModuleFunctionalEvaluationResult:
    """The disclosed ``UNSUPPORTED_ANALYSIS`` result for a whole network with no eligible
    executable artifact -- decided entirely locally (no Harness round trip)."""
    return ModuleFunctionalEvaluationResult(
        evaluation_id=f"functional-evaluation::{modularization_id}::{module_id}::unsupported",
        request_id=request_id,
        correlation_id=correlation_id,
        run_id=run_id,
        parent_model_id=parent_model_id,
        modularization_id=modularization_id,
        module_id=module_id,
        status=FunctionalEvaluationStatus.UNSUPPORTED_ANALYSIS,
        policy_version=MODULE_FUNCTIONAL_EVALUATION_POLICY_VERSION,
        warnings=(reason,),
        provenance_refs=(f"modularization::{modularization_id}", f"module::{module_id}"),
    )


def insufficient_targets_evaluation(
    *,
    parent_model_id: str,
    modularization_id: str,
    module_id: str,
    reason: str,
    request_id: str,
    correlation_id: str,
    run_id: str,
) -> ModuleFunctionalEvaluationResult:
    """The disclosed ``INSUFFICIENT_TARGETS`` result for a module with too few internal/
    external perturbation targets -- decided entirely locally (no Harness round trip)."""
    return ModuleFunctionalEvaluationResult(
        evaluation_id=f"functional-evaluation::{modularization_id}::{module_id}::insufficient",
        request_id=request_id,
        correlation_id=correlation_id,
        run_id=run_id,
        parent_model_id=parent_model_id,
        modularization_id=modularization_id,
        module_id=module_id,
        status=FunctionalEvaluationStatus.INSUFFICIENT_TARGETS,
        policy_version=MODULE_FUNCTIONAL_EVALUATION_POLICY_VERSION,
        warnings=(reason,),
        provenance_refs=(f"modularization::{modularization_id}", f"module::{module_id}"),
    )


def build_module_functional_evaluation_request(
    model: ModelSpecification,
    modularization_id: str,
    module_id: str,
    *,
    correlation_id: str,
    run_id: str,
    max_internal_targets: int = DEFAULT_MAX_TARGETS_PER_KIND,
    max_external_targets: int = DEFAULT_MAX_TARGETS_PER_KIND,
    fraction: Decimal = DEFAULT_PERTURBATION_FRACTION,
    baseline_start_time: float = 0.0,
    baseline_end_time: float = 1000.0,
    baseline_num_points: int = 200,
    request_id: str | None = None,
    requested_at: str | None = None,
) -> ModuleFunctionalEvaluationRequest:
    """Build one ``ModuleFunctionalEvaluationRequest`` for ``module_id`` of
    ``modularization_id``, against the *whole* canonical network.

    Raises ``ModuleFunctionalEvaluationReferenceError`` when the whole network itself has no
    eligible executable artifact (readiness is not ``EXECUTABLE``) -- use
    ``unsupported_analysis_evaluation`` instead; or when fewer than ``MIN_INTERNAL_TARGETS``
    internal or ``MIN_EXTERNAL_TARGETS`` external perturbation targets exist -- use
    ``insufficient_targets_evaluation`` instead. Neither case ever reaches the Harness.
    """
    if not isinstance(model, ModelSpecification):
        raise ModuleFunctionalEvaluationReferenceError(
            f"build_module_functional_evaluation_request requires a ModelSpecification, got "
            f"{model!r}"
        )
    package = generate_antimony(model)
    if package.full_antimony.readiness is not AntimonyArtifactReadiness.EXECUTABLE:
        raise ModuleFunctionalEvaluationReferenceError(
            f"whole network has no eligible executable artifact (readiness="
            f"{package.full_antimony.readiness.value!r}) -- use unsupported_analysis_evaluation"
            " instead of building a request for it"
        )
    whole_network_handoff = build_canonical_downstream_handoff(model, package)

    targets = select_functional_evaluation_targets(
        model,
        modularization_id,
        module_id,
        max_internal=max_internal_targets,
        max_external=max_external_targets,
        fraction=fraction,
    )
    internal_count = sum(1 for t in targets if t.is_internal)
    external_count = len(targets) - internal_count
    if internal_count < MIN_INTERNAL_TARGETS or external_count < MIN_EXTERNAL_TARGETS:
        raise ModuleFunctionalEvaluationReferenceError(
            f"module_id {module_id!r} of modularization {modularization_id!r} has only "
            f"{internal_count} internal and {external_count} external perturbation targets "
            f"(need >= {MIN_INTERNAL_TARGETS} internal, >= {MIN_EXTERNAL_TARGETS} external) -- "
            "use insufficient_targets_evaluation instead of building a request for it"
        )

    return ModuleFunctionalEvaluationRequest(
        request_id=request_id or f"functional-evaluation-request::{uuid.uuid4()}",
        correlation_id=correlation_id,
        run_id=run_id,
        parent_model_id=model.model_id,
        modularization_id=modularization_id,
        module_id=module_id,
        whole_network_handoff=whole_network_handoff,
        baseline_request={
            "request_id": f"functional-evaluation-baseline::{run_id}",
            "start_time": baseline_start_time,
            "end_time": baseline_end_time,
            "num_points": baseline_num_points,
            "integrator": "cvode",
            "absolute_tolerance": 1e-10,
            "relative_tolerance": 1e-8,
        },
        perturbation_targets=targets,
        internal_species_ids=_member_species_ids(model, modularization_id, module_id),
        boundary_species_ids=_boundary_species_ids(model, modularization_id, module_id),
        requested_at=requested_at,
    )


__all__ = [
    "MIN_EXTERNAL_TARGETS",
    "MIN_INTERNAL_TARGETS",
    "build_module_functional_evaluation_request",
    "insufficient_targets_evaluation",
    "select_functional_evaluation_targets",
    "unsupported_analysis_evaluation",
]
