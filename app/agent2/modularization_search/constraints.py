"""Hard-constraint checks (task instructions §3) -- every proposal operator in ``operators.py``
calls these *before* constructing any new ``ModuleMembership``/``ModulePort`` row, never after
(a violating candidate is never generated and then discarded).

Module size is measured in ``REACTION`` membership count -- a module's own primary unit of
content, consistent with ``operators.py``'s own reaction-centric move/merge/split operators.
"""

from __future__ import annotations

from app.agent2.modularization_search.types import BoundaryFixedState, SearchConstraints
from app.agent2.types import ModuleComponentType, ModuleMembership


def is_excluded(constraints: SearchConstraints, component_id: str) -> bool:
    """True iff ``component_id`` must never become a member of any module ("forbidden module
    membership") -- every operator must skip it entirely, never even consider it."""
    return component_id in constraints.excluded_component_ids


def is_grouped_with_others(constraints: SearchConstraints, component_id: str) -> bool:
    """True iff ``component_id`` belongs to a ``must_stay_together`` group with more than one
    member -- V1's own move-eligibility simplification (task instructions §3: "candidate
    generation must never violate hard user constraints") never proposes moving a single
    member of such a group alone; only a whole-group move could respect cohesion, and that is
    not implemented in this increment (disclosed in the module docstring of ``operators.py``).
    """
    return any(
        component_id in group and len(group) > 1 for group in constraints.must_stay_together
    )


def would_violate_forbidden_together(
    constraints: SearchConstraints, module_component_ids: frozenset[str]
) -> bool:
    """True iff placing exactly ``module_component_ids`` together in one module would fully
    co-locate two or more members of any one ``forbidden_together`` group."""
    return any(
        len(group & module_component_ids) >= 2 for group in constraints.forbidden_together
    )


def reaction_membership_count(memberships: tuple[ModuleMembership, ...], module_id: str) -> int:
    return sum(
        1
        for m in memberships
        if m.module_id == module_id and m.component_type is ModuleComponentType.REACTION
    )


def module_size_ok(constraints: SearchConstraints, reaction_count: int) -> bool:
    if constraints.min_module_size is not None and reaction_count < constraints.min_module_size:
        return False
    return not (
        constraints.max_module_size is not None and reaction_count > constraints.max_module_size
    )


def module_count_ok(constraints: SearchConstraints, module_count: int) -> bool:
    if constraints.min_module_count is not None and module_count < constraints.min_module_count:
        return False
    return not (
        constraints.max_module_count is not None and module_count > constraints.max_module_count
    )


def boundary_fixed_state_for(
    constraints: SearchConstraints, species_id: str
) -> BoundaryFixedState | None:
    for fb in constraints.fixed_boundaries:
        if fb.species_id == species_id:
            return fb.state
    return None


def can_add_boundary(constraints: SearchConstraints, species_id: str) -> bool:
    state = boundary_fixed_state_for(constraints, species_id)
    return state is not BoundaryFixedState.MUST_NOT_BE_DECLARED


def can_remove_boundary(constraints: SearchConstraints, species_id: str) -> bool:
    state = boundary_fixed_state_for(constraints, species_id)
    return state is not BoundaryFixedState.MUST_BE_DECLARED


__all__ = [
    "boundary_fixed_state_for",
    "can_add_boundary",
    "can_remove_boundary",
    "is_excluded",
    "is_grouped_with_others",
    "module_count_ok",
    "module_size_ok",
    "reaction_membership_count",
    "would_violate_forbidden_together",
]
