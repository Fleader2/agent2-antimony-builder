"""Reaction-adjacency topology helpers shared by ``MERGE_MODULES``/``SPLIT_MODULE`` -- reads
only ``FullNetwork.reactions``, never mutates anything, never duplicates
``app.agent2.module_evaluation.criteria``'s own private adjacency helper (a different package,
kept independent) but computes the identical, simple fact: two reactions are adjacent iff they
share at least one participant species, regardless of role.
"""

from __future__ import annotations

from app.agent2.types import FullNetwork


def reaction_species(network: FullNetwork, reaction_id: str) -> frozenset[str]:
    reaction = next(r for r in network.reactions if r.reaction_id == reaction_id)
    return frozenset(p.species_id for p in reaction.participants)


def build_reaction_adjacency(
    network: FullNetwork, reaction_ids: frozenset[str]
) -> dict[str, frozenset[str]]:
    """``{reaction_id: {adjacent reaction_id, ...}}`` restricted to ``reaction_ids`` alone."""
    species_by_reaction = {rid: reaction_species(network, rid) for rid in reaction_ids}
    adjacency: dict[str, set[str]] = {rid: set() for rid in reaction_ids}
    ordered = sorted(reaction_ids)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if species_by_reaction[a] & species_by_reaction[b]:
                adjacency[a].add(b)
                adjacency[b].add(a)
    return {k: frozenset(v) for k, v in adjacency.items()}


def connected_components(adjacency: dict[str, frozenset[str]]) -> tuple[frozenset[str], ...]:
    """Deterministic connected-component partition of ``adjacency``'s own node set -- visits
    nodes in sorted order, and components are returned sorted by their own smallest member."""
    seen: set[str] = set()
    components: list[frozenset[str]] = []
    for node in sorted(adjacency):
        if node in seen:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency.get(current, frozenset()) - component)
        seen |= component
        components.append(frozenset(component))
    return tuple(sorted(components, key=lambda c: sorted(c)))


def modules_are_adjacent(
    network: FullNetwork, reactions_a: frozenset[str], reactions_b: frozenset[str]
) -> bool:
    """True iff some reaction in ``reactions_a`` shares a species with some reaction in
    ``reactions_b`` -- the real-network-topology notion of "adjacent modules" ``MERGE_MODULES``
    restricts its own proposals to (task instructions §2: "merge adjacent modules")."""
    species_a: set[str] = set()
    for r in reactions_a:
        species_a |= reaction_species(network, r)
    species_b: set[str] = set()
    for r in reactions_b:
        species_b |= reaction_species(network, r)
    return bool(species_a & species_b)


__all__ = [
    "build_reaction_adjacency",
    "connected_components",
    "modules_are_adjacent",
    "reaction_species",
]
