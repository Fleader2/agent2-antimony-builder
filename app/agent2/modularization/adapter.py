"""Module Decomposition/Modularization Reconciliation increment: convert the pre-existing
heuristic ``ModuleDecompositionSet`` (``app.agent2.boundaries.assess_boundaries`` ->
``app.agent2.modules.decompose_network``) into the unified ``ModelModularization``/
``ModelModule``/``ModuleMembership``/``ModulePort`` representation -- the *one* producer of
that representation this repository ships today, among what may in the future be several
(a ``USER_DEFINED`` modularization a caller constructs directly, a future ``IMPORTED`` one
from an external source, or a future ``TOPOLOGICAL``/``FUNCTIONAL``/``DYNAMIC``/
``SENSITIVITY_BASED``/``HYBRID`` algorithmic one).

Never a second, parallel module representation: a converted ``ModuleDecomposition`` is
attached to ``ModelSpecification`` *only* via the fields this module's own output populates
(``modularizations``/``model_modules``/``module_memberships``/``module_ports``) -- the old
``ModuleSpecification``/``ModuleDecomposition`` objects themselves remain purely an
intermediate the heuristic algorithm still produces internally, never stored on
``ModelSpecification`` directly (that field was removed -- see that type's own docstring).

Maps the heuristic's own qualitative, evidence-based partition to ``ModularizationMethod
.TOPOLOGICAL`` -- the closest existing reserved vocabulary (boundary-likelihood-driven
connectivity, never a biological-function/sensitivity/dynamics-based method) -- without
implementing any *new* automatic-discovery algorithm: the discovery already existed
(``decompose_network``), this module only reshapes its already-decided output.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.modules.types import ModuleDecompositionSet
from app.agent2.types import (
    ModelModularization,
    ModelModule,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ModulePort,
    ModulePortDirection,
)
from app.agent2.version import MODULARIZATION_POLICY_VERSION


def _qualify(modularization_id: str, raw_module_id: str) -> str:
    """A module id, qualified by its own owning modularization -- see
    ``modularizations_from_decomposition_set``'s own module-level docstring note on why this
    is never the heuristic decomposer's bare ``module_NNN`` id directly."""
    return f"{modularization_id}::{raw_module_id}"


@dataclass(frozen=True, slots=True)
class ModularizationBundle:
    """One converted ``ModuleDecomposition``, ready to spread directly onto
    ``ModelSpecification``'s own ``modularizations``/``model_modules``/``module_memberships``/
    ``module_ports`` fields (each a 1-tuple here; a caller combining several decompositions
    concatenates several bundles' own tuples together)."""

    modularizations: tuple[ModelModularization, ...]
    model_modules: tuple[ModelModule, ...]
    module_memberships: tuple[ModuleMembership, ...]
    module_ports: tuple[ModulePort, ...]


