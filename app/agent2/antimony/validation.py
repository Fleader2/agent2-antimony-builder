"""Minimal serializer-integrity checks (Increment 9, Step 36) -- never scientific validation.

Confirms only what a *serializer* must guarantee before it can safely
render text: every reference the generator is about to use actually
resolves, and no two entities in the same Antimony symbol-table category
were assigned the same identifier. Never mass-balance, connectivity,
duplicate-reaction-biology, disconnected-subnetwork, or unit-consistency
analysis -- that remains Agent 3's job (``docs/12_antimony_generation.md``
§28-29).

Every check here should be unreachable given a valid ``ModelSpecification``
and a correctly-built ``IdentifierMap`` -- they exist as a defensive
backstop, mirroring the identical "should never trigger" backstop pattern
already established in
``app.agent2.model_specification.assembler._validate_cross_artifact_references``.
"""

from __future__ import annotations

from app.agent2.antimony.errors import AntimonyIdentifierCollisionError, AntimonyReferenceError
from app.agent2.antimony.naming import IdentifierMap, all_identifiers
from app.agent2.types import ModelSpecification


def validate_serializer_integrity(model: ModelSpecification, id_map: IdentifierMap) -> None:
    """Raise a focused, typed error if the serializer's own preconditions do not hold.

    Never raised for a normal unresolved-kinetics state (that is
    ``AntimonyArtifactReadiness``, not an error) -- only for a genuine
    reference/collision inconsistency.
    """
    _require_no_duplicate_identifiers(id_map)
    _require_kinetic_law_references_resolve(model, id_map)
    _require_module_references_resolve(model, id_map)


def _require_no_duplicate_identifiers(id_map: IdentifierMap) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for identifier in all_identifiers(id_map):
        if identifier in seen:
            duplicates.add(identifier)
        seen.add(identifier)
    if duplicates:
        raise AntimonyIdentifierCollisionError(
            f"identifier map produced duplicate Antimony identifier(s): {sorted(duplicates)}"
        )


def _require_kinetic_law_references_resolve(
    model: ModelSpecification, id_map: IdentifierMap
) -> None:
    for law in model.kinetic_laws:
        if law.reaction_id not in id_map.reactions:
            raise AntimonyReferenceError(
                f"kinetic law {law.kinetic_law_id!r} references reaction {law.reaction_id!r}, "
                "which has no assigned Antimony reaction identifier"
            )
        for species_id in law.species_ids:
            if species_id not in id_map.species:
                raise AntimonyReferenceError(
                    f"kinetic law {law.kinetic_law_id!r} references species {species_id!r}, "
                    "which has no assigned Antimony identifier"
                )
        for parameter_id in law.parameter_ids:
            if parameter_id not in id_map.parameters:
                raise AntimonyReferenceError(
                    f"kinetic law {law.kinetic_law_id!r} references parameter {parameter_id!r}, "
                    "which has no assigned Antimony identifier"
                )


def _require_module_references_resolve(model: ModelSpecification, id_map: IdentifierMap) -> None:
    for module in model.module_specifications:
        for species_id in module.species_ids:
            if species_id not in id_map.species:
                raise AntimonyReferenceError(
                    f"module {module.module_id!r} references species {species_id!r}, which has "
                    "no assigned Antimony identifier"
                )
        for reaction_id in module.reaction_ids:
            if reaction_id not in {r.reaction_id for r in model.full_network.reactions}:
                raise AntimonyReferenceError(
                    f"module {module.module_id!r} references reaction {reaction_id!r}, which "
                    "does not exist in the full network"
                )


__all__ = ["validate_serializer_integrity"]
