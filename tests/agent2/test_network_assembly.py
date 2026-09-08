"""Tests for Whole-Network Assembly (Increment 2): ``app.agent2.network``.

No simulation, no Antimony, no database, no filesystem, no network access
anywhere -- every test constructs an ``Agent1CuratedKnowledgeViewContract``
directly and calls ``assemble_full_network`` on it.
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app.agent2.network import assemble_full_network
from app.agent2.network.errors import (
    DanglingReferenceError,
    DuplicateCuratedIdentifierError,
    MissingCompartmentReferenceError,
    NetworkAssemblyError,
    UnknownParticipantRoleError,
)
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedAllostericInteraction,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeModification,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    CuratedRegulatoryInteraction,
    FullNetwork,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.1"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _compartment(**overrides) -> CuratedCompartment:
    merged = {"id": "cyto", "name": "cytosol"} | overrides
    return CuratedCompartment(**merged)


def _compound(**overrides) -> CuratedCompound:
    merged = {"id": "glc", "name": "glucose"} | overrides
    return CuratedCompound(**merged)


def _reaction(**overrides) -> CuratedReaction:
    merged = {"id": "r1", "name": "reaction 1"} | overrides
    return CuratedReaction(**merged)


def _participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "glc",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _enzyme_association(**overrides) -> CuratedReactionEnzymeAssociation:
    merged = {"reaction_id": "r1", "protein_id": "p1", "relationship": "CATALYZES"} | overrides
    return CuratedReactionEnzymeAssociation(**merged)


def _regulation(**overrides) -> CuratedRegulatoryInteraction:
    merged = {
        "id": "reg1",
        "regulator_type": "compound",
        "target_type": "reaction",
        "effect": "INHIBITION",
        "regulator_id": "glc",
        "target_id": "r1",
    } | overrides
    return CuratedRegulatoryInteraction(**merged)


def _kinetic_measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km1",
        "parameter_type": "KM",
        "value": Decimal("0.5"),
        "unit": "mM",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _enzyme_state(**overrides) -> CuratedEnzymeState:
    merged = {"id": "es1", "state_type": "PHOSPHORYLATED", "protein_id": "p1"} | overrides
    return CuratedEnzymeState(**merged)


def _enzyme_modification(**overrides) -> CuratedEnzymeModification:
    merged = {
        "id": "mod1",
        "enzyme_state_id": "es1",
        "modification_type": "PHOSPHORYLATION",
        "residue": "Ser129",
    } | overrides
    return CuratedEnzymeModification(**merged)


def _allosteric_interaction(**overrides) -> CuratedAllostericInteraction:
    merged = {
        "id": "allo1",
        "enzyme_state_id": "es1",
        "ligand_compound_id": "glc",
        "effect": "ACTIVATOR",
    } | overrides
    return CuratedAllostericInteraction(**merged)


def _enzyme_state_transition(**overrides) -> CuratedEnzymeStateTransition:
    merged = {
        "id": "trans1",
        "from_state_id": "es0",
        "to_state_id": "es1",
        "transition_type": "PHOSPHORYLATION",
    } | overrides
    return CuratedEnzymeStateTransition(**merged)


def _simple_reaction_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
    """One compartment, one compound, one reaction with one reactant participant."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(_participant(),),
    )


# --- Public API ------------------------------------------------------------------------------


def test_assemble_full_network_returns_full_network():
    network = assemble_full_network(_simple_reaction_handoff())
    assert isinstance(network, FullNetwork)


def test_assemble_full_network_rejects_non_handoff_type():
    with pytest.raises(TypeError):
        assemble_full_network("not a handoff")


# --- Empty network -----------------------------------------------------------------------------


def test_empty_handoff_produces_empty_network():
    network = assemble_full_network(_handoff())
    assert network.compartments == ()
    assert network.species == ()
    assert network.reactions == ()
    assert network.enzyme_associations == ()
    assert network.regulatory_interactions == ()
    assert network.kinetic_measurements == ()


def test_empty_network_is_still_valid_full_network():
    network = assemble_full_network(_handoff())
    assert isinstance(network, FullNetwork)


# --- Compartments ------------------------------------------------------------------------------


def test_compartments_preserve_agent1_identifiers():
    handoff = _handoff(compartments=(_compartment(id="cyto", name="cytosol"),))
    network = assemble_full_network(handoff)
    assert len(network.compartments) == 1
    compartment = network.compartments[0]
    assert compartment.compartment_id == "cyto"
    assert compartment.name == "cytosol"
    assert compartment.source_entity_id == "cyto"


