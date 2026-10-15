"""Turning a proposed component partition into a validated ``CandidateModularizationBundle``,
and attaching/extracting bundles to/from a ``ModelSpecification`` for evaluation -- never
mutating ``model`` anywhere in this module (``dataclasses.replace`` always returns a new
object).
"""

from __future__ import annotations

from dataclasses import replace

from app.agent2.modularization_search.errors import ModularizationSearchReferenceError
from app.agent2.modularization_search.identity import (
    ModuleContentKey,
    derive_membership_id,
    derive_module_id,
    derive_port_id,
    module_content_key,
)
from app.agent2.modularization_search.types import CandidateModularizationBundle
from app.agent2.types import (
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleMembership,
    ModulePort,
)

#: Every bundle this package builds (before final id-stamping by ``search.py``) uses this one
#: placeholder modularization_id -- never persisted in any returned result; always replaced by
#: ``restamp_modularization_id`` before a candidate is ever retained, rejected, or evaluated.
PENDING_MODULARIZATION_ID = "pending"


def extract_bundle(
    model: ModelSpecification, modularization_id: str
) -> CandidateModularizationBundle:
    """Pull one existing modularization's own modules/memberships/ports out of ``model`` as a
    self-contained bundle -- raises ``ModularizationSearchReferenceError`` if it does not
    exist."""
    modularization = next(
        (m for m in model.modularizations if m.modularization_id == modularization_id), None
    )
    if modularization is None:
        known = sorted(m.modularization_id for m in model.modularizations)
        raise ModularizationSearchReferenceError(
            f"extract_bundle: modularization_id {modularization_id!r} does not exist in "
            f"model.modularizations (known: {known})"
        )
    modules = tuple(m for m in model.model_modules if m.module_id in modularization.module_ids)
    memberships = tuple(
        m for m in model.module_memberships if m.modularization_id == modularization_id
    )
    ports = tuple(p for p in model.module_ports if p.modularization_id == modularization_id)
    return CandidateModularizationBundle(
        modularization=modularization, modules=modules, memberships=memberships, ports=ports
    )


def attach_bundle(
    model: ModelSpecification, bundle: CandidateModularizationBundle
) -> ModelSpecification:
    """An ephemeral evaluation view of ``model`` carrying *only* ``bundle``'s own modularization
    data -- mirrors ``app.agent2.module_evaluation``'s own established convention of never
    permanently attaching a candidate. ``model`` itself is never mutated."""
    return replace(
        model,
        modularizations=(bundle.modularization,),
        model_modules=bundle.modules,
        module_memberships=bundle.memberships,
        module_ports=bundle.ports,
    )


def attach_many(
    model: ModelSpecification, bundles: tuple[CandidateModularizationBundle, ...]
) -> ModelSpecification:
    """An ephemeral evaluation view carrying every one of ``bundles`` simultaneously (for
    multi-candidate weight-space/stability analysis) -- a ``ModelModule`` shared, byte-
    identical, by more than one bundle (content-addressed, so this only ever happens for a
    genuinely unchanged module) is included exactly once, never duplicated (``ModelSpecification``
    requires every ``module_id`` to be globally unique)."""
    modules_by_id: dict[str, ModelModule] = {}
    for bundle in bundles:
        for m in bundle.modules:
            modules_by_id[m.module_id] = m
    return replace(
        model,
        modularizations=tuple(b.modularization for b in bundles),
        model_modules=tuple(modules_by_id.values()),
        module_memberships=tuple(mm for b in bundles for mm in b.memberships),
        module_ports=tuple(p for b in bundles for p in b.ports),
    )


