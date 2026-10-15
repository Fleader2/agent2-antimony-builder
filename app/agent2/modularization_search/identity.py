"""Content-addressed module/membership/port identity.

Every module id this package generates is a deterministic function of that module's own
membership *content* (its own sorted ``(component_type, component_id)`` pairs), never an
arbitrary counter -- two candidates that happen to contain an identical module always agree on
that module's own id, which is exactly what makes (a) duplicate-equivalence detection a simple
signature comparison (``candidate_signature``) and (b) calibration-evidence lookup by module
*content* (``app.agent2.module_evaluation.calibration_adapter`` is keyed by whatever module id
a caller's own evidence names) both work correctly across independently-generated candidates
without any extra bookkeeping.

``membership_id``/``port_id`` additionally fold in ``modularization_id`` (never globally
reusable across different candidates on their own) since ``ModelSpecification`` requires both
to be globally unique across every modularization it ever carries simultaneously
(``app.agent2.types.ModelSpecification.__post_init__``) -- confirmed by direct inspection.
"""

from __future__ import annotations

from app.agent2.types import ModuleComponentType, ModuleMembership, ModulePort

#: A module's own full content key: every ``(component_type, component_id)`` pair naming it,
#: regardless of the actual module_id string any particular membership row happens to use.
ModuleContentKey = frozenset[tuple[str, str]]


def module_content_key(
    memberships: tuple[ModuleMembership, ...], module_id: str
) -> ModuleContentKey:
    """This module's own content key, computed from whichever ``memberships`` actually name
    ``module_id`` -- never from the module_id string itself."""
    return frozenset(
        (m.component_type.value, m.component_id) for m in memberships if m.module_id == module_id
    )


def derive_module_id(content_key: ModuleContentKey) -> str:
    """A deterministic, human-readable, content-addressed module id -- never an opaque hash,
    consistent with every other id in this codebase. Raises ``ValueError`` for an empty content
    key (an empty module is never a valid proposal output -- every operator must guarantee
    this before calling here)."""
    if not content_key:
        raise ValueError("derive_module_id requires a non-empty content_key -- no empty modules")
    parts = "|".join(f"{t}:{c}" for t, c in sorted(content_key))
    return f"mod::{parts}"


def derive_membership_id(
    *,
    modularization_id: str,
    module_id: str,
    component_type: ModuleComponentType,
    component_id: str,
) -> str:
    return (
        f"membership::{modularization_id}::{module_id}::{component_type.value}::{component_id}"
    )


def derive_port_id(
    *, modularization_id: str, module_id: str, species_id: str, direction_value: str
) -> str:
    return f"port::{modularization_id}::{module_id}::{species_id}::{direction_value}"


def candidate_signature(
    memberships: tuple[ModuleMembership, ...], ports: tuple[ModulePort, ...]
) -> tuple[frozenset[ModuleContentKey], frozenset[tuple[str, str, str, bool]]]:
    """The full duplicate-equivalence signature for one candidate: its own membership
    partition (a module-relabeling-invariant set of content keys) plus its own declared port
    facts (module content key, species, direction, externally_controlled) -- two candidates
    with identical partitions but different declared boundaries are never treated as
    duplicates, and vice versa.
    """
    module_ids = {m.module_id for m in memberships}
    partition = frozenset(module_content_key(memberships, mid) for mid in module_ids)
    port_facts = frozenset(
        (
            "|".join(f"{t}:{c}" for t, c in sorted(module_content_key(memberships, p.module_id))),
            p.species_id,
            p.direction.value,
            p.externally_controlled,
        )
        for p in ports
    )
    return partition, port_facts


__all__ = [
    "ModuleContentKey",
    "candidate_signature",
    "derive_membership_id",
    "derive_module_id",
    "derive_port_id",
    "module_content_key",
]