def test_multiple_compartments_all_preserved():
    handoff = _handoff(
        compartments=(
            _compartment(id="cyto", name="cytosol"),
            _compartment(id="mito", name="mitochondrion"),
        )
    )
    network = assemble_full_network(handoff)
    assert {c.compartment_id for c in network.compartments} == {"cyto", "mito"}


def test_compartments_never_merged_even_if_same_name():
    handoff = _handoff(
        compartments=(_compartment(id="c1", name="cytosol"), _compartment(id="c2", name="cytosol"))
    )
    network = assemble_full_network(handoff)
    assert len(network.compartments) == 2


# --- Species ---------------------------------------------------------------------------------


def test_compartment_specific_species_are_distinct():
    """glucose[cytosol] and glucose[mitochondrion] must never collapse into one species."""
    handoff = _handoff(
        compartments=(
            _compartment(id="cyto", name="cytosol"),
            _compartment(id="mito", name="mitochondrion"),
        ),
        compounds=(_compound(id="glc", name="glucose"),),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="glc", compartment_id="cyto"),
            _participant(
                reaction_id="r2", compound_id="glc", compartment_id="mito", role="PRODUCT"
            ),
        ),
    )
    network = assemble_full_network(handoff)
    assert len(network.species) == 2
    compartments_seen = {s.compartment_id for s in network.species}
    assert compartments_seen == {"cyto", "mito"}


def test_duplicated_compound_across_participants_yields_one_species():
    """Same compound in the same compartment, referenced by many participants, is one species."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", role="REACTANT"),
            _participant(reaction_id="r2", role="PRODUCT"),
        ),
    )
    network = assemble_full_network(handoff)
    assert len(network.species) == 1


def test_species_preserves_originating_compound_and_compartment():
    network = assemble_full_network(_simple_reaction_handoff())
    species = network.species[0]
    assert species.source_compound_id == "glc"
    assert species.compartment_id == "cyto"
    assert species.name == "glucose"


def test_compound_never_referenced_gets_no_species():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="glc"), _compound(id="unused", name="never referenced")),
        reactions=(_reaction(),),
        reaction_participants=(_participant(),),
    )
    network = assemble_full_network(handoff)
    assert {s.source_compound_id for s in network.species} == {"glc"}


# --- Reactions ---------------------------------------------------------------------------------


def test_reaction_preserves_identifier_and_name():
    network = assemble_full_network(_simple_reaction_handoff())
    reaction = network.reactions[0]
    assert reaction.reaction_id == "r1"
    assert reaction.source_reaction_id == "r1"


def test_reaction_reversible_preserved_verbatim():
    network = assemble_full_network(_simple_reaction_handoff(reversible=True))
    assert network.reactions[0].reversible is True


def test_reaction_reversible_none_never_inferred():
    network = assemble_full_network(_simple_reaction_handoff(reversible=None))
    assert network.reactions[0].reversible is None


def test_multiple_reactions_all_assembled():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1"),
            _participant(reaction_id="r2"),
            _participant(reaction_id="r3"),
        ),
    )
    network = assemble_full_network(handoff)
    assert {r.reaction_id for r in network.reactions} == {"r1", "r2", "r3"}


def test_reaction_with_zero_participants_fails_construction():
    """Never infer missing participants -- a reaction with none must raise, not be padded."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(),),
        reaction_participants=(),
    )
    with pytest.raises(ValueError):
        assemble_full_network(handoff)