def modularizations_from_decomposition_set(
    decomposition_set: ModuleDecompositionSet,
    *,
    policy_version: str = MODULARIZATION_POLICY_VERSION,
) -> ModularizationBundle:
    """Convert every ``ModuleDecomposition`` in ``decomposition_set`` into its own
    ``ModelModularization`` (plus that modularization's own modules/memberships/ports),
    concatenated into one ``ModularizationBundle``.

    Zero decompositions (an empty ``decomposition_set.decompositions``) is a perfectly valid
    input -- it simply produces an empty bundle, never an error (task instructions: "do not
    require GENERATED models to have exactly one decomposition"). Multiple decompositions are
    likewise supported natively: each becomes its own, independent, equally-unranked
    ``ModelModularization`` -- never one marked more authoritative than another.
    """
    modularizations: list[ModelModularization] = []
    model_modules: list[ModelModule] = []
    module_memberships: list[ModuleMembership] = []
    module_ports: list[ModulePort] = []

    specs_by_id = {spec.module_id: spec for spec in decomposition_set.module_specifications}

    for decomposition in decomposition_set.decompositions:
        modularization_id = f"modularization::{decomposition.decomposition_id}"

        # Module ids are qualified by their own owning modularization_id below -- never the
        # heuristic decomposer's own bare "module_NNN" directly. That naming is anchored only
        # to one decomposition's own connected-component order (docs/10 §14), so two
        # independent decompositions of the identical network legitimately produce the
        # identical bare id (e.g. both naming their first module "module_001") -- a real,
        # expected collision once more than one decomposition/modularization can coexist on
        # one ``ModelSpecification`` (whose own ``model_modules[].module_id`` must be globally
        # unique, never merely unique per modularization).
        qualified_module_ids = tuple(
            _qualify(modularization_id, mid) for mid in decomposition.module_ids
        )
        modularizations.append(
            ModelModularization(
                modularization_id=modularization_id,
                name=decomposition.name,
                method=ModularizationMethod.TOPOLOGICAL,
                module_ids=qualified_module_ids,
                description=decomposition.explanation,
                assumptions=decomposition.assumptions,
                provenance_refs=(
                    f"module-decomposition::{decomposition.decomposition_id}",
                    f"modularization-policy::{policy_version}",
                ),
            )
        )

        selected_specs = [
            specs_by_id[module_id]
            for module_id in sorted(decomposition.module_ids)
            if module_id in specs_by_id
        ]
        for spec in selected_specs:
            qualified_id = _qualify(modularization_id, spec.module_id)
            model_modules.append(
                ModelModule(
                    module_id=qualified_id,
                    name=spec.name,
                    assumptions=spec.assumptions,
                    provenance_refs=spec.provenance_refs,
                )
            )
            for component_type, component_ids in (
                (ModuleComponentType.REACTION, spec.reaction_ids),
                (ModuleComponentType.SPECIES, spec.species_ids),
                (ModuleComponentType.PARAMETER, spec.parameter_ids),
            ):
                for component_id in sorted(component_ids):
                    module_memberships.append(
                        ModuleMembership(
                            membership_id=(
                                f"membership::{modularization_id}::{qualified_id}::"
                                f"{component_type.value}::{component_id}"
                            ),
                            modularization_id=modularization_id,
                            module_id=qualified_id,
                            component_type=component_type,
                            component_id=component_id,
                        )
                    )

        # One port per (module_id, species_id, direction) actually implied by this
        # decomposition's own InterModuleBoundaryInterface records -- deduplicated first
        # (the identical species can legitimately cross more than one distinct boundary
        # between the same two modules), never one port per interface naively.
        port_assumptions: dict[tuple[str, str, ModulePortDirection], set[str]] = {}
        for interface in decomposition.interfaces:
            for species_id in interface.shared_species_ids:
                note = (
                    f"Derived from InterModuleBoundaryInterface {interface.interface_id!r} "
                    f"(boundary={interface.boundary_id!r}, "
                    f"likelihood={interface.boundary_likelihood.value})."
                )
                for raw_module_id, direction in (
                    (interface.upstream_module_id, ModulePortDirection.OUTPUT),
                    (interface.downstream_module_id, ModulePortDirection.INPUT),
                ):
                    key = (_qualify(modularization_id, raw_module_id), species_id, direction)
                    port_assumptions.setdefault(key, set()).add(note)

        for (module_id, species_id, direction), notes in sorted(port_assumptions.items()):
            module_ports.append(
                ModulePort(
                    port_id=(
                        f"port::{modularization_id}::{module_id}::{species_id}::{direction.value}"
                    ),
                    modularization_id=modularization_id,
                    module_id=module_id,
                    species_id=species_id,
                    direction=direction,
                    assumptions=tuple(sorted(notes)),
                )
            )

    return ModularizationBundle(
        modularizations=tuple(modularizations),
        model_modules=tuple(model_modules),
        module_memberships=tuple(module_memberships),
        module_ports=tuple(module_ports),
    )


__all__ = ["ModularizationBundle", "modularizations_from_decomposition_set"]
