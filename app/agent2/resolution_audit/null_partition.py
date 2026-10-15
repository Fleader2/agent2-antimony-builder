"""Deterministic, structure-blind null/reference partition construction.

``build_null_partition`` chops the network's own reactions into ``module_count`` contiguous,
as-equal-as-possible groups by *sorted reaction id alone* -- never by any real topological,
compartment, or functional-annotation signal. This is the entire point: any score trend this
partition shows, under any criterion, is by construction a pure module-count/size mathematical
artifact, never genuine biological structure (there is none to detect). Fully deterministic --
no randomness anywhere (task instructions §3: "do not introduce random nondeterministic
tests").
"""

from __future__ import annotations

from app.agent2.resolution_audit.errors import ResolutionAuditReferenceError
from app.agent2.types import (
    FullNetwork,
    ModelModularization,
    ModelModule,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
)


def _chunk_evenly(ids: list[str], chunk_count: int) -> list[list[str]]:
    """``chunk_count`` contiguous slices of ``ids``, as equal in size as possible -- the first
    ``len(ids) % chunk_count`` slices get one extra element, deterministically, never randomly
    distributed."""
    base_size, remainder = divmod(len(ids), chunk_count)
    chunks: list[list[str]] = []
    index = 0
    for i in range(chunk_count):
        size = base_size + (1 if i < remainder else 0)
        chunks.append(ids[index : index + size])
        index += size
    return chunks


def build_null_partition(
    network: FullNetwork, module_count: int, *, modularization_id: str
) -> tuple[ModelModularization, tuple[ModelModule, ...], tuple[ModuleMembership, ...]]:
    """Build one deterministic, structure-blind ``NULL_REFERENCE`` partition of ``network``'s
    own reactions (plus the species each reaction touches, assigned to whichever bucket its
    own alphabetically-first reaction landed in -- the identical "no real signal, just a
    deterministic tie-break" principle) into exactly ``min(module_count, reaction_count)``
    modules.

    Raises ``ResolutionAuditReferenceError`` for ``module_count < 1`` or a network with no
    reactions at all.
    """
    if not isinstance(module_count, int) or isinstance(module_count, bool) or module_count < 1:
        raise ResolutionAuditReferenceError(
            f"build_null_partition requires module_count >= 1, got {module_count!r}"
        )
    reaction_ids = sorted(r.reaction_id for r in network.reactions)
    if not reaction_ids:
        raise ResolutionAuditReferenceError(
            "build_null_partition: network has no reactions to partition"
        )
    effective_count = min(module_count, len(reaction_ids))
    chunks = _chunk_evenly(reaction_ids, effective_count)
    module_ids = tuple(f"{modularization_id}::module::{i:03d}" for i in range(len(chunks)))

    reaction_to_module: dict[str, str] = {}
    memberships: list[ModuleMembership] = []
    for module_id, chunk in zip(module_ids, chunks, strict=True):
        for reaction_id in chunk:
            reaction_to_module[reaction_id] = module_id
            memberships.append(
                ModuleMembership(
                    membership_id=f"{modularization_id}::mem::REACTION::{reaction_id}",
                    modularization_id=modularization_id,
                    module_id=module_id,
                    component_type=ModuleComponentType.REACTION,
                    component_id=reaction_id,
                )
            )

    # Each species follows whichever bucket its own alphabetically-first participating
    # reaction landed in -- a deterministic tie-break carrying no biological meaning, exactly
    # as intended for a null baseline.
    species_first_reaction: dict[str, str] = {}
    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    for reaction_id in reaction_ids:
        reaction = reactions_by_id[reaction_id]
        for participant in reaction.participants:
            species_first_reaction.setdefault(participant.species_id, reaction_id)
    for species_id, reaction_id in sorted(species_first_reaction.items()):
        module_id = reaction_to_module[reaction_id]
        memberships.append(
            ModuleMembership(
                membership_id=f"{modularization_id}::mem::SPECIES::{species_id}",
                modularization_id=modularization_id,
                module_id=module_id,
                component_type=ModuleComponentType.SPECIES,
                component_id=species_id,
            )
        )

    modules = tuple(ModelModule(module_id=mid, name=mid) for mid in module_ids)
    modularization = ModelModularization(
        modularization_id=modularization_id,
        name=modularization_id,
        method=ModularizationMethod.NULL_REFERENCE,
        module_ids=module_ids,
    )
    return modularization, modules, tuple(memberships)


__all__ = ["build_null_partition"]