def test_disconnected_subnetworks_assemble_successfully():
    """Two reactions sharing nothing must still assemble -- connectivity is Agent 3's job."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="glc"), _compound(id="pyr", name="pyruvate")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="glc"),
            _participant(reaction_id="r2", compound_id="pyr", role="PRODUCT"),
        ),
    )
    network = assemble_full_network(handoff)
    assert len(network.reactions) == 2
    assert len(network.species) == 2


# --- Reaction participants ---------------------------------------------------------------------


def test_participant_stoichiometry_preserved_verbatim():
    handoff = _simple_reaction_handoff()
    handoff = dataclasses.replace(
        handoff, reaction_participants=(_participant(stoichiometry=Decimal("2.5")),)
    )
    network = assemble_full_network(handoff)
    assert network.reactions[0].participants[0].stoichiometry == Decimal("2.5")


def test_participant_role_mapped_correctly():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(
            _compound(id="glc"),
            _compound(id="pyr", name="pyruvate"),
            _compound(id="mod", name="modifier compound"),
        ),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(compound_id="glc", role="REACTANT"),
            _participant(compound_id="pyr", role="PRODUCT"),
            _participant(compound_id="mod", role="MODIFIER"),
        ),
    )
    network = assemble_full_network(handoff)
    roles = {p.role.value for p in network.reactions[0].participants}
    assert roles == {"REACTANT", "PRODUCT", "MODIFIER"}


def test_unknown_participant_role_raises():
    handoff = _simple_reaction_handoff()
    handoff = dataclasses.replace(handoff, reaction_participants=(_participant(role="COFACTOR"),))
    with pytest.raises(UnknownParticipantRoleError):
        assemble_full_network(handoff)


def test_never_invents_atp_adp_or_water():
    """A reaction with only what Agent 1 curated must never gain extra participants."""
    network = assemble_full_network(_simple_reaction_handoff())
    names = {network.species[i].name for i in range(len(network.species))}
    assert names == {"glucose"}


# --- Enzyme associations -----------------------------------------------------------------------


def test_enzyme_association_preserved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    network = assemble_full_network(handoff)
    assert len(network.enzyme_associations) == 1
    association = network.enzyme_associations[0]
    assert association.reaction_id == "r1"
    assert association.protein_id == "p1"
    assert association.relationship == "CATALYZES"


def test_enzyme_association_linked_from_reaction():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    network = assemble_full_network(handoff)
    reaction = network.reactions[0]
    assert reaction.enzyme_association_ids == (network.enzyme_associations[0].association_id,)


def test_multiple_enzyme_associations_for_one_reaction_all_preserved():
    """Isozymes: never collapsed into one 'preferred' association."""
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id="p2"),
        ),
    )
    network = assemble_full_network(handoff)
    assert len(network.enzyme_associations) == 2
    assert len(network.reactions[0].enzyme_association_ids) == 2


def test_enzyme_association_ids_are_deterministic():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    first = assemble_full_network(handoff)
    second = assemble_full_network(handoff)
    assert (
        first.enzyme_associations[0].association_id == second.enzyme_associations[0].association_id
    )


def test_enzyme_association_dangling_reaction_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="does-not-exist"),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


# --- Regulation --------------------------------------------------------------------------------


def test_regulation_preserved_exactly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), regulatory_interactions=(_regulation(),)
    )
    network = assemble_full_network(handoff)
    assert len(network.regulatory_interactions) == 1
    regulation = network.regulatory_interactions[0]
    assert regulation.id == "reg1"
    assert regulation.effect == "INHIBITION"
    assert regulation.regulator_id == "glc"
    assert regulation.target_id == "r1"


def test_regulation_linked_from_target_reaction():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), regulatory_interactions=(_regulation(),)
    )
    network = assemble_full_network(handoff)
    assert network.reactions[0].regulatory_interaction_ids == ("reg1",)


def test_regulation_never_interpreted_or_classified():
    """The effect string is carried through unmodified -- never mapped to a closed vocabulary."""
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        regulatory_interactions=(_regulation(effect="a weird custom effect"),),
    )
    network = assemble_full_network(handoff)
    assert network.regulatory_interactions[0].effect == "a weird custom effect"


def test_regulation_between_two_reactions_indexed_on_both():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1"),
            _participant(reaction_id="r2"),
        ),
        regulatory_interactions=(
            _regulation(
                regulator_type="reaction", regulator_id="r1", target_type="reaction", target_id="r2"
            ),
        ),
    )
    network = assemble_full_network(handoff)
    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    assert reactions_by_id["r1"].regulatory_interaction_ids == ("reg1",)
    assert reactions_by_id["r2"].regulatory_interaction_ids == ("reg1",)


# --- Kinetic measurements ----------------------------------------------------------------------


def test_kinetic_measurement_preserved_verbatim():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(
                reported_rate_law="v = Vmax*S/(Km+S)",
                source="BRENDA",
                confidence_score=Decimal("80"),
            ),
        ),
    )
    network = assemble_full_network(handoff)
    assert len(network.kinetic_measurements) == 1
    measurement = network.kinetic_measurements[0]
    assert measurement.parameter_type == "KM"
    assert measurement.value == Decimal("0.5")
    assert measurement.unit == "mM"
    assert measurement.reported_rate_law == "v = Vmax*S/(Km+S)"
    assert measurement.source == "BRENDA"
    assert measurement.confidence_score == Decimal("80")


def test_kinetic_measurements_never_assigned_to_reactions():
    """ReactionSpecification has no kinetic_measurement_ids field at all -- structural guard."""
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), kinetic_measurements=(_kinetic_measurement(),)
    )
    network = assemble_full_network(handoff)
    reaction_field_names = {f.name for f in dataclasses.fields(network.reactions[0])}
    assert "kinetic_measurement_ids" not in reaction_field_names


def test_kinetic_measurements_attached_at_network_level_not_per_reaction():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), kinetic_measurements=(_kinetic_measurement(),)
    )
    network = assemble_full_network(handoff)
    assert len(network.kinetic_measurements) == 1
    # Attached to the network, never folded into the reaction itself.
    assert not hasattr(network.reactions[0], "kinetic_measurements")


def test_kinetic_measurement_never_becomes_parameter_specification():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), kinetic_measurements=(_kinetic_measurement(),)
    )
    network = assemble_full_network(handoff)
    assert isinstance(network.kinetic_measurements[0], CuratedKineticMeasurement)


def test_multiple_kinetic_measurements_all_preserved_never_averaged():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", value=Decimal("0.3")),
            _kinetic_measurement(id="km2", value=Decimal("0.7")),
        ),
    )
    network = assemble_full_network(handoff)
    values = {m.value for m in network.kinetic_measurements}
    assert values == {Decimal("0.3"), Decimal("0.7")}


# --- Enzyme regulatory states (Increment 3) -----------------------------------------------------


def test_enzyme_states_preserved_by_assembly():
    handoff = dataclasses.replace(_simple_reaction_handoff(), enzyme_states=(_enzyme_state(),))
    network = assemble_full_network(handoff)
    assert network.enzyme_states == (_enzyme_state(),)


def test_enzyme_modifications_preserved_by_assembly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        enzyme_modifications=(_enzyme_modification(),),
    )
    network = assemble_full_network(handoff)
    assert network.enzyme_modifications == (_enzyme_modification(),)


def test_allosteric_interactions_preserved_by_assembly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        allosteric_interactions=(_allosteric_interaction(),),
    )
    network = assemble_full_network(handoff)
    assert network.allosteric_interactions == (_allosteric_interaction(),)


def test_enzyme_state_transitions_preserved_by_assembly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_state_transitions=(_enzyme_state_transition(),),
    )
    network = assemble_full_network(handoff)
    assert network.enzyme_state_transitions == (_enzyme_state_transition(),)


def test_state_specific_reaction_enzyme_association_preserved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    network = assemble_full_network(handoff)
    assert network.enzyme_associations[0].enzyme_state_id == "es1"


def test_state_specific_kinetic_measurement_state_reference_preserved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        kinetic_measurements=(_kinetic_measurement(enzyme_state_id="es1"),),
    )
    network = assemble_full_network(handoff)
    assert network.kinetic_measurements[0].enzyme_state_id == "es1"


def test_dangling_enzyme_modification_state_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), enzyme_modifications=(_enzyme_modification(),)
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_dangling_allosteric_interaction_state_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), allosteric_interactions=(_allosteric_interaction(),)
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_dangling_enzyme_state_transition_from_state_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es1"),),
        enzyme_state_transitions=(_enzyme_state_transition(),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_dangling_state_specific_reaction_enzyme_association_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="unknown-state"),
        ),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_dangling_state_specific_kinetic_measurement_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(_kinetic_measurement(enzyme_state_id="unknown-state"),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_duplicate_enzyme_state_ids_raise():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(), _enzyme_state()),
    )
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


def test_enzyme_state_family_assembly_still_deterministic():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_modifications=(_enzyme_modification(),),
        allosteric_interactions=(_allosteric_interaction(),),
        enzyme_state_transitions=(_enzyme_state_transition(),),
    )
    first = assemble_full_network(handoff)
    second = assemble_full_network(handoff)
    assert first == second


# --- Confidence and provenance preservation -----------------------------------------------------


def test_confidence_on_kinetic_measurement_never_recomputed():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(confidence_score=Decimal("42"), confidence_class="MODERATE"),
        ),
    )
    network = assemble_full_network(handoff)
    measurement = network.kinetic_measurements[0]
    assert measurement.confidence_score == Decimal("42")
    assert measurement.confidence_class == "MODERATE"


def test_provenance_preserved_via_source_entity_ids():
    network = assemble_full_network(_simple_reaction_handoff())
    assert network.compartments[0].source_entity_id == "cyto"
    assert network.species[0].source_compound_id == "glc"
    assert network.reactions[0].source_reaction_id == "r1"


# --- Determinism ------------------------------------------------------------------------------


def test_assembly_is_deterministic():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(_enzyme_association(),),
        regulatory_interactions=(_regulation(),),
        kinetic_measurements=(_kinetic_measurement(),),
    )
    first = assemble_full_network(handoff)
    second = assemble_full_network(handoff)
    assert first == second


def test_assembly_never_mutates_handoff():
    handoff = _simple_reaction_handoff()
    before = dataclasses.replace(handoff)
    assemble_full_network(handoff)
    assert handoff == before


# --- Duplicate identifiers -----------------------------------------------------------------------


def test_duplicate_compartment_ids_raise():
    handoff = _handoff(compartments=(_compartment(id="c1"), _compartment(id="c1", name="other")))
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


def test_duplicate_compound_ids_raise():
    handoff = _handoff(compounds=(_compound(id="c1"), _compound(id="c1", name="other")))
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


def test_duplicate_reaction_ids_raise():
    handoff = _handoff(reactions=(_reaction(id="r1"), _reaction(id="r1", name="other")))
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


def test_duplicate_regulatory_interaction_ids_raise():
    handoff = _handoff(regulatory_interactions=(_regulation(id="reg1"), _regulation(id="reg1")))
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


def test_duplicate_kinetic_measurement_ids_raise():
    handoff = _handoff(
        kinetic_measurements=(_kinetic_measurement(id="km1"), _kinetic_measurement(id="km1"))
    )
    with pytest.raises(DuplicateCuratedIdentifierError):
        assemble_full_network(handoff)


# --- Dangling / invalid references -----------------------------------------------------------


def test_participant_dangling_reaction_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_participants=(_participant(reaction_id="does-not-exist"),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_participant_dangling_compound_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_participants=(_participant(compound_id="does-not-exist"),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_participant_dangling_compartment_reference_raises():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_participants=(_participant(compartment_id="does-not-exist"),),
    )
    with pytest.raises(DanglingReferenceError):
        assemble_full_network(handoff)


def test_participant_missing_compartment_reference_raises():
    """Agent 1 v1 allows a nullable compartment reference; SpeciesSpecification requires one."""
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_participants=(_participant(compartment_id=None),)
    )
    with pytest.raises(MissingCompartmentReferenceError):
        assemble_full_network(handoff)


def test_all_network_errors_are_value_errors():
    """Every custom error must remain catchable as a plain ValueError."""
    for error_cls in (
        NetworkAssemblyError,
        DuplicateCuratedIdentifierError,
        DanglingReferenceError,
        UnknownParticipantRoleError,
        MissingCompartmentReferenceError,
    ):
        assert issubclass(error_cls, ValueError)


# --- Constructor failure on inconsistent data (defense in depth) -------------------------------


def test_construction_failure_never_produces_partial_network():
    """A failed assembly must never leave a half-built FullNetwork reachable."""
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_participants=(_participant(role="NOT_A_ROLE"),)
    )
    with pytest.raises(UnknownParticipantRoleError):
        result = assemble_full_network(handoff)
        del result  # unreachable; assemble_full_network must raise before returning


# --- Scope-safety: structural assembly only -----------------------------------------------------


def test_network_package_never_imports_forbidden_modeling_libraries():
    forbidden_roots = {"tellurium", "roadrunner", "libsbml", "antimony", "COPASI", "scipy", "numpy"}
    for path in (APP_ROOT / "agent2" / "network").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert not (imported_roots & forbidden_roots), (
            f"{path} imports {imported_roots & forbidden_roots}"
        )


def test_network_package_never_imports_agent1_package():
    for path in (APP_ROOT / "agent2" / "network").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert "agent1" not in imported_roots


def test_network_package_defines_no_kinetic_law_or_boundary_or_module_logic():
    forbidden_substrings = (
        "kinetic_law_id =",
        "KineticLawSpecification(",
        "BoundaryAssessment(",
        "ModuleSpecification(",
        "ModuleDecomposition(",
        "ParameterSpecification(",
        "antimony",
    )
    for path in (APP_ROOT / "agent2" / "network").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_network_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in (APP_ROOT / "agent2" / "network").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert not (imported_roots & forbidden_roots)
