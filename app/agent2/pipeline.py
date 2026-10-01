"""Agent 2's canonical, official, end-to-end orchestration entrypoint.

**Five-Agent Workflow V1 Hardening increment.** Before this module existed, every discrete
Agent 2 stage function (translate, assemble, characterize, assign kinetic laws, resolve
reaction context, resolve enzyme concentrations, build enzyme-state dynamics, declare
parameters, assess boundaries, decompose modules, assemble the model specification, generate
Antimony) was independently implemented and independently tested, but no single piece of
already-committed code chained them together in the correct order outside of test fixtures.
That meant the integration harness (and any other real caller) had no choice but to either
hand-roll that chain itself -- risking silently mis-implementing Agent 2's own orchestration,
exactly the failure mode this project's own conventions forbid -- or consume an already-real,
previously-captured artifact instead of ever actually running Agent 2 live.

``run_agent2_pipeline`` closes that gap. It calls only existing, already-committed, already-
independently-tested stage functions, in the one order each stage's own test suite already
proves correct:

* The base seven-stage chain (``assemble_full_network`` through
  ``assemble_model_specification``) mirrors ``tests/agent2/test_model_specification.py``'s own
  ``_assemble_full`` helper verbatim.
* Reaction-context resolution's placement (immediately after network assembly, its own result
  replacing ``network`` for every subsequent stage) mirrors
  ``tests/agent2/test_reaction_context.py``'s own already-passing chain.
* The enzyme-state-dynamics two-pass wiring (boundaries/modules computed against the
  pre-augmentation network and assignments; the final parameters and model computed against
  the augmented network and merged assignments) mirrors
  ``tests/agent2/test_enzyme_state_dynamics.py``'s own already-passing chain and
  ``app.agent2.enzyme_state_dynamics.builder``'s own documented two-pass contract.

No scientific policy of any individual stage is changed, reassessed, or reimplemented here --
this module only sequences them. See ``docs/19_canonical_orchestration_entrypoint.md`` for the
full evidence trail backing this exact ordering.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.agent2.antimony import generate_antimony
from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.enzyme_state_dynamics import (
    build_enzyme_state_dynamics,
    merge_transition_assignments,
)
from app.agent2.handoff.translate import translate_agent1_view_to_agent2
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.kinetics.reaction_context import (
    apply_resolved_reaction_context,
    resolve_kinetic_measurement_reaction_context,
)
from app.agent2.model_specification import assemble_model_specification
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.quantitative_context import resolve_enzyme_concentrations
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    Agent2OutputPackage,
    ModelSpecification,
)
from app.agent2.version import AGENT2_DOWNSTREAM_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class Agent2PipelineResult:
    """Everything one real ``run_agent2_pipeline`` call produces.

    ``package`` is Agent 2's own full, rich internal output (``ModelSpecification`` +
    ``FullAntimonyArtifact``) -- kept for a caller that needs it. ``downstream_handoff`` is the
    one canonical, already-serialized, plain-dict contract Agents 3, 4, and 5 actually consume
    (``AGENT2_DOWNSTREAM_CONTRACT_VERSION``) -- see ``build_canonical_downstream_handoff``.
    """

    package: Agent2OutputPackage
    downstream_handoff: dict[str, Any]


def run_agent2_pipeline(
    agent1_handoff: Mapping[str, Any] | Agent1CuratedKnowledgeViewContract,
) -> Agent2PipelineResult:
    """Run Agent 2's complete, canonical pipeline end to end.

    ``agent1_handoff`` is either a plain JSON-decoded dict shaped like Agent 1's own real
    ``Agent1CuratedKnowledgeView`` (the same shape ``translate_agent1_view_to_agent2`` already
    accepts), or an already-constructed ``Agent1CuratedKnowledgeViewContract`` -- never mutated
    either way. Every intermediate stage result is a brand-new object; nothing is modified in
    place anywhere in this chain (every stage function this module calls is itself already
    documented as non-mutating).

    Raises whatever typed error the first stage that cannot proceed raises (e.g.
    ``MalformedHandoffPayloadError`` for a malformed input dict, or any stage's own reference-
    integrity error) -- never silently recovers from or works around a real orchestration
    defect. Deterministic: identical input always produces identical output (every stage this
    calls is itself already documented and tested as deterministic).
    """
    if isinstance(agent1_handoff, Agent1CuratedKnowledgeViewContract):
        handoff = agent1_handoff
    else:
        handoff = translate_agent1_view_to_agent2(agent1_handoff)

    network = assemble_full_network(handoff)
    resolutions = resolve_kinetic_measurement_reaction_context(network)
    network = apply_resolved_reaction_context(network, resolutions)

    characterization = characterize_full_network(network)
    kinetic_laws = assign_kinetic_laws(characterization, network)
    enzyme_concentrations = resolve_enzyme_concentrations(network)
    dynamics = build_enzyme_state_dynamics(network, enzyme_concentrations)

    # Pass 1: boundaries/modules computed against the pre-augmentation network and assignments
    # -- mirrors app.agent2.enzyme_state_dynamics.builder's own documented two-pass contract.
    parameters_for_boundaries = declare_parameters(kinetic_laws, network, enzyme_concentrations)
    boundaries = assess_boundaries(
        network, characterization, kinetic_laws, parameters_for_boundaries
    )
    modules = decompose_network(network, kinetic_laws, parameters_for_boundaries, boundaries)

    # Pass 2: final parameters and model computed against the enzyme-state-augmented network
    # and the merged (original + transition) kinetic-law assignments.
    merged_kinetic_laws = merge_transition_assignments(
        kinetic_laws, dynamics.transition_assignments
    )
    final_parameters = declare_parameters(
        merged_kinetic_laws,
        dynamics.network,
        enzyme_concentrations,
        enzyme_state_concentrations=dynamics.state_concentrations,
    )
    model = assemble_model_specification(
        dynamics.network,
        merged_kinetic_laws,
        final_parameters,
        boundaries,
        modules,
        enzyme_concentrations=enzyme_concentrations,
        enzyme_state_pools=dynamics.pools,
        enzyme_state_concentrations=dynamics.state_concentrations,
    )
    package = generate_antimony(model)
    downstream_handoff = build_canonical_downstream_handoff(model, package)
    return Agent2PipelineResult(package=package, downstream_handoff=downstream_handoff)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _compartment_dict(compartment) -> dict[str, Any]:
    return {
        "compartment_id": compartment.compartment_id,
        "name": compartment.name,
        "initial_volume": _decimal_str(compartment.initial_volume),
        "volume_unit": compartment.volume_unit,
        "constant": compartment.constant,
    }


def _species_dict(species) -> dict[str, Any]:
    return {
        "species_id": species.species_id,
        "name": species.name,
        "compartment_id": species.compartment_id,
        "source_compound_id": species.source_compound_id,
        "source_enzyme_state_id": species.source_enzyme_state_id,
        "initial_amount": _decimal_str(species.initial_amount),
        "initial_concentration": _decimal_str(species.initial_concentration),
        "constant": species.constant,
        "boundary_condition": species.boundary_condition,
        "initialization_source": species.initialization_source.value
        if species.initialization_source is not None
        else None,
    }


def _participant_dict(participant) -> dict[str, Any]:
    return {
        "species_id": participant.species_id,
        "role": participant.role.value if hasattr(participant.role, "value") else participant.role,
        "stoichiometry": _decimal_str(participant.stoichiometry),
    }


def _reaction_dict(reaction) -> dict[str, Any]:
    return {
        "reaction_id": reaction.reaction_id,
        "name": reaction.name,
        "reversible": reaction.reversible,
        "participants": [_participant_dict(p) for p in reaction.participants],
    }


def _kinetic_law_dict(law) -> dict[str, Any]:
    return {
        "kinetic_law_id": law.kinetic_law_id,
        "reaction_id": law.reaction_id,
        "law_type": law.law_type.value if hasattr(law.law_type, "value") else law.law_type,
        "expression": law.expression,
        "parameter_ids": list(law.parameter_ids),
        "species_ids": list(law.species_ids),
        "enzyme_state_id": law.enzyme_state_id,
        "protein_id": law.protein_id,
        "complex_id": law.complex_id,
        "assumptions": list(law.assumptions),
    }


def _parameter_dict(parameter) -> dict[str, Any]:
    return {
        "parameter_id": parameter.parameter_id,
        "name": parameter.name,
        "source": parameter.source.value
        if hasattr(parameter.source, "value")
        else parameter.source,
        "value": _decimal_str(parameter.value),
        "unit": parameter.unit,
        "reaction_id": parameter.reaction_id,
        "kinetic_law_assignment_id": parameter.kinetic_law_assignment_id,
        "uncertainty_text": parameter.uncertainty_text,
        "provenance_refs": list(parameter.provenance_refs),
        "lower_bound": _decimal_str(parameter.lower_bound),
        "upper_bound": _decimal_str(parameter.upper_bound),
        "fixed": parameter.fixed,
    }


def _model_assumption_dict(assumption) -> dict[str, Any]:
    return {
        "assumption_id": assumption.assumption_id,
        "category": assumption.category,
        "statement": assumption.statement,
        "related_entity_ids": list(assumption.related_entity_ids),
        "reason_code": assumption.reason_code,
    }


def build_canonical_downstream_handoff(
    model: ModelSpecification, package: Agent2OutputPackage
) -> dict[str, Any]:
    """Serialize ``model``/``package`` into the one canonical downstream handoff dict Agents 3,
    4, and 5 all consume unchanged (``AGENT2_DOWNSTREAM_CONTRACT_VERSION``,
    ``"agent2-downstream-v1"``).

    Every value is read directly from ``model``/``package`` -- never recomputed, never
    defaulted, never omitted silently. This is the single producer-side function responsible
    for this contract's own shape; Agents 3/4/5 each parse exactly this shape (see
    ``docs/19_canonical_orchestration_entrypoint.md`` for the full field-by-field mapping).
    """
    network = model.full_network
    antimony = package.full_antimony
    return {
        "contract_version": AGENT2_DOWNSTREAM_CONTRACT_VERSION,
        "model_id": model.model_id,
        "network_id": network.network_id,
        "antimony_text": antimony.antimony_text,
        "antimony_generator_version": antimony.generator_version,
        "readiness": antimony.readiness.value
        if hasattr(antimony.readiness, "value")
        else antimony.readiness,
        "unresolved_reaction_ids": list(antimony.unresolved_reaction_ids),
        "unresolved_kinetic_law_ids": list(antimony.unresolved_kinetic_law_ids),
        "compartments": [_compartment_dict(c) for c in network.compartments],
        "species": [_species_dict(s) for s in network.species],
        "reactions": [_reaction_dict(r) for r in network.reactions],
        "kinetic_laws": [_kinetic_law_dict(k) for k in model.kinetic_laws],
        "parameters": [_parameter_dict(p) for p in model.parameters],
        "model_assumptions": [_model_assumption_dict(a) for a in model.model_assumptions],
    }


__all__ = ["Agent2PipelineResult", "build_canonical_downstream_handoff", "run_agent2_pipeline"]
