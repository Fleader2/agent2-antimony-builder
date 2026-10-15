"""Deterministic weight-grid generation (task instructions §2).

``generate_weight_vectors`` is this module's one public entry point: given a `WeightGridSpec`
(one `WeightRange` per criterion to vary, task's own "user-supplied weight grids/ranges"),
deterministically expands it into every legal `CriteriaWeights` combination. Pure: no
database, no filesystem, no network access, no random numbers anywhere in its call graph --
the identical spec always produces the identical, identically-ordered vectors.
"""

from __future__ import annotations

import itertools
from decimal import Decimal

from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
from app.agent2.weight_space_exploration.errors import WeightSpaceExplorationReferenceError
from app.agent2.weight_space_exploration.types import WeightGridSpec, WeightRange


def _evenly_spaced_indices(total: int, count: int) -> tuple[int, ...]:
    """``count`` deterministic, strictly-increasing, unique indices into ``range(total)``,
    spread as evenly as possible -- never random, never a prefix/suffix slice, so a caller
    capping a large grid still samples across its *entire* span rather than only its first
    few entries."""
    if count >= total:
        return tuple(range(total))
    if count <= 1:
        return (0,)
    chosen: list[int] = []
    seen: set[int] = set()
    for i in range(count):
        candidate = round(i * (total - 1) / (count - 1))
        while candidate in seen:
            candidate += 1
        seen.add(candidate)
        chosen.append(candidate)
    return tuple(sorted(chosen))


def generate_weight_vectors(spec: WeightGridSpec) -> tuple[CriteriaWeights, ...]:
    """Every legal `CriteriaWeights` combination `spec` implies, in deterministic order
    (the cartesian product of each `WeightRange`'s own sorted `levels`, in `spec.ranges`'
    own order -- `itertools.product` preserves input order exactly).

    The all-zero combination (every criterion at level `0`) is always excluded -- it could
    never construct a valid `CriteriaWeights` anyway (that type itself requires at least one
    positive weight), so it is skipped here rather than raising.

    When the full cartesian product exceeds `spec.max_combinations`, it is deterministically
    down-sampled to exactly that many vectors (`_evenly_spaced_indices`) -- never a random
    subset, never merely the first `N`.
    """
    level_lists = [r.levels for r in spec.ranges]
    criteria = [r.criterion for r in spec.ranges]

    combinations = [
        combo for combo in itertools.product(*level_lists) if any(level > 0 for level in combo)
    ]
    if not combinations:
        raise WeightSpaceExplorationReferenceError(
            "generate_weight_vectors: every WeightRange in spec.ranges contains only level 0 "
            "-- no non-trivial CriteriaWeights can be constructed"
        )

    if spec.max_combinations is not None and len(combinations) > spec.max_combinations:
        indices = _evenly_spaced_indices(len(combinations), spec.max_combinations)
        combinations = [combinations[i] for i in indices]

    return tuple(
        CriteriaWeights(
            weights=tuple(
                CriterionWeight(criterion, level)
                for criterion, level in zip(criteria, combo, strict=True)
            ),
            policy_version=spec.policy_version,
        )
        for combo in combinations
    )


def uniform_weight_grid(
    criteria: tuple[ModularizationCriterion, ...],
    *,
    steps: int = 3,
    max_combinations: int | None = None,
    policy_version: str,
) -> WeightGridSpec:
    """Convenience constructor for the common case: every criterion in ``criteria`` varied
    over the identical ``steps`` evenly-spaced integer levels ``0, 1, ..., steps - 1`` (task
    instructions §2's own "deterministic simplex/grid sampling"). A caller needing
    non-uniform or asymmetric ranges per criterion builds a `WeightGridSpec` directly instead.
    """
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 2:
        raise WeightSpaceExplorationReferenceError(
            f"uniform_weight_grid requires steps >= 2 (at least 'off' and 'on'), got {steps!r}"
        )
    levels = tuple(Decimal(i) for i in range(steps))
    return WeightGridSpec(
        ranges=tuple(WeightRange(criterion, levels) for criterion in criteria),
        max_combinations=max_combinations,
        policy_version=policy_version,
    )


__all__ = ["generate_weight_vectors", "uniform_weight_grid"]
