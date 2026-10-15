"""Candidate Modularization Search: the public, read-only search API.

``search_candidate_modularizations`` is this package's one core entry point -- a bounded,
deterministic beam/best-first search (task instructions §4) over proposal operators
(``operators.py``), reusing the existing Module Boundary Evaluation Framework/Weight-Space
Exploration framework completely unchanged (task instructions §5) for every evaluation.

Never mutates ``model``: every candidate is an ephemeral ``CandidateModularizationBundle``,
attached to a fresh, disposable copy of ``model`` (``dataclasses.replace``, via
``assembly.attach_bundle``/``attach_many``) only for the duration of one evaluation call.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal

from app.agent2.modularization_search.assembly import (
    attach_bundle,
    attach_many,
    canonicalize_bundle,
    extract_bundle,
    restamp_modularization_id,
)
from app.agent2.modularization_search.errors import ModularizationSearchReferenceError
from app.agent2.modularization_search.identity import (
    ModuleContentKey,
    candidate_signature,
    module_content_key,
)
from app.agent2.modularization_search.operators import (
    propose_add_boundary,
    propose_merge_modules,
    propose_move_reaction,
    propose_remove_boundary,
    propose_split_module,
    propose_vary_module_count,
)
from app.agent2.modularization_search.types import (
    CandidateLineage,
    CandidateModularizationBundle,
    CandidateModularizationSearchResult,
    ProposalOperation,
    RejectedCandidate,
    SearchConstraints,
    SearchPolicy,
)
from app.agent2.module_calibration.types import ModuleCalibrationEvaluation
from app.agent2.module_evaluation import CriteriaWeights, evaluate_modularization
from app.agent2.module_evaluation.types import (
    ModularizationCriterion,
    ModularizationEvaluation,
    TopologyFilteringPolicy,
)
from app.agent2.resolution_audit import build_null_partition
from app.agent2.types import ModelSpecification
from app.agent2.version import (
    MODULARIZATION_SEARCH_POLICY_VERSION,
    WEIGHT_SPACE_EXPLORATION_POLICY_VERSION,
)
from app.agent2.weight_space_exploration import (
    HighScoringSolutionPolicy,
    HighScoringSolutionSelectionMethod,
    explore_weight_space,
)

_OPERATOR_FUNCS = {
    ProposalOperation.MOVE_REACTION: propose_move_reaction,
    ProposalOperation.MERGE_MODULES: propose_merge_modules,
    ProposalOperation.SPLIT_MODULE: propose_split_module,
    ProposalOperation.ADD_BOUNDARY: propose_add_boundary,
    ProposalOperation.REMOVE_BOUNDARY: propose_remove_boundary,
    ProposalOperation.VARY_MODULE_COUNT: propose_vary_module_count,
}

#: The unconstrained default -- a frozen, immutable singleton, never mutated by anything in
#: this module, so sharing it across every call that omits ``constraints`` is safe.
_UNCONSTRAINED = SearchConstraints()


def _cap_fairly_across_operations(
    raw_proposals: list[tuple[str, ProposalOperation, object]], max_candidates: int
) -> list[tuple[str, ProposalOperation, object]]:
    """Split ``max_candidates`` evenly across every operation that actually produced at least
    one raw proposal this generation (deterministic remainder distribution to the
    alphabetically-first operations), rather than one global, lexicographically-ordered
    truncation -- a single global cut would let whichever operation happens to produce the
    most raw proposals (observed, on a real model: ``ADD_BOUNDARY``) silently starve every
    other operation (e.g. ``VARY_MODULE_COUNT``) out of ever being considered at all, even
    though the caller explicitly allowed it. Each operation's own share is itself taken in a
    fixed, deterministic order (sorted by parent id, then affected ids) -- never randomly.
    """
    by_operation: dict[ProposalOperation, list] = {}
    for item in raw_proposals:
        by_operation.setdefault(item[1], []).append(item)
    active_operations = sorted(by_operation, key=lambda op: op.value)
    if not active_operations:
        return []
    share_count = len(active_operations)
    base_share, remainder = divmod(max_candidates, share_count)
    capped: list[tuple[str, ProposalOperation, object]] = []
    for index, operation in enumerate(active_operations):
        share = base_share + (1 if index < remainder else 0)
        items = sorted(
            by_operation[operation],
            key=lambda item: (item[0], item[2].affected_module_ids, item[2].affected_component_ids),
        )
        capped.extend(items[:share])
    return capped


def _calibration_evidence_for_bundle(
    bundle: CandidateModularizationBundle,
    calibration_evidence: Mapping[ModuleContentKey, ModuleCalibrationEvaluation] | None,
) -> dict[str, ModuleCalibrationEvaluation] | None:
    """Content-addressed lookup (task instructions §2/§5): a module in ``bundle`` whose own
    content key matches one the caller already has evidence for picks it up automatically,
    regardless of which generation/operation produced that exact module -- never recomputed,
    never requested here (``calibration_evidence`` must already have been obtained by routing
    a ``ModuleCalibrationRequest`` through the Harness/Agent 3/Agent 4 before this search ever
    ran)."""
    if calibration_evidence is None:
        return None
    module_ids = {m.module_id for m in bundle.memberships}
    return {
        module_id: calibration_evidence[module_content_key(bundle.memberships, module_id)]
        for module_id in module_ids
        if module_content_key(bundle.memberships, module_id) in calibration_evidence
    }


def _null_reference_scores_for_module_count(
    model: ModelSpecification,
    module_count: int,
    criteria_weights: CriteriaWeights,
    topology_filtering: TopologyFilteringPolicy | None,
    cache: dict[int, dict[ModularizationCriterion, Decimal]],
) -> dict[ModularizationCriterion, Decimal]:
    """Module-Count / Resolution Bias Audit increment: the matching, deterministic,
    structure-blind null partition's own per-criterion score at ``module_count`` -- computed
    once per distinct module count actually encountered this search (``cache``), reusing
    ``app.agent2.resolution_audit.build_null_partition`` unchanged, never a new scoring
    algorithm. Only criteria with *available* evidence on the null partition contribute an
    entry -- an unavailable one is simply absent, never fabricated."""
    if module_count in cache:
        return cache[module_count]
    null_modularization, null_modules, null_memberships = build_null_partition(
        model.full_network, module_count, modularization_id=f"null::search::{module_count}"
    )
    null_model = replace(
        model,
        modularizations=(null_modularization,),
        model_modules=null_modules,
        module_memberships=null_memberships,
        module_ports=(),
    )
    null_evaluation = evaluate_modularization(
        null_model,
        null_modularization.modularization_id,
        criteria_weights,
        topology_filtering=topology_filtering,
    )
    result = {
        cs.criterion: cs.raw_score for cs in null_evaluation.criterion_scores if cs.available
    }
    cache[module_count] = result
    return result


def search_candidate_modularizations(
    model: ModelSpecification,
    seed_modularization_id: str,
    criteria_weights: CriteriaWeights,
    search_policy: SearchPolicy,
    *,
    constraints: SearchConstraints | None = None,
    topology_filtering: TopologyFilteringPolicy | None = None,
    calibration_evidence: Mapping[ModuleContentKey, ModuleCalibrationEvaluation] | None = None,
    apply_resolution_correction: bool = False,
    stability_weight_vectors: tuple[CriteriaWeights, ...] | None = None,
    high_scoring_policy: HighScoringSolutionPolicy | None = None,
    policy_version: str = MODULARIZATION_SEARCH_POLICY_VERSION,
) -> CandidateModularizationSearchResult:
    """Run one bounded, deterministic beam search starting from ``seed_modularization_id``.

    Works identically for a ``GENERATED`` or ``IMPORTED`` ``model`` -- every value read here
    comes from ``model.full_network``/``.kinetic_laws``/``.module_memberships``/``.module_ports``
    alone, never from anything origin-specific. Works identically when ``model`` is itself a
    previously-derived module/submodel re-assembled as its own ``ModelSpecification``
    (recursive readiness, task instructions §8) -- nothing here assumes "the whole canonical
    model."

    ``calibration_evidence`` (optional), when given, is a flat mapping from a module's own
    content key (``app.agent2.modularization_search.identity.module_content_key`` -- the
    frozenset of ``(component_type, component_id)`` pairs naming it) to its already-obtained
    ``ModuleCalibrationEvaluation``. Agent 4 is never called automatically inside this search
    (task instructions §5) -- only evidence the caller already has, obtained through the
    existing Recursive Module Evaluation Orchestration layer, is ever consulted.

    ``apply_resolution_correction`` (Module-Count / Resolution Bias Audit increment, optional,
    defaults to ``False``) -- when set, every candidate's own evaluation additionally scores a
    matching, deterministic, structure-blind null partition at that candidate's own module
    count (computed on the fly, cached per distinct count actually encountered --
    ``app.agent2.resolution_audit.build_null_partition``, never a new scoring algorithm) and
    uses the *corrected* score (never clamped below the raw one on the record, only when
    driving ranking) in place of raw for ranking/retention -- while every candidate's own raw
    score, null baseline, and module count remain fully inspectable on its own
    ``ModularizationEvaluation.criterion_scores``. Omitting it (the default) reproduces this
    function's exact pre-existing behavior with no change whatsoever.

    ``stability_weight_vectors``/``high_scoring_policy`` (optional) configure the final
    weight-space/stable-boundary analysis run over every retained candidate together
    (``explore_weight_space``, unchanged); omitting either defaults to the single
    ``criteria_weights`` vector and a "retain every candidate found" ``TOP_N`` policy,
    respectively -- the search's own beam/retention policy already did the hard work of
    keeping only promising candidates, so the default stability pass does not re-filter them.

    Raises ``ModularizationSearchReferenceError`` for a malformed ``model`` or an unknown
    ``seed_modularization_id``. Never raises for a proposal operator finding nothing valid to
    propose, a candidate violating a hard constraint, or a duplicate candidate -- all three are
    normal, disclosed outcomes (an empty proposal list, a ``RejectedCandidate`` entry), never
    exceptions.
    """
    if not isinstance(model, ModelSpecification):
        raise ModularizationSearchReferenceError(
            f"search_candidate_modularizations requires a ModelSpecification, got {model!r}"
        )
    constraints = constraints if constraints is not None else _UNCONSTRAINED
    seed_raw = extract_bundle(model, seed_modularization_id)

    counter = 0
    null_reference_cache: dict[int, dict[ModularizationCriterion, Decimal]] = {}

    def _next_id(generation: int) -> str:
        nonlocal counter
        counter += 1
        return f"candidate::gen{generation}::{counter:04d}"

    def _evaluate(bundle: CandidateModularizationBundle) -> ModularizationEvaluation:
        evidence = _calibration_evidence_for_bundle(bundle, calibration_evidence)
        eval_model = attach_bundle(model, bundle)
        null_reference_scores = None
        if apply_resolution_correction:
            module_count = len({m.module_id for m in bundle.memberships})
            null_reference_scores = _null_reference_scores_for_module_count(
                model, module_count, criteria_weights, topology_filtering, null_reference_cache
            )
        return evaluate_modularization(
            eval_model,
            bundle.modularization.modularization_id,
            criteria_weights,
            topology_filtering=topology_filtering,
            calibration_evidence=evidence,
            null_reference_scores=null_reference_scores,
        )

    seed_id = _next_id(0)
    seed_bundle = restamp_modularization_id(canonicalize_bundle(seed_raw), seed_id)
    seed_evaluation = _evaluate(seed_bundle)

    seed_signature = candidate_signature(seed_bundle.memberships, seed_bundle.ports)
    seen_signatures: set = {seed_signature}
    retained_by_signature: dict = {seed_signature: seed_bundle}
    evaluations_by_id: dict[str, ModularizationEvaluation] = {seed_id: seed_evaluation}
    lineage: list[CandidateLineage] = [
        CandidateLineage(
            candidate_id=seed_id,
            parent_candidate_id=None,
            operation=ProposalOperation.SEED,
            affected_component_ids=(),
            affected_module_ids=(),
            generation=0,
            policy_version=policy_version,
        )
    ]
    rejected: list[RejectedCandidate] = []

    frontier: list[tuple[str, CandidateModularizationBundle]] = [(seed_id, seed_bundle)]
    iterations_run = 0

    for generation in range(1, search_policy.max_iterations + 1):
        iterations_run = generation
        raw_proposals = []
        for parent_id, parent_bundle in frontier:
            for operation in search_policy.allowed_operations:
                func = _OPERATOR_FUNCS.get(operation)
                if func is None:
                    continue
                for proposal in func(parent_bundle, model, constraints):
                    raw_proposals.append((parent_id, operation, proposal))

        capped = _cap_fairly_across_operations(
            raw_proposals, search_policy.max_candidates_per_iteration
        )

        new_this_generation: list[tuple[str, CandidateModularizationBundle, tuple]] = []
        for parent_id, operation, proposal in capped:
            signature = candidate_signature(proposal.bundle.memberships, proposal.bundle.ports)
            candidate_id = _next_id(generation)
            if signature in seen_signatures:
                rejected.append(
                    RejectedCandidate(
                        candidate_id=candidate_id,
                        parent_candidate_id=parent_id,
                        operation=operation,
                        reason=(
                            "duplicate of an already-seen candidate (identical membership "
                            "partition and port declarations)"
                        ),
                    )
                )
                continue
            seen_signatures.add(signature)
            final_bundle = restamp_modularization_id(proposal.bundle, candidate_id)
            lineage.append(
                CandidateLineage(
                    candidate_id=candidate_id,
                    parent_candidate_id=parent_id,
                    operation=operation,
                    affected_component_ids=proposal.affected_component_ids,
                    affected_module_ids=proposal.affected_module_ids,
                    generation=generation,
                    policy_version=policy_version,
                )
            )
            new_this_generation.append((candidate_id, final_bundle, signature))

        if not new_this_generation:
            break  # bounded termination: no new, non-duplicate candidate this generation

        scored = []
        for candidate_id, cbundle, signature in new_this_generation:
            evaluation = _evaluate(cbundle)
            evaluations_by_id[candidate_id] = evaluation
            scored.append((candidate_id, cbundle, signature, evaluation))

        scored.sort(
            key=lambda item: (
                item[3].overall_score is None,
                -(item[3].overall_score) if item[3].overall_score is not None else Decimal(0),
                item[0],
            )
        )
        beam = scored[: search_policy.beam_width]
        overflow = scored[search_policy.beam_width :]
        lineage_by_id = {entry.candidate_id: entry for entry in lineage}
        for candidate_id, _cbundle, _signature, evaluation in overflow:
            entry = lineage_by_id[candidate_id]
            rejected.append(
                RejectedCandidate(
                    candidate_id=candidate_id,
                    parent_candidate_id=entry.parent_candidate_id,
                    operation=entry.operation,
                    reason=(
                        f"did not make the beam cutoff this generation "
                        f"(overall_score={evaluation.overall_score})"
                    ),
                )
            )
        for _candidate_id, cbundle, signature, _evaluation in beam:
            retained_by_signature[signature] = cbundle

        frontier = [(candidate_id, cbundle) for candidate_id, cbundle, _sig, _ev in beam]

    retained_bundles = tuple(retained_by_signature.values())
    retained_ids = tuple(b.modularization.modularization_id for b in retained_bundles)
    retained_evaluations = tuple(evaluations_by_id[cid] for cid in retained_ids)

    weight_vectors = (
        stability_weight_vectors if stability_weight_vectors is not None else (criteria_weights,)
    )
    policy = (
        high_scoring_policy
        if high_scoring_policy is not None
        else HighScoringSolutionPolicy(
            HighScoringSolutionSelectionMethod.TOP_N,
            Decimal(len(retained_bundles)),
            policy_version=policy_version,
        )
    )
    combined_model = attach_many(model, retained_bundles)
    combined_calibration_evidence = (
        {
            b.modularization.modularization_id: _calibration_evidence_for_bundle(
                b, calibration_evidence
            )
            for b in retained_bundles
        }
        if calibration_evidence is not None
        else None
    )
    weight_space_result = explore_weight_space(
        combined_model,
        retained_ids,
        weight_vectors,
        policy,
        topology_filtering=topology_filtering,
        calibration_evidence=combined_calibration_evidence,
        policy_version=WEIGHT_SPACE_EXPLORATION_POLICY_VERSION,
    )

    return CandidateModularizationSearchResult(
        search_id=f"search::{model.model_id}::{seed_modularization_id}",
        model_id=model.model_id,
        seed_candidate_id=seed_id,
        retained=retained_bundles,
        evaluations=retained_evaluations,
        weight_space_result=weight_space_result,
        lineage=tuple(lineage),
        rejected=tuple(rejected),
        search_policy=search_policy,
        iterations_run=iterations_run,
        policy_version=policy_version,
        provenance_refs=(f"seed-modularization::{seed_modularization_id}",),
    )


__all__ = ["search_candidate_modularizations"]
