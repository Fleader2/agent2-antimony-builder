"""Stable-boundary discovery: high-scoring-solution selection, and the boundary/co-membership/
modularization-recurrence stability measures (task instructions §4/§5).

Every function here is pure and deterministic: no database, no filesystem, no network access,
no simulation, no random numbers, no mutation of any input. Nothing here ever forces an
unstable solution into a single consensus (task instructions §4) -- every measure is reported
as a frequency in `[0, 1]`, for the caller to interpret, never collapsed into one "the"
answer.
"""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_CEILING, Decimal

from app.agent2.module_evaluation import ModularizationEvaluation
from app.agent2.types import FullNetwork, ModelSpecification, ModuleComponentType
from app.agent2.weight_space_exploration.errors import WeightSpaceExplorationReferenceError
from app.agent2.weight_space_exploration.types import (
    BoundaryStability,
    ComponentCoMembershipStability,
    HighScoringSolutionPolicy,
    HighScoringSolutionSelectionMethod,
    ModularizationRecurrence,
)


def select_high_scoring_solutions(
    evaluations: tuple[ModularizationEvaluation, ...], policy: HighScoringSolutionPolicy
) -> tuple[ModularizationEvaluation, ...]:
    """Every evaluation `policy` selects as "high-scoring" (task instructions §5), in
    best-first order (ties broken by `evaluation_id`, ascending, for full determinism).

    An evaluation with `overall_score is None` (no available evidence at all) is never
    eligible under any method -- it is excluded before ranking, never treated as the worst
    possible score. Returns `()` when no evaluation has an available score at all -- never an
    error; an empty high-scoring set is itself a disclosed, legitimate outcome.
    """
    available = [e for e in evaluations if e.overall_score is not None]
    if not available:
        return ()
    ranked = sorted(available, key=lambda e: (-e.overall_score, e.evaluation_id))

    if policy.method is HighScoringSolutionSelectionMethod.TOP_N:
        n = int(policy.value)
        return tuple(ranked[:n])

    if policy.method is HighScoringSolutionSelectionMethod.PERCENTILE:
        raw_count = (Decimal(len(ranked)) * policy.value).to_integral_value(
            rounding=ROUND_CEILING
        )
        return tuple(ranked[: max(1, int(raw_count))])

    # WITHIN_DELTA_OF_BEST
    best_score = ranked[0].overall_score
    return tuple(e for e in ranked if best_score - e.overall_score <= policy.value)


def _build_reaction_adjacency(network: FullNetwork) -> dict[frozenset[str], set[str]]:
    """``{frozenset({reaction_id_a, reaction_id_b}): {shared_species_id, ...}}`` for every
    pair of reactions sharing at least one species, over the *entire* network -- weight- and
    modularization-independent, computed once and reused across every high-scoring solution.
    Deliberately duplicated (never imported) from
    ``app.agent2.module_evaluation.criteria``'s own identical adjacency-building logic inside
    ``score_topological_separation`` -- that function's own version is scoped to one
    modularization's own member reactions, never the whole network, so reuse would require a
    new cross-package dependency for a tiny, pure, single-purpose computation; mirrors this
    project's own established convention for this exact situation (e.g.
    ``app.agent2.enzyme_concentration_species``/``app.agent2.model_specification.mapping``'s
    own duplicated ``_reaction_compartment_id``).
    """
    species_to_reactions: dict[str, set[str]] = {}
    for reaction in network.reactions:
        for participant in reaction.participants:
            species_to_reactions.setdefault(participant.species_id, set()).add(
                reaction.reaction_id
            )

    adjacency: dict[frozenset[str], set[str]] = {}
    for species_id, reaction_ids in species_to_reactions.items():
        if len(reaction_ids) < 2:
            continue
        ordered = sorted(reaction_ids)
        for i, r1 in enumerate(ordered):
            for r2 in ordered[i + 1 :]:
                adjacency.setdefault(frozenset({r1, r2}), set()).add(species_id)
    return adjacency


def _module_ids_by_component(
    model: ModelSpecification, modularization_id: str, component_type: ModuleComponentType
) -> dict[str, frozenset[str]]:
    """``{component_id: frozenset(module_id, ...)}`` for this one modularization's own
    membership rows of ``component_type`` -- weight-independent (a modularization's own
    structure never changes across weight vectors), so this is computed at most once per
    distinct ``modularization_id`` actually encountered, never once per evaluation."""
    result: dict[str, set[str]] = {}
    for m in model.module_memberships:
        if m.modularization_id == modularization_id and m.component_type is component_type:
            result.setdefault(m.component_id, set()).add(m.module_id)
    return {component_id: frozenset(module_ids) for component_id, module_ids in result.items()}


