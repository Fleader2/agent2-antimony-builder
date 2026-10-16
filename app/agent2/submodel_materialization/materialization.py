"""Canonical Submodel Materialization for Recursive Modularization (task instructions §1):
given a parent ``ModelSpecification`` + ``modularization_id`` + ``module_id``, materialize a
new, independently valid, genuinely scoped canonical ``ModelSpecification`` containing only
that module's own reactions and their dependency closure.

This is the one, real fix for the disclosed scope limit ``app.agent2.candidate_orchestration
.round.build_submodel`` has carried since the Recursive Agent-4-Assisted Candidate Search
Orchestration increment: that function carries ``full_network``/``kinetic_laws``/``parameters``
over from the parent *unchanged*, so a "submodel" is only a re-scoped *modularization* sitting
on top of the full, untruncated network. ``build_submodel`` now delegates to
``materialize_submodel`` below -- see that function's own docstring.
"""

from __future__ import annotations

from dataclasses import replace

from app.agent2.modularization_search.identity import derive_membership_id, derive_port_id
from app.agent2.submodel_materialization.closure import compute_dependency_closure
from app.agent2.submodel_materialization.errors import SubmodelMaterializationReferenceError
from app.agent2.submodel_materialization.types import (
    BoundaryTreatmentRecord,
    SubmodelMaterializationLineage,
    SubmodelMaterializationResult,
)
from app.agent2.types import (
    FullNetwork,
    ModelModularization,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
)
from app.agent2.version import SUBMODEL_MATERIALIZATION_POLICY_VERSION


