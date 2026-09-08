"""Reaction and Enzyme-State Characterization (Increment 3): the second executable
stage of Agent 2.

``characterize_full_network`` is this package's one public entry point. It
is a deterministic, pure function: no database, no filesystem, no network
access, no connector, no LLM, no simulation, and no randomness or
wall-clock time anywhere in its call graph. Calling it twice with an equal
``FullNetwork`` always returns an equal ``NetworkCharacterization``.

It describes what kind of biochemical/modeling situation each reaction and
catalytic enzyme state represents -- it never assigns a
``KineticLawSpecification``, declares a ``ParameterSpecification``,
assesses a ``BoundaryAssessment``, decomposes a module, or generates
Antimony (Increment 3 instructions, Steps 27-29; verified structurally,
see ``tests/agent2/test_characterization_scope.py``).

**Reads only already-validated data.** ``FullNetwork.__post_init__``
already guarantees every cross-reference within it resolves
(``app.agent2.types._validate_full_network_references``) -- this module
never re-validates that, and ``app.agent2.characterization.validation
.require_resolved`` exists only as a defensive backstop for a reference
that should never actually fail to resolve.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from app.agent2.characterization.classifier import classify_reaction
from app.agent2.characterization.types import (
    CharacterizationFlag,
    EnzymeStateCharacterization,
    NetworkCharacterization,
    ReactionCharacterization,
    UnresolvedFeature,
)
from app.agent2.characterization.validation import require_full_network
from app.agent2.types import (
    CuratedEnzymeState,
    CuratedKineticMeasurement,
    FullNetwork,
    ParticipantRole,
    ReactionEnzymeAssociation,
    ReactionSpecification,
)
from app.agent2.version import REACTION_CHARACTERIZATION_POLICY_VERSION

_REGULATION_INCOMPLETENESS_ASSUMPTION = (
    "Agent 1's regulation curation pipeline is known-incomplete "
    "(docs/23_agent1_v1_scope_and_completion.md section 11 in the Agent 1 repository); "
    "REGULATION_CONTEXT_INCOMPLETE is therefore emitted for every reaction regardless of "
    "whether any RegulatoryInteraction is curated for it -- absence of a curated regulatory "
    "fact is never treated as absence of biological regulation."
)


def _group_ids(items: Iterable, *, key: Callable, value: Callable) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        group_key = key(item)
        if group_key is None:
            continue
        grouped.setdefault(group_key, []).append(value(item))
    return grouped


def _group_objects(items: Iterable, *, key: Callable) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        group_key = key(item)
        if group_key is None:
            continue
        grouped.setdefault(group_key, []).append(item)
    return grouped


def characterize_full_network(network: FullNetwork) -> NetworkCharacterization:
    """Deterministically characterize every reaction and catalytic enzyme state in ``network``.

    See module docstring. Raises
    ``app.agent2.characterization.errors.UnsupportedCharacterizationInputError``
    if ``network`` is not a ``FullNetwork``.
    """
    require_full_network(network)

    species_by_id = {s.species_id: s for s in network.species}
    enzyme_associations_by_id = {a.association_id: a for a in network.enzyme_associations}
    transitions_by_id = {t.id: t for t in network.enzyme_state_transitions}

    modifications_by_state = _group_ids(
        network.enzyme_modifications, key=lambda m: m.enzyme_state_id, value=lambda m: m.id
    )
    allosteric_by_state = _group_ids(
        network.allosteric_interactions, key=lambda a: a.enzyme_state_id, value=lambda a: a.id
    )
    transitions_by_reaction = _group_ids(
        network.enzyme_state_transitions, key=lambda t: t.reaction_id, value=lambda t: t.id
    )
    transitions_by_state: dict[str, list[str]] = {}
    for transition in network.enzyme_state_transitions:
        transitions_by_state.setdefault(transition.from_state_id, []).append(transition.id)
        transitions_by_state.setdefault(transition.to_state_id, []).append(transition.id)
    kinetic_measurements_by_reaction = _group_objects(
        network.kinetic_measurements, key=lambda m: m.reaction_id
    )
    kinetic_measurements_by_state = _group_objects(
        network.kinetic_measurements, key=lambda m: m.enzyme_state_id
    )
    catalytic_reactions_by_state: dict[str, list[str]] = {}
    for association in network.enzyme_associations:
        if association.enzyme_state_id is not None:
            catalytic_reactions_by_state.setdefault(association.enzyme_state_id, []).append(
                association.reaction_id
            )

    reaction_characterizations = tuple(
        sorted(
            (
                _characterize_reaction(
                    reaction,
                    network=network,
                    species_by_id=species_by_id,
                    enzyme_associations_by_id=enzyme_associations_by_id,
                    transitions_by_id=transitions_by_id,
                    modifications_by_state=modifications_by_state,
                    allosteric_by_state=allosteric_by_state,
                    transitions_by_reaction=transitions_by_reaction,
                    kinetic_measurements_by_reaction=kinetic_measurements_by_reaction,
                    kinetic_measurements_by_state=kinetic_measurements_by_state,
                )
                for reaction in network.reactions
            ),
            key=lambda characterization: characterization.reaction_id,
        )
    )

    enzyme_state_characterizations = tuple(
        sorted(
            (
                _characterize_enzyme_state(
                    state,
                    modifications_by_state=modifications_by_state,
                    allosteric_by_state=allosteric_by_state,
                    transitions_by_state=transitions_by_state,
                    catalytic_reactions_by_state=catalytic_reactions_by_state,
                    kinetic_measurements_by_state=kinetic_measurements_by_state,
                )
                for state in network.enzyme_states
            ),
            key=lambda characterization: characterization.enzyme_state_id,
        )
    )

    return NetworkCharacterization(
        network_id=network.network_id,
        reaction_characterizations=reaction_characterizations,
        enzyme_state_characterizations=enzyme_state_characterizations,
        characterization_policy_version=REACTION_CHARACTERIZATION_POLICY_VERSION,
        assumptions=(_REGULATION_INCOMPLETENESS_ASSUMPTION,),
    )


def _characterize_reaction(
    reaction: ReactionSpecification,
    *,
    network: FullNetwork,
    species_by_id: dict,
    enzyme_associations_by_id: dict[str, ReactionEnzymeAssociation],
    transitions_by_id: dict,
    modifications_by_state: dict[str, list[str]],
    allosteric_by_state: dict[str, list[str]],
    transitions_by_reaction: dict[str, list[str]],
    kinetic_measurements_by_reaction: dict[str, list[CuratedKineticMeasurement]],
    kinetic_measurements_by_state: dict[str, list[CuratedKineticMeasurement]],
) -> ReactionCharacterization:
    participant_species_ids = tuple(p.species_id for p in reaction.participants)
    reactant_species_ids = tuple(
        p.species_id for p in reaction.participants if p.role is ParticipantRole.REACTANT
    )
    product_species_ids = tuple(
        p.species_id for p in reaction.participants if p.role is ParticipantRole.PRODUCT
    )
    modifier_species_ids = tuple(
        p.species_id for p in reaction.participants if p.role is ParticipantRole.MODIFIER
    )

    catalyst_association_ids = tuple(sorted(reaction.enzyme_association_ids))
    catalytic_protein_ids_set: set[str] = set()
    catalytic_complex_ids_set: set[str] = set()
    catalytic_enzyme_state_ids_set: set[str] = set()
    for association_id in reaction.enzyme_association_ids:
        association = enzyme_associations_by_id[association_id]
        if association.protein_id is not None:
            catalytic_protein_ids_set.add(association.protein_id)
        if association.complex_id is not None:
            catalytic_complex_ids_set.add(association.complex_id)
        if association.enzyme_state_id is not None:
            catalytic_enzyme_state_ids_set.add(association.enzyme_state_id)
    catalytic_protein_ids = tuple(sorted(catalytic_protein_ids_set))
    catalytic_complex_ids = tuple(sorted(catalytic_complex_ids_set))
    catalytic_enzyme_state_ids = tuple(sorted(catalytic_enzyme_state_ids_set))

    regulation_ids = tuple(sorted(reaction.regulatory_interaction_ids))

    allosteric_interaction_ids_set: set[str] = set()
    for state_id in catalytic_enzyme_state_ids:
        allosteric_interaction_ids_set.update(allosteric_by_state.get(state_id, ()))
    allosteric_interaction_ids = tuple(sorted(allosteric_interaction_ids_set))

    this_reaction_transition_ids = tuple(
        sorted(transitions_by_reaction.get(reaction.reaction_id, ()))
    )
    enzyme_state_ids_set = set(catalytic_enzyme_state_ids)
    for transition_id in this_reaction_transition_ids:
        transition = transitions_by_id[transition_id]
        enzyme_state_ids_set.add(transition.from_state_id)
        enzyme_state_ids_set.add(transition.to_state_id)
    enzyme_state_ids = tuple(sorted(enzyme_state_ids_set))

    general_measurements = {
        m.id: m
        for m in kinetic_measurements_by_reaction.get(reaction.reaction_id, ())
        if m.enzyme_state_id is None
    }
    state_specific_measurements: dict[str, CuratedKineticMeasurement] = {
        m.id: m
        for m in kinetic_measurements_by_reaction.get(reaction.reaction_id, ())
        if m.enzyme_state_id is not None
    }
    for state_id in catalytic_enzyme_state_ids:
        for measurement in kinetic_measurements_by_state.get(state_id, ()):
            state_specific_measurements[measurement.id] = measurement
    kinetic_measurement_ids = tuple(sorted(general_measurements))
    state_specific_kinetic_measurement_ids = tuple(sorted(state_specific_measurements))
    reported_rate_law_measurement_ids = tuple(
        sorted(
            measurement.id
            for measurement in (
                *general_measurements.values(),
                *state_specific_measurements.values(),
            )
            if measurement.reported_rate_law is not None
        )
    )

    reversible = reaction.reversible
    is_state_transition_reaction = bool(this_reaction_transition_ids)
    reaction_classes = classify_reaction(
        reaction,
        species_by_id=species_by_id,
        is_state_transition_reaction=is_state_transition_reaction,
    )

    flags: set[CharacterizationFlag] = set()
    if catalyst_association_ids:
        flags.add(CharacterizationFlag.HAS_CATALYST)
    if len(catalyst_association_ids) > 1:
        flags.add(CharacterizationFlag.MULTIPLE_CATALYSTS)
    if catalytic_enzyme_state_ids:
        flags.add(CharacterizationFlag.STATE_SPECIFIC_CATALYSIS)
    if regulation_ids:
        flags.add(CharacterizationFlag.HAS_REGULATION)
    if allosteric_interaction_ids:
        flags.add(CharacterizationFlag.HAS_ALLOSTERY)
    if any(modifications_by_state.get(state_id) for state_id in catalytic_enzyme_state_ids):
        flags.add(CharacterizationFlag.HAS_MODIFIED_ENZYME_STATE)
    if this_reaction_transition_ids:
        flags.add(CharacterizationFlag.HAS_STATE_TRANSITION)
    if kinetic_measurement_ids:
        flags.add(CharacterizationFlag.HAS_KINETIC_MEASUREMENTS)
    if state_specific_kinetic_measurement_ids:
        flags.add(CharacterizationFlag.HAS_STATE_SPECIFIC_KINETICS)
    if reported_rate_law_measurement_ids:
        flags.add(CharacterizationFlag.HAS_REPORTED_RATE_LAW)
    if reversible is not None:
        flags.add(CharacterizationFlag.REVERSIBILITY_KNOWN)
    else:
        flags.add(CharacterizationFlag.REVERSIBILITY_UNKNOWN)
    compartments_seen = {species_by_id[sid].compartment_id for sid in participant_species_ids}
    if len(compartments_seen) > 1:
        flags.add(CharacterizationFlag.MULTIPLE_COMPARTMENTS)
    if modifier_species_ids:
        flags.add(CharacterizationFlag.PARTICIPANT_MODIFIERS_PRESENT)

    unresolved: set[UnresolvedFeature] = set()
    if not catalyst_association_ids:
        unresolved.add(UnresolvedFeature.NO_CATALYST_INFORMATION)
    else:
        general_catalyst_ids = set(catalytic_protein_ids) | set(catalytic_complex_ids)
        if general_catalyst_ids and not catalytic_enzyme_state_ids:
            has_known_states_for_general_catalyst = any(
                state.protein_id in general_catalyst_ids
                or state.complex_id in general_catalyst_ids
                for state in network.enzyme_states
            )
            if has_known_states_for_general_catalyst:
                unresolved.add(UnresolvedFeature.CATALYST_STATE_UNSPECIFIED)
                unresolved.add(UnresolvedFeature.ENZYME_STATE_CONTEXT_INCOMPLETE)
    if not kinetic_measurement_ids and not state_specific_kinetic_measurement_ids:
        unresolved.add(UnresolvedFeature.NO_KINETIC_MEASUREMENTS)
    if not state_specific_kinetic_measurement_ids:
        unresolved.add(UnresolvedFeature.NO_STATE_SPECIFIC_KINETICS)
    if not reported_rate_law_measurement_ids:
        unresolved.add(UnresolvedFeature.NO_REPORTED_RATE_LAW)
    if reversible is None:
        unresolved.add(UnresolvedFeature.REVERSIBILITY_UNKNOWN)
    # Always disclosed: Agent 1's regulation pipeline is known-incomplete, so absence of a
    # curated RegulatoryInteraction is never treated as absence of biological regulation
    # (Increment 3 instructions, Step 23). See _REGULATION_INCOMPLETENESS_ASSUMPTION.
    unresolved.add(UnresolvedFeature.REGULATION_CONTEXT_INCOMPLETE)
    if not reactant_species_ids and not product_species_ids:
        unresolved.add(UnresolvedFeature.PARTICIPANT_CONTEXT_INCOMPLETE)

    return ReactionCharacterization(
        reaction_id=reaction.reaction_id,
        reaction_name=reaction.name,
        participant_species_ids=participant_species_ids,
        reactant_species_ids=reactant_species_ids,
        product_species_ids=product_species_ids,
        modifier_species_ids=modifier_species_ids,
        reversible=reversible,
        reaction_classes=reaction_classes,
        catalyst_association_ids=catalyst_association_ids,
        catalytic_protein_ids=catalytic_protein_ids,
        catalytic_complex_ids=catalytic_complex_ids,
        catalytic_enzyme_state_ids=catalytic_enzyme_state_ids,
        regulation_ids=regulation_ids,
        allosteric_interaction_ids=allosteric_interaction_ids,
        enzyme_state_ids=enzyme_state_ids,
        enzyme_state_transition_ids=this_reaction_transition_ids,
        kinetic_measurement_ids=kinetic_measurement_ids,
        state_specific_kinetic_measurement_ids=state_specific_kinetic_measurement_ids,
        reported_rate_law_measurement_ids=reported_rate_law_measurement_ids,
        characterization_flags=tuple(sorted(flags, key=lambda flag: flag.value)),
        unresolved_features=tuple(sorted(unresolved, key=lambda feature: feature.value)),
        provenance_refs=reaction.provenance_refs,
    )


def _characterize_enzyme_state(
    state: CuratedEnzymeState,
    *,
    modifications_by_state: dict[str, list[str]],
    allosteric_by_state: dict[str, list[str]],
    transitions_by_state: dict[str, list[str]],
    catalytic_reactions_by_state: dict[str, list[str]],
    kinetic_measurements_by_state: dict[str, list[CuratedKineticMeasurement]],
) -> EnzymeStateCharacterization:
    return EnzymeStateCharacterization(
        enzyme_state_id=state.id,
        parent_protein_id=state.protein_id,
        parent_complex_id=state.complex_id,
        state_type=state.state_type,
        compartment_id=state.compartment_id,
        modification_ids=tuple(sorted(modifications_by_state.get(state.id, ()))),
        allosteric_interaction_ids=tuple(sorted(allosteric_by_state.get(state.id, ()))),
        transition_ids=tuple(sorted(set(transitions_by_state.get(state.id, ())))),
        catalytic_reaction_ids=tuple(sorted(set(catalytic_reactions_by_state.get(state.id, ())))),
        kinetic_measurement_ids=tuple(
            sorted(m.id for m in kinetic_measurements_by_state.get(state.id, ()))
        ),
    )


__all__ = ["characterize_full_network"]