def rebuild_bundle(
    bundle: CandidateModularizationBundle,
    groups: tuple[ModuleContentKey, ...],
    *,
    ports: tuple[ModulePort, ...] | None = None,
) -> CandidateModularizationBundle:
    """Build a new, validated bundle from ``groups`` (one content key per new module) --
    every membership row's own ``role``/``notes``/``confidence``/``provenance_refs`` is
    preserved from ``bundle``'s own original row for that exact ``(component_type,
    component_id)`` pair (never fabricated). Module ids are freshly content-derived; a module
    whose own content is byte-identical to one that already existed in ``bundle`` naturally
    re-derives the identical id (content-addressing, never a coincidence).

    ``ports`` (optional): the candidate's own new port list, already rebuilt by the caller
    (``ADD_BOUNDARY``/``REMOVE_BOUNDARY`` build this explicitly). When omitted (every other
    operator), ports are carried over from ``bundle`` for any module whose own content did not
    change, and dropped for any module whose content did -- never a fabricated boundary for a
    module that did not exist before this rebuild.

    Uses ``PENDING_MODULARIZATION_ID`` throughout -- ``search.py``'s own ``restamp_
    modularization_id`` assigns the real, final candidate id only after dedup/retention.
    """
    original_by_component: dict[tuple[str, str], ModuleMembership] = {}
    for m in bundle.memberships:
        original_by_component.setdefault((m.component_type.value, m.component_id), m)

    old_module_ids = {m.module_id for m in bundle.memberships}
    existing_modules_by_id = {m.module_id: m for m in bundle.modules}

    new_modules: list[ModelModule] = []
    new_memberships: list[ModuleMembership] = []
    new_module_ids: list[str] = []
    for group in groups:
        new_module_id = derive_module_id(group)
        new_module_ids.append(new_module_id)
        new_modules.append(
            existing_modules_by_id.get(new_module_id)
            or ModelModule(module_id=new_module_id, name=new_module_id)
        )
        for component_type_value, component_id in sorted(group):
            original = original_by_component[(component_type_value, component_id)]
            new_memberships.append(
                ModuleMembership(
                    membership_id=derive_membership_id(
                        modularization_id=PENDING_MODULARIZATION_ID,
                        module_id=new_module_id,
                        component_type=original.component_type,
                        component_id=component_id,
                    ),
                    modularization_id=PENDING_MODULARIZATION_ID,
                    module_id=new_module_id,
                    component_type=original.component_type,
                    component_id=component_id,
                    role=original.role,
                    notes=original.notes,
                    confidence=original.confidence,
                    provenance_refs=original.provenance_refs,
                )
            )

    if ports is None:
        # A port survives iff the module it was attached to has *identical content* before and
        # after this rebuild -- never matched by comparing old/new module_id strings directly,
        # since an old id may not itself be content-addressed yet (e.g. a freshly-extracted
        # seed's own human-given module ids). new_id_by_old_content remaps such a surviving
        # port's own module_id to its correct, freshly-derived id.
        old_content_by_module_id = {
            mid: module_content_key(bundle.memberships, mid) for mid in old_module_ids
        }
        new_id_by_content = {group: derive_module_id(group) for group in groups}
        rebuilt_ports = []
        for p in bundle.ports:
            old_content = old_content_by_module_id.get(p.module_id)
            new_module_id = new_id_by_content.get(old_content) if old_content is not None else None
            if new_module_id is None:
                continue
            rebuilt_ports.append(
                ModulePort(
                    port_id=derive_port_id(
                        modularization_id=PENDING_MODULARIZATION_ID,
                        module_id=new_module_id,
                        species_id=p.species_id,
                        direction_value=p.direction.value,
                    ),
                    modularization_id=PENDING_MODULARIZATION_ID,
                    module_id=new_module_id,
                    species_id=p.species_id,
                    direction=p.direction,
                    role=p.role,
                    externally_controlled=p.externally_controlled,
                    initial_value=p.initial_value,
                    unit=p.unit,
                    assumptions=p.assumptions,
                    provenance_refs=p.provenance_refs,
                )
            )
        ports = tuple(rebuilt_ports)

    modularization = ModelModularization(
        modularization_id=PENDING_MODULARIZATION_ID,
        name=PENDING_MODULARIZATION_ID,
        method=ModularizationMethod.SEARCH_GENERATED,
        module_ids=tuple(new_module_ids),
    )
    return CandidateModularizationBundle(
        modularization=modularization,
        modules=tuple(new_modules),
        memberships=tuple(new_memberships),
        ports=ports,
    )


def restamp_modularization_id(
    bundle: CandidateModularizationBundle, candidate_id: str
) -> CandidateModularizationBundle:
    """Replace ``PENDING_MODULARIZATION_ID`` throughout ``bundle`` with the real, final,
    globally-unique ``candidate_id`` -- the one place a candidate's own ``modularization_id``
    (and every membership/port id folding it in) is actually assigned."""
    memberships = tuple(
        replace(
            m,
            modularization_id=candidate_id,
            membership_id=derive_membership_id(
                modularization_id=candidate_id,
                module_id=m.module_id,
                component_type=m.component_type,
                component_id=m.component_id,
            ),
        )
        for m in bundle.memberships
    )
    ports = tuple(
        replace(
            p,
            modularization_id=candidate_id,
            port_id=derive_port_id(
                modularization_id=candidate_id,
                module_id=p.module_id,
                species_id=p.species_id,
                direction_value=p.direction.value,
            ),
        )
        for p in bundle.ports
    )
    modularization = replace(
        bundle.modularization, modularization_id=candidate_id, name=candidate_id
    )
    return CandidateModularizationBundle(
        modularization=modularization,
        modules=bundle.modules,
        memberships=memberships,
        ports=ports,
    )


def module_group(
    bundle: CandidateModularizationBundle, module_id: str
) -> ModuleContentKey:
    return module_content_key(bundle.memberships, module_id)


def canonicalize_bundle(bundle: CandidateModularizationBundle) -> CandidateModularizationBundle:
    """Re-derive every module id in ``bundle`` from its own content -- the one step that makes
    the "module_id is always content-addressed" invariant hold from the very start. Every
    bundle this package produces from here on (every proposal operator calls ``rebuild_bundle``,
    which always re-derives ids from the groups it is given) maintains this invariant
    automatically; only a freshly-``extract_bundle``'d seed (whose own module ids were
    whatever a human/caller originally gave them) needs this one explicit call."""
    module_ids = sorted({m.module_id for m in bundle.memberships})
    groups = tuple(module_group(bundle, mid) for mid in module_ids)
    return rebuild_bundle(bundle, groups)


__all__ = [
    "PENDING_MODULARIZATION_ID",
    "attach_bundle",
    "attach_many",
    "canonicalize_bundle",
    "extract_bundle",
    "module_group",
    "rebuild_bundle",
    "restamp_modularization_id",
]