def materialize_submodel(
    model: ModelSpecification,
    modularization_id: str,
    module_id: str,
    *,
    policy_version: str = SUBMODEL_MATERIALIZATION_POLICY_VERSION,
) -> SubmodelMaterializationResult:
    """Materialize ``module_id`` (of ``model.modularizations`` entry ``modularization_id``)
    into its own standalone, canonical ``ModelSpecification`` (task instructions §1).

    Retains, and only ever retains: the module's own internal reactions (its ``REACTION``
    ``ModuleMembership`` rows); every participating/internal species (including explicit
    enzyme species required by a retained reaction's own kinetic law); required parameters;
    required compartments; rules/events/observables that a disclosed, heuristic reference scan
    confirms stay within that closure (``app.agent2.submodel_materialization.closure``); and
    the module's own existing boundary ``ModulePort`` rows, restamped (never re-authored) onto
    the new modularization/module id.

    Never mutates ``model`` -- every object returned is either copied verbatim or built via
    ``dataclasses.replace``.

    Raises ``SubmodelMaterializationReferenceError`` if ``modularization_id``/``module_id``
    does not exist, or if the module has zero internal reactions (nothing to materialize).
    Any other structural gap (the dependency closure genuinely missing something a retained
    reaction/kinetic-law requires) surfaces as the final, assembled ``ModelSpecification``'s own
    already-complete reference-integrity validation raising ``ValueError`` -- never silently
    repaired, never re-validated a second time here.
    """
    modularizations_by_id = {m.modularization_id: m for m in model.modularizations}
    modularization = modularizations_by_id.get(modularization_id)
    if modularization is None:
        raise SubmodelMaterializationReferenceError(
            f"materialize_submodel: modularization_id {modularization_id!r} does not exist in "
            f"model.modularizations (known: {sorted(modularizations_by_id)})"
        )
    if module_id not in modularization.module_ids:
        raise SubmodelMaterializationReferenceError(
            f"materialize_submodel: module_id {module_id!r} is not a member of modularization "
            f"{modularization_id!r}'s own module_ids {modularization.module_ids!r}"
        )
    parent_module = next((m for m in model.model_modules if m.module_id == module_id), None)
    if parent_module is None:
        raise SubmodelMaterializationReferenceError(
            f"materialize_submodel: module_id {module_id!r} is not a member of model.model_modules"
        )

    own_memberships = tuple(
        m
        for m in model.module_memberships
        if m.modularization_id == modularization_id and m.module_id == module_id
    )
    reaction_ids = frozenset(
        m.component_id for m in own_memberships if m.component_type is ModuleComponentType.REACTION
    )
    if not reaction_ids:
        raise SubmodelMaterializationReferenceError(
            f"materialize_submodel: module_id {module_id!r} of modularization "
            f"{modularization_id!r} has zero REACTION memberships -- nothing to materialize"
        )

    closure = compute_dependency_closure(model, reaction_ids)

    submodel_modularization_id = f"submodel::{modularization_id}::{module_id}"
    submodel_module_id = module_id

    # --- FullNetwork: structural components only, filtered to the closure; every
    # non-structural "supporting data" field is dropped (task instructions §1: "do not retain
    # unrelated parent-network components") except ``enzyme_states``, filtered to just the
    # states a retained explicit enzyme species/kinetic law actually names -- required to keep
    # ``SpeciesSpecification.source_enzyme_state_id`` (the field that *makes* a retained species
    # an explicit enzyme species) referentially valid. ``reaction.enzyme_association_ids``/
    # ``.regulatory_interaction_ids`` are stripped (their own registries are dropped) -- these
    # name curation-provenance links, never executable semantics (task instructions §6 lists
    # stoichiometry/reversibility/kinetic laws/enzyme concentrations/parameters as the
    # protected semantics; association/regulation *links* are not among them).
    compartments_by_id = {c.compartment_id: c for c in model.full_network.compartments}
    species_by_id = {s.species_id: s for s in model.full_network.species}
    reactions_by_id = {r.reaction_id: r for r in model.full_network.reactions}
    enzyme_states_by_id = {s.id: s for s in model.full_network.enzyme_states}

    submodel_compartments = tuple(
        compartments_by_id[cid] for cid in compartments_by_id if cid in closure.compartment_ids
    )
    submodel_species = tuple(
        species_by_id[sid] for sid in species_by_id if sid in closure.species_ids
    )
    submodel_reactions = tuple(
        replace(reactions_by_id[rid], enzyme_association_ids=(), regulatory_interaction_ids=())
        for rid in reactions_by_id
        if rid in closure.reaction_ids
    )
    submodel_enzyme_states = tuple(
        enzyme_states_by_id[eid] for eid in enzyme_states_by_id if eid in closure.enzyme_state_ids
    )

    submodel_network = FullNetwork(
        network_id=f"{model.full_network.network_id}::submodel::{module_id}",
        name=f"{model.full_network.name} :: {module_id}",
        compartments=submodel_compartments,
        species=submodel_species,
        reactions=submodel_reactions,
        enzyme_states=submodel_enzyme_states,
        organism_id=model.full_network.organism_id,
        assumptions=model.full_network.assumptions,
        provenance_refs=model.full_network.provenance_refs,
    )

    submodel_kinetic_laws = tuple(
        law for law in model.kinetic_laws if law.kinetic_law_id in closure.kinetic_law_ids
    )
    submodel_parameters = tuple(
        p for p in model.parameters if p.parameter_id in closure.parameter_ids
    )
    submodel_rules = tuple(r for r in model.rules if r.rule_id in closure.retained_rule_ids)
    submodel_events = tuple(e for e in model.events if e.event_id in closure.retained_event_ids)
    submodel_observables = tuple(
        o for o in model.observables if o.observable_id in closure.retained_observable_ids
    )

    # --- module_memberships: freshly derived from the closure (never copied from
    # ``own_memberships`` verbatim, since those may name only REACTION components) -- a
    # pre-existing row for the identical (component_type, component_id) pair has its own
    # role/notes/confidence/provenance_refs preserved; a newly-derived component (a species/
    # parameter/rule/event/observable the closure added, with no pre-existing row) gets a
    # fresh, defaulted membership row.
    original_by_key = {(m.component_type, m.component_id): m for m in own_memberships}

    def _membership(component_type: ModuleComponentType, component_id: str) -> ModuleMembership:
        original = original_by_key.get((component_type, component_id))
        return ModuleMembership(
            membership_id=derive_membership_id(
                modularization_id=submodel_modularization_id,
                module_id=submodel_module_id,
                component_type=component_type,
                component_id=component_id,
            ),
            modularization_id=submodel_modularization_id,
            module_id=submodel_module_id,
            component_type=component_type,
            component_id=component_id,
            role=original.role if original is not None else None,
            notes=original.notes if original is not None else None,
            confidence=original.confidence if original is not None else None,
            provenance_refs=original.provenance_refs if original is not None else (),
        )

    submodel_memberships = (
        tuple(
            _membership(ModuleComponentType.REACTION, rid) for rid in sorted(closure.reaction_ids)
        )
        + tuple(
            _membership(ModuleComponentType.SPECIES, sid) for sid in sorted(closure.species_ids)
        )
        + tuple(
            _membership(ModuleComponentType.PARAMETER, pid) for pid in sorted(closure.parameter_ids)
        )
        + tuple(
            _membership(ModuleComponentType.RULE, rid) for rid in sorted(closure.retained_rule_ids)
        )
        + tuple(
            _membership(ModuleComponentType.EVENT, eid)
            for eid in sorted(closure.retained_event_ids)
        )
        + tuple(
            _membership(ModuleComponentType.OBSERVABLE, oid)
            for oid in sorted(closure.retained_observable_ids)
        )
    )

    # --- module_ports: the module's own existing boundary ports, restamped (never
    # re-authored) onto the new modularization/module id -- task instructions §2: "boundary
    # species must remain canonical references with clear roles ... preserve information
    # needed to generate an independently executable standalone Antimony submodel."
    own_ports = tuple(
        p
        for p in model.module_ports
        if p.modularization_id == modularization_id and p.module_id == module_id
    )
    submodel_ports = tuple(
        replace(
            port,
            port_id=derive_port_id(
                modularization_id=submodel_modularization_id,
                module_id=submodel_module_id,
                species_id=port.species_id,
                direction_value=port.direction.value,
            ),
            modularization_id=submodel_modularization_id,
            module_id=submodel_module_id,
        )
        for port in own_ports
    )

    submodel_modularization = ModelModularization(
        modularization_id=submodel_modularization_id,
        name=submodel_modularization_id,
        method=ModularizationMethod.USER_DEFINED,
        module_ids=(submodel_module_id,),
        description=(
            f"Canonical submodel materialized from {model.model_id}::"
            f"{modularization_id}::{module_id}"
        ),
    )

    lineage_ref = (
        f"submodel-materialization::parent-model={model.model_id}::"
        f"parent-modularization={modularization_id}::parent-module={module_id}::"
        f"policy={policy_version}"
    )
    submodel_provenance_refs = tuple(dict.fromkeys((*model.provenance_refs, lineage_ref)))

    submodel = ModelSpecification(
        model_id=f"{model.model_id}::submodel::{module_id}",
        name=f"{model.name} :: {module_id}",
        full_network=submodel_network,
        organism_id=model.organism_id,
        kinetic_laws=submodel_kinetic_laws,
        parameters=submodel_parameters,
        assumptions=model.assumptions,
        model_assumptions=model.model_assumptions,
        rules=submodel_rules,
        events=submodel_events,
        observables=submodel_observables,
        source_type=model.source_type,
        source_provenance=model.source_provenance,
        modularizations=(submodel_modularization,),
        model_modules=(parent_module,),
        module_memberships=submodel_memberships,
        module_ports=submodel_ports,
        provenance_refs=submodel_provenance_refs,
        contract_version=model.contract_version,
    )

    boundary_treatments = tuple(
        BoundaryTreatmentRecord(
            species_id=port.species_id,
            direction=port.direction,
            role=port.role,
            externally_controlled=port.externally_controlled,
            initial_value=port.initial_value,
        )
        for port in sorted(submodel_ports, key=lambda p: (p.species_id, p.direction.value))
    )

    lineage = SubmodelMaterializationLineage(
        parent_model_id=model.model_id,
        parent_modularization_id=modularization_id,
        parent_module_id=module_id,
        submodel_modularization_id=submodel_modularization_id,
        submodel_module_id=submodel_module_id,
        retained_reaction_ids=tuple(sorted(closure.reaction_ids)),
        retained_species_ids=tuple(sorted(closure.species_ids)),
        retained_parameter_ids=tuple(sorted(closure.parameter_ids)),
        retained_compartment_ids=tuple(sorted(closure.compartment_ids)),
        explicit_enzyme_species_ids=tuple(sorted(closure.explicit_enzyme_species_ids)),
        retained_rule_ids=tuple(sorted(closure.retained_rule_ids)),
        retained_event_ids=tuple(sorted(closure.retained_event_ids)),
        retained_observable_ids=tuple(sorted(closure.retained_observable_ids)),
        boundary_treatments=boundary_treatments,
        materialization_policy_version=policy_version,
    )

    return SubmodelMaterializationResult(
        submodel=submodel,
        submodel_modularization_id=submodel_modularization_id,
        submodel_module_id=submodel_module_id,
        lineage=lineage,
        unresolved_dependencies=closure.unresolved_dependencies,
    )


__all__ = ["materialize_submodel"]
