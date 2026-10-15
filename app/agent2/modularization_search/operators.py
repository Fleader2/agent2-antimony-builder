"""Deterministic proposal operators (task instructions §2).

Every operator here is a pure function: ``(bundle, model, constraints) -> tuple[Proposal, ...]``
-- it never mutates ``bundle``/``model``, and returns *every* valid, constraint-respecting
proposal it can construct, in deterministic (sorted) order, never randomly. Capping the number
of proposals actually explored is ``search.py``'s own job (``SearchPolicy
.max_candidates_per_iteration``), not any operator's.

**V1 simplification, disclosed, not hidden:** ``MOVE_REACTION`` never proposes moving a
reaction that is itself a member of a ``must_stay_together`` group with more than one member
(only a whole-group move could respect cohesion, and whole-group moves are not implemented in
this increment) -- see ``constraints.is_grouped_with_others``. ``SPLIT_MODULE`` similarly
declines (produces no proposal for that one module) whenever its own natural bucketing would
separate any such group's own members across the two new modules.

Module size/count throughout this module is always measured in ``REACTION`` membership count.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.agent2.modularization_search.assembly import (
    module_group,
    rebuild_bundle,
)
from app.agent2.modularization_search.constraints import (
    can_add_boundary,
    can_remove_boundary,
    is_excluded,
    is_grouped_with_others,
    module_count_ok,
    module_size_ok,
    reaction_membership_count,
    would_violate_forbidden_together,
)
from app.agent2.modularization_search.identity import derive_port_id
from app.agent2.modularization_search.topology import (
    build_reaction_adjacency,
    connected_components,
    modules_are_adjacent,
    reaction_species,
)
from app.agent2.modularization_search.types import CandidateModularizationBundle, SearchConstraints
from app.agent2.types import (
    ModelSpecification,
    ModuleComponentType,
    ModulePort,
    ModulePortDirection,
    ParticipantRole,
)


@dataclass(frozen=True, slots=True)
class Proposal:
    """One operator's own raw output -- consumed by ``search.py`` alone (never part of the
    public result contract; ``CandidateLineage`` is built from this plus a freshly-assigned,
    deterministic final id)."""

    bundle: CandidateModularizationBundle
    affected_component_ids: tuple[str, ...]
    affected_module_ids: tuple[str, ...]


def _module_ids(bundle: CandidateModularizationBundle) -> list[str]:
    return sorted({m.module_id for m in bundle.memberships})


def _reaction_ids_of(bundle: CandidateModularizationBundle, module_id: str) -> frozenset[str]:
    return frozenset(
        c
        for t, c in module_group(bundle, module_id)
        if t == ModuleComponentType.REACTION.value
    )


def _other_groups(bundle: CandidateModularizationBundle, exclude: frozenset[str]) -> tuple:
    return tuple(
        module_group(bundle, mid) for mid in _module_ids(bundle) if mid not in exclude
    )


# --- MOVE_REACTION --------------------------------------------------------------------------


def propose_move_reaction(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    proposals: list[Proposal] = []
    reaction_module = {
        m.component_id: m.module_id
        for m in bundle.memberships
        if m.component_type is ModuleComponentType.REACTION
    }
    module_ids = _module_ids(bundle)
    for reaction_id in sorted(reaction_module):
        if is_excluded(constraints, reaction_id) or is_grouped_with_others(
            constraints, reaction_id
        ):
            continue
        source_module = reaction_module[reaction_id]
        source_count = reaction_membership_count(bundle.memberships, source_module)
        if source_count <= 1:
            continue  # never empty the source module
        if not module_size_ok(constraints, source_count - 1):
            continue
        for target_module in module_ids:
            if target_module == source_module:
                continue
            target_count = reaction_membership_count(bundle.memberships, target_module)
            if not module_size_ok(constraints, target_count + 1):
                continue
            moved_key = (ModuleComponentType.REACTION.value, reaction_id)
            new_source_group = frozenset(
                module_group(bundle, source_module) - {moved_key}
            )
            new_target_group = frozenset(module_group(bundle, target_module) | {moved_key})
            if would_violate_forbidden_together(
                constraints, frozenset(c for _, c in new_target_group)
            ):
                continue
            groups = (
                new_source_group,
                new_target_group,
                *_other_groups(bundle, frozenset({source_module, target_module})),
            )
            new_bundle = rebuild_bundle(bundle, groups)
            proposals.append(
                Proposal(new_bundle, (reaction_id,), (source_module, target_module))
            )
    return tuple(proposals)


# --- MERGE_MODULES --------------------------------------------------------------------------


def _merge_pair(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
    module_a: str,
    module_b: str,
) -> Proposal | None:
    reactions_a = _reaction_ids_of(bundle, module_a)
    reactions_b = _reaction_ids_of(bundle, module_b)
    if not modules_are_adjacent(model.full_network, reactions_a, reactions_b):
        return None
    if not module_count_ok(constraints, len(_module_ids(bundle)) - 1):
        return None
    merged_group = module_group(bundle, module_a) | module_group(bundle, module_b)
    merged_component_ids = frozenset(c for _, c in merged_group)
    if would_violate_forbidden_together(constraints, merged_component_ids):
        return None
    merged_reaction_count = len(reactions_a | reactions_b)
    if not module_size_ok(constraints, merged_reaction_count):
        return None
    groups = (merged_group, *_other_groups(bundle, frozenset({module_a, module_b})))
    new_bundle = rebuild_bundle(bundle, groups)
    return Proposal(new_bundle, (), (module_a, module_b))


def propose_merge_modules(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    module_ids = _module_ids(bundle)
    proposals: list[Proposal] = []
    for i, module_a in enumerate(module_ids):
        for module_b in module_ids[i + 1 :]:
            proposal = _merge_pair(bundle, model, constraints, module_a, module_b)
            if proposal is not None:
                proposals.append(proposal)
    return tuple(proposals)


# --- SPLIT_MODULE ---------------------------------------------------------------------------


def _assign_non_reaction_component(
    model: ModelSpecification,
    component_type: ModuleComponentType,
    component_id: str,
    module_reaction_ids: frozenset[str],
    bucket_a: frozenset[str],
    bucket_b: frozenset[str],
) -> str:
    """``"a"``/``"b"`` -- which bucket this species/parameter follows, by majority of its own
    anchor reactions (restricted to the module's own reaction set) found in each bucket. Ties
    (anchors in both, or no anchors at all) deterministically default to ``"a"`` -- never
    fabricating a preference the data does not actually show."""
    if component_type is ModuleComponentType.SPECIES:
        anchors = {
            r
            for r in module_reaction_ids
            if component_id in reaction_species(model.full_network, r)
        }
    else:  # PARAMETER
        anchors = {
            kl.reaction_id
            for kl in model.kinetic_laws
            if component_id in kl.parameter_ids and kl.reaction_id in module_reaction_ids
        }
    in_a = bool(anchors & bucket_a)
    in_b = bool(anchors & bucket_b)
    if in_b and not in_a:
        return "b"
    return "a"


def _split_module(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
    module_id: str,
) -> Proposal | None:
    group = module_group(bundle, module_id)
    reaction_ids = frozenset(c for t, c in group if t == ModuleComponentType.REACTION.value)
    if len(reaction_ids) < 2:
        return None
    if not module_count_ok(constraints, len(_module_ids(bundle)) + 1):
        return None

    adjacency = build_reaction_adjacency(model.full_network, reaction_ids)
    components = connected_components(adjacency)
    if len(components) >= 2:
        bucket_a = components[0]
        bucket_b = frozenset().union(*components[1:])
    else:
        ordered = sorted(reaction_ids)
        midpoint = len(ordered) // 2
        bucket_a = frozenset(ordered[:midpoint]) if midpoint > 0 else frozenset(ordered[:1])
        bucket_b = frozenset(ordered[midpoint:]) if midpoint > 0 else frozenset(ordered[1:])
        if not bucket_a or not bucket_b:
            return None

    # must_stay_together: reject this split outright if it would separate any group's members.
    for required_group in constraints.must_stay_together:
        touched = required_group & reaction_ids
        if len(touched) > 1 and not (touched <= bucket_a or touched <= bucket_b):
            return None

    new_group_a: set[tuple[str, str]] = {
        (ModuleComponentType.REACTION.value, r) for r in bucket_a
    }
    new_group_b: set[tuple[str, str]] = {
        (ModuleComponentType.REACTION.value, r) for r in bucket_b
    }
    for component_type_value, component_id in group:
        if component_type_value == ModuleComponentType.REACTION.value:
            continue
        if is_excluded(constraints, component_id):
            # "forbidden module membership": never carry an excluded component into either
            # new module -- its own row is dropped, never fabricated back in.
            continue
        component_type = ModuleComponentType(component_type_value)
        if component_type not in (ModuleComponentType.SPECIES, ModuleComponentType.PARAMETER):
            # RULE/EVENT/OBSERVABLE membership: not reaction-anchored in this increment's own
            # scope -- carried into bucket "a" deterministically rather than silently dropped.
            new_group_a.add((component_type_value, component_id))
            continue
        bucket = _assign_non_reaction_component(
            model, component_type, component_id, reaction_ids, bucket_a, bucket_b
        )
        (new_group_a if bucket == "a" else new_group_b).add(
            (component_type_value, component_id)
        )

    if not module_size_ok(constraints, len(bucket_a)) or not module_size_ok(
        constraints, len(bucket_b)
    ):
        return None
    a_component_ids = frozenset(c for _, c in new_group_a)
    b_component_ids = frozenset(c for _, c in new_group_b)
    if would_violate_forbidden_together(
        constraints, a_component_ids
    ) or would_violate_forbidden_together(constraints, b_component_ids):
        return None

    groups = (
        frozenset(new_group_a),
        frozenset(new_group_b),
        *_other_groups(bundle, frozenset({module_id})),
    )
    new_bundle = rebuild_bundle(bundle, groups)
    return Proposal(new_bundle, (), (module_id,))


def propose_split_module(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    proposals: list[Proposal] = []
    for module_id in _module_ids(bundle):
        proposal = _split_module(bundle, model, constraints, module_id)
        if proposal is not None:
            proposals.append(proposal)
    return tuple(proposals)


# --- ADD_BOUNDARY / REMOVE_BOUNDARY --------------------------------------------------------


def _infer_direction(
    model: ModelSpecification,
    species_id: str,
    reactions_a: frozenset[str],
    reactions_b: frozenset[str],
) -> ModulePortDirection:
    """Deterministic: if ``species_id`` is only ever a PRODUCT of a reaction in ``reactions_a``
    and only ever a REACTANT of a reaction in ``reactions_b``, A is OUTPUT / B is INPUT -- else
    (genuinely ambiguous) ``INPUT_OUTPUT`` for both, never guessed."""
    network = model.full_network

    def roles_in(reaction_ids: frozenset[str]) -> set[ParticipantRole]:
        roles: set[ParticipantRole] = set()
        for r in reaction_ids:
            reaction = next(rr for rr in network.reactions if rr.reaction_id == r)
            for p in reaction.participants:
                if p.species_id == species_id:
                    roles.add(p.role)
        return roles

    roles_a = roles_in(reactions_a)
    roles_b = roles_in(reactions_b)
    a_is_product_only = roles_a == {ParticipantRole.PRODUCT}
    b_is_reactant_only = roles_b == {ParticipantRole.REACTANT}
    if a_is_product_only and b_is_reactant_only:
        return ModulePortDirection.OUTPUT  # caller assigns OUTPUT to A, INPUT to B
    return ModulePortDirection.INPUT_OUTPUT


def _shared_species(
    model: ModelSpecification, reactions_a: frozenset[str], reactions_b: frozenset[str]
) -> tuple[str, ...]:
    species_a = {s for r in reactions_a for s in reaction_species(model.full_network, r)}
    species_b = {s for r in reactions_b for s in reaction_species(model.full_network, r)}
    return tuple(sorted(species_a & species_b))


def propose_add_boundary(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    proposals: list[Proposal] = []
    module_ids = _module_ids(bundle)
    declared = {(p.module_id, p.species_id) for p in bundle.ports}
    for i, module_a in enumerate(module_ids):
        reactions_a = _reaction_ids_of(bundle, module_a)
        for module_b in module_ids[i + 1 :]:
            reactions_b = _reaction_ids_of(bundle, module_b)
            for species_id in _shared_species(model, reactions_a, reactions_b):
                if not can_add_boundary(constraints, species_id):
                    continue
                if (module_a, species_id) in declared or (module_b, species_id) in declared:
                    continue
                direction = _infer_direction(model, species_id, reactions_a, reactions_b)
                if direction is ModulePortDirection.OUTPUT:
                    dir_a, dir_b = ModulePortDirection.OUTPUT, ModulePortDirection.INPUT
                else:
                    dir_a = dir_b = ModulePortDirection.INPUT_OUTPUT
                new_ports = (
                    *bundle.ports,
                    ModulePort(
                        port_id=derive_port_id(
                            modularization_id="pending",
                            module_id=module_a,
                            species_id=species_id,
                            direction_value=dir_a.value,
                        ),
                        modularization_id="pending",
                        module_id=module_a,
                        species_id=species_id,
                        direction=dir_a,
                    ),
                    ModulePort(
                        port_id=derive_port_id(
                            modularization_id="pending",
                            module_id=module_b,
                            species_id=species_id,
                            direction_value=dir_b.value,
                        ),
                        modularization_id="pending",
                        module_id=module_b,
                        species_id=species_id,
                        direction=dir_b,
                    ),
                )
                groups = tuple(module_group(bundle, mid) for mid in module_ids)
                new_bundle = rebuild_bundle(bundle, groups, ports=new_ports)
                proposals.append(
                    Proposal(new_bundle, (species_id,), (module_a, module_b))
                )
    return tuple(proposals)


def propose_remove_boundary(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    proposals: list[Proposal] = []
    # Group declared ports by species_id to find cross-module declared pairs.
    by_species: dict[str, list[ModulePort]] = {}
    for p in bundle.ports:
        by_species.setdefault(p.species_id, []).append(p)
    for species_id in sorted(by_species):
        ports = by_species[species_id]
        if len(ports) < 2 or not can_remove_boundary(constraints, species_id):
            continue
        module_ids_touched = tuple(sorted({p.module_id for p in ports}))
        if len(module_ids_touched) < 2:
            continue
        new_ports = tuple(p for p in bundle.ports if p.species_id != species_id)
        groups = tuple(module_group(bundle, mid) for mid in _module_ids(bundle))
        new_bundle = rebuild_bundle(bundle, groups, ports=new_ports)
        proposals.append(Proposal(new_bundle, (species_id,), module_ids_touched))
    return tuple(proposals)


# --- VARY_MODULE_COUNT ----------------------------------------------------------------------

_MAX_GREEDY_STEPS = 50


def _largest_module_split(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> CandidateModularizationBundle | None:
    by_size = sorted(
        _module_ids(bundle),
        key=lambda mid: (-reaction_membership_count(bundle.memberships, mid), mid),
    )
    for module_id in by_size:
        proposal = _split_module(bundle, model, constraints, module_id)
        if proposal is not None:
            return proposal.bundle
    return None


def _smallest_adjacent_merge(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> CandidateModularizationBundle | None:
    module_ids = _module_ids(bundle)
    pairs = [(a, b) for i, a in enumerate(module_ids) for b in module_ids[i + 1 :]]

    def combined_size(pair: tuple[str, str]) -> int:
        a, b = pair
        return reaction_membership_count(bundle.memberships, a) + reaction_membership_count(
            bundle.memberships, b
        )

    for a, b in sorted(pairs, key=lambda pair: (combined_size(pair), pair)):
        proposal = _merge_pair(bundle, model, constraints, a, b)
        if proposal is not None:
            return proposal.bundle
    return None


def _greedy_reach_count(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
    target: int,
    *,
    grow: bool,
) -> CandidateModularizationBundle | None:
    """Repeatedly split/merge toward ``target``. Intermediate steps necessarily pass through
    module counts outside ``[min_module_count, max_module_count]`` whenever the starting count
    is far from that range (e.g. 26 modules -> a target of 8 must pass through 25, 24, ...,
    9) -- the count-range constraint is a statement about the *final* candidate this operator
    produces, never about every intermediate state along the way (every *other* constraint --
    size, forbidden/must-stay-together, excluded components -- is still enforced on every
    single step, via ``_unconstrained_count``). The final bundle's own count is always checked
    against the *real* ``constraints`` before being accepted (the ``current_count == target``
    check below), so a target that itself violates some other hard constraint is still never
    reached.
    """
    unconstrained_count = replace(constraints, min_module_count=None, max_module_count=None)
    current = bundle
    for _ in range(_MAX_GREEDY_STEPS):
        current_count = len(_module_ids(current))
        if current_count == target:
            return current
        step = (
            _largest_module_split(current, model, unconstrained_count)
            if grow
            else _smallest_adjacent_merge(current, model, unconstrained_count)
        )
        if step is None:
            return None
        current = step
    return current if len(_module_ids(current)) == target else None


def propose_vary_module_count(
    bundle: CandidateModularizationBundle,
    model: ModelSpecification,
    constraints: SearchConstraints,
) -> tuple[Proposal, ...]:
    """Jump directly toward each *end* of the allowed module-count range that is not already
    the current count -- correctly in whichever direction actually reaches it: split (grow)
    when the target is above the current count, merge (shrink) when it is below, regardless of
    which bound (``min_module_count``/``max_module_count``) that target came from (e.g. a
    current count of 26 with ``max_module_count=8`` must *shrink* to reach 8, not grow)."""
    proposals: list[Proposal] = []
    current_count = len(_module_ids(bundle))
    module_ids = tuple(_module_ids(bundle))
    targets: list[int] = []
    if constraints.max_module_count is not None and constraints.max_module_count != current_count:
        targets.append(constraints.max_module_count)
    if (
        constraints.min_module_count is not None
        and constraints.min_module_count != current_count
        and constraints.min_module_count not in targets
    ):
        targets.append(constraints.min_module_count)
    for target in targets:
        result = _greedy_reach_count(
            bundle, model, constraints, target, grow=target > current_count
        )
        if result is not None:
            proposals.append(Proposal(result, (), module_ids))
    return tuple(proposals)


__all__ = [
    "Proposal",
    "propose_add_boundary",
    "propose_merge_modules",
    "propose_move_reaction",
    "propose_remove_boundary",
    "propose_split_module",
    "propose_vary_module_count",
]