def compute_boundary_stability(
    model: ModelSpecification, high_scoring_evaluations: tuple[ModularizationEvaluation, ...]
) -> tuple[BoundaryStability, ...]:
    """One `BoundaryStability` per network-adjacency edge that was applicable (both of its
    own reactions covered by some module) in at least one high-scoring evaluation's own
    modularization -- task instructions §4's "boundary recurrence frequency."

    An edge whose two reactions are covered by every high-scoring solution's own
    modularization, and always end up in the same module, recurs with `cut_frequency == 0`
    (a stably *internal* connection -- never reported as "unstable" merely because it is
    stably *not* a boundary). An edge cut in some solutions and not others has a
    `cut_frequency` strictly between `0` and `1` -- genuinely ambiguous, never forced to a
    single answer (see `app.agent2.weight_space_exploration.exploration`'s own
    ambiguous-band disclosure).
    """
    if not high_scoring_evaluations:
        return ()
    adjacency = _build_reaction_adjacency(model.full_network)
    module_ids_cache: dict[str, dict[str, frozenset[str]]] = {}
    cut_counts: Counter[frozenset[str]] = Counter()
    applicable_counts: Counter[frozenset[str]] = Counter()

    for evaluation in high_scoring_evaluations:
        mz_id = evaluation.modularization_id
        if mz_id not in module_ids_cache:
            module_ids_cache[mz_id] = _module_ids_by_component(
                model, mz_id, ModuleComponentType.REACTION
            )
        module_ids_by_reaction = module_ids_cache[mz_id]
        for edge in adjacency:
            r1, r2 = tuple(edge)
            modules_1 = module_ids_by_reaction.get(r1)
            modules_2 = module_ids_by_reaction.get(r2)
            if modules_1 is None or modules_2 is None:
                continue
            applicable_counts[edge] += 1
            if not (modules_1 & modules_2):
                cut_counts[edge] += 1

    results = []
    for edge, applicable in applicable_counts.items():
        reaction_id_a, reaction_id_b = sorted(edge)
        results.append(
            BoundaryStability(
                reaction_id_a=reaction_id_a,
                reaction_id_b=reaction_id_b,
                shared_species_ids=tuple(sorted(adjacency[edge])),
                cut_frequency=Decimal(cut_counts.get(edge, 0)) / Decimal(applicable),
                high_scoring_solution_count=applicable,
            )
        )
    return tuple(sorted(results, key=lambda b: (b.reaction_id_a, b.reaction_id_b)))


def compute_co_membership_stability(
    model: ModelSpecification,
    high_scoring_evaluations: tuple[ModularizationEvaluation, ...],
    component_type: ModuleComponentType,
) -> tuple[ComponentCoMembershipStability, ...]:
    """One `ComponentCoMembershipStability` per pair of components (of ``component_type``)
    that co-occurred in some module of some high-scoring evaluation's own modularization at
    least once -- task instructions §4's "module co-membership frequency," the more general
    counterpart to `compute_boundary_stability` (meaningful for species, and directly
    comparable *across different module counts*, since a component's own canonical id is
    identical regardless of which, or how many, modules its own modularization happens to
    define).

    Candidate pairs are restricted to those that co-occur within some one module of some one
    high-scoring modularization at least once -- never every possible pair in the network, so
    computation stays proportional to what was actually explored, not the full component
    count squared.
    """
    if not high_scoring_evaluations:
        return ()
    module_ids_cache: dict[str, dict[str, frozenset[str]]] = {}
    candidate_pairs: set[frozenset[str]] = set()
    seen_modularization_ids: set[str] = set()

    for evaluation in high_scoring_evaluations:
        mz_id = evaluation.modularization_id
        if mz_id in seen_modularization_ids:
            continue
        seen_modularization_ids.add(mz_id)
        module_ids_by_component = _module_ids_by_component(model, mz_id, component_type)
        module_ids_cache[mz_id] = module_ids_by_component

        members_by_module: dict[str, set[str]] = {}
        for component_id, module_ids in module_ids_by_component.items():
            for module_id in module_ids:
                members_by_module.setdefault(module_id, set()).add(component_id)
        for members in members_by_module.values():
            ordered = sorted(members)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    candidate_pairs.add(frozenset({a, b}))

    co_counts: Counter[frozenset[str]] = Counter()
    applicable_counts: Counter[frozenset[str]] = Counter()
    for evaluation in high_scoring_evaluations:
        module_ids_by_component = module_ids_cache[evaluation.modularization_id]
        for pair in candidate_pairs:
            a, b = tuple(pair)
            modules_a = module_ids_by_component.get(a)
            modules_b = module_ids_by_component.get(b)
            if modules_a is None or modules_b is None:
                continue
            applicable_counts[pair] += 1
            if modules_a & modules_b:
                co_counts[pair] += 1

    results = []
    for pair, applicable in applicable_counts.items():
        component_id_a, component_id_b = sorted(pair)
        results.append(
            ComponentCoMembershipStability(
                component_type=component_type,
                component_id_a=component_id_a,
                component_id_b=component_id_b,
                co_membership_frequency=Decimal(co_counts.get(pair, 0)) / Decimal(applicable),
                high_scoring_solution_count=applicable,
            )
        )
    return tuple(sorted(results, key=lambda c: (c.component_id_a, c.component_id_b)))


def compute_modularization_recurrence(
    evaluations: tuple[ModularizationEvaluation, ...],
    high_scoring_evaluation_ids: frozenset[str],
) -> tuple[ModularizationRecurrence, ...]:
    """One `ModularizationRecurrence` per distinct `modularization_id` actually evaluated --
    task instructions §4's "modularization recurrence/similarity": what fraction of the
    weight vectors this modularization was evaluated under actually placed it among the
    high-scoring solutions.
    """
    if not evaluations:
        raise WeightSpaceExplorationReferenceError(
            "compute_modularization_recurrence requires at least one evaluation"
        )
    by_modularization: dict[str, list[ModularizationEvaluation]] = {}
    for e in evaluations:
        by_modularization.setdefault(e.modularization_id, []).append(e)

    results = []
    for mz_id, evals in sorted(by_modularization.items()):
        evaluated_count = len(evals)
        high_scoring_count = sum(
            1 for e in evals if e.evaluation_id in high_scoring_evaluation_ids
        )
        results.append(
            ModularizationRecurrence(
                modularization_id=mz_id,
                module_count=evals[0].module_count,
                evaluated_count=evaluated_count,
                high_scoring_count=high_scoring_count,
                recurrence_frequency=Decimal(high_scoring_count) / Decimal(evaluated_count),
            )
        )
    return tuple(results)


__all__ = [
    "compute_boundary_stability",
    "compute_co_membership_stability",
    "compute_modularization_recurrence",
    "select_high_scoring_solutions",
]
