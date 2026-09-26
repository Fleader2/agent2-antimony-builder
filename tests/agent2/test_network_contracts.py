"""Tests for the full-network structural domain (Increment 1).

Covers ``CompartmentSpecification``, ``SpeciesSpecification``,
``ReactionParticipantSpecification``, ``ReactionSpecification``, and
``FullNetwork``. No network-assembly algorithm exists yet -- every network
here is constructed directly.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.types import (
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedKineticMeasurement,
    CuratedRegulatoryInteraction,
    FullNetwork,
    ParticipantRole,
    ReactionEnzymeAssociation,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "c1",
        "name": "cytosol",
        "source_scope": CompartmentSourceScope.AGENT1_CURATED,
        "source_entity_id": "agent1-compartment-1",
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "s1", "name": "ATP", "compartment_id": "c1"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "s1",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "test reaction",
        "participants": (_participant(),),
    } | overrides
    return ReactionSpecification(**merged)


# --- Enum vocabularies -----------------------------------------------------------------------


def test_participant_role_has_exactly_three_values():
    assert {member.value for member in ParticipantRole} == {"REACTANT", "PRODUCT", "MODIFIER"}


def test_compartment_source_scope_has_exactly_two_values():
    assert {member.value for member in CompartmentSourceScope} == {
        "AGENT1_CURATED",
        "MODELING_CONSTRUCT",
    }


# --- Immutability -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        CompartmentSpecification,
        SpeciesSpecification,
        ReactionParticipantSpecification,
        ReactionSpecification,
        FullNetwork,
    ],
)
def test_network_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_full_network_instance_is_immutable():
    network = FullNetwork(network_id="n1", name="test network")
    with pytest.raises(dataclasses.FrozenInstanceError):
        network.name = "renamed"


# --- CompartmentSpecification ------------------------------------------------------------------


def test_compartment_agent1_curated_requires_source_entity_id():
    with pytest.raises(ValueError):
        CompartmentSpecification(
            compartment_id="c1", name="cytosol", source_scope=CompartmentSourceScope.AGENT1_CURATED
        )


def test_compartment_modeling_construct_forbids_source_entity_id():
    with pytest.raises(ValueError):
        CompartmentSpecification(
            compartment_id="c1",
            name="synthetic",
            source_scope=CompartmentSourceScope.MODELING_CONSTRUCT,
            source_entity_id="should-not-be-here",
            assumptions=("declared for mass-balance closure",),
        )


def test_compartment_modeling_construct_requires_disclosed_assumption():
    with pytest.raises(ValueError):
        CompartmentSpecification(
            compartment_id="c1",
            name="synthetic",
            source_scope=CompartmentSourceScope.MODELING_CONSTRUCT,
        )


def test_compartment_modeling_construct_succeeds_with_disclosure():
    compartment = CompartmentSpecification(
        compartment_id="c1",
        name="synthetic",
        source_scope=CompartmentSourceScope.MODELING_CONSTRUCT,
        assumptions=("declared for mass-balance closure",),
    )
    assert compartment.source_entity_id is None


def test_compartment_initial_volume_must_be_decimal():
    with pytest.raises(TypeError):
        _compartment(initial_volume=1.0)
    compartment = _compartment(initial_volume=Decimal("1.0"), volume_unit="L")
    assert compartment.initial_volume == Decimal("1.0")


def test_compartment_never_invents_a_unit():
    compartment = _compartment(initial_volume=Decimal("1.0"))
    assert compartment.volume_unit is None


# --- SpeciesSpecification --------------------------------------------------------------------


def test_species_requires_compartment_id():
    with pytest.raises(ValueError):
        SpeciesSpecification(species_id="s1", name="ATP", compartment_id="")


def test_species_rejects_both_amount_and_concentration():
    with pytest.raises(ValueError):
        _species(initial_amount=Decimal("1"), initial_concentration=Decimal("2"))


def test_species_allows_amount_alone():
    species = _species(initial_amount=Decimal("1"))
    assert species.initial_amount == Decimal("1")
    assert species.initial_concentration is None


def test_species_numeric_fields_reject_float():
    with pytest.raises(TypeError):
        _species(initial_amount=1.0)
    with pytest.raises(TypeError):
        _species(initial_concentration=1.0)


def test_species_constant_and_boundary_condition_are_independent():
    species = _species(constant=True, boundary_condition=False)
    assert species.constant is True
    assert species.boundary_condition is False


def test_species_initialization_source_reuses_parameter_source():
    from app.agent2.types import ParameterSource

    species = _species(
        initial_amount=Decimal("1"), initialization_source=ParameterSource.PLACEHOLDER
    )
    assert species.initialization_source is ParameterSource.PLACEHOLDER
    with pytest.raises(TypeError):
        _species(initialization_source="PLACEHOLDER")


# --- ReactionParticipantSpecification ----------------------------------------------------------


def test_participant_stoichiometry_must_be_decimal():
    with pytest.raises(TypeError):
        _participant(stoichiometry=1.0)


def test_participant_stoichiometry_must_be_positive():
    with pytest.raises(ValueError):
        _participant(stoichiometry=Decimal("0"))
    with pytest.raises(ValueError):
        _participant(stoichiometry=Decimal("-1"))


def test_participant_role_requires_real_enum():
    with pytest.raises(TypeError):
        _participant(role="REACTANT")


def test_modifier_still_requires_positive_stoichiometry():
    """Increment 1 instructions, Step 5: mirrors Agent 1's own schema, which
    enforces stoichiometry > 0 for every role including MODIFIER."""
    modifier = _participant(role=ParticipantRole.MODIFIER, stoichiometry=Decimal("1"))
    assert modifier.role is ParticipantRole.MODIFIER
    with pytest.raises(ValueError):
        _participant(role=ParticipantRole.MODIFIER, stoichiometry=Decimal("0"))


# --- ReactionSpecification --------------------------------------------------------------------


def test_reaction_requires_at_least_one_participant():
    with pytest.raises(ValueError):
        ReactionSpecification(reaction_id="r1", name="empty reaction", participants=())


def test_reaction_reversible_defaults_to_none_never_inferred():
    reaction = _reaction()
    assert reaction.reversible is None


def test_reaction_kinetic_law_id_may_be_unresolved():
    reaction = _reaction()
    assert reaction.kinetic_law_id is None


def test_reaction_preserves_participant_multiplicity():
    participants = (
        _participant(species_id="s1", role=ParticipantRole.REACTANT, stoichiometry=Decimal("1")),
        _participant(species_id="s1", role=ParticipantRole.REACTANT, stoichiometry=Decimal("1")),
    )
    reaction = _reaction(participants=participants)
    assert len(reaction.participants) == 2


# --- FullNetwork -----------------------------------------------------------------------------


def test_full_network_builds_with_consistent_references():
    network = FullNetwork(
        network_id="n1",
        name="test network",
        compartments=(_compartment(),),
        species=(_species(),),
        reactions=(_reaction(),),
    )
    assert network.reactions[0].reaction_id == "r1"


def test_full_network_rejects_duplicate_compartment_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(), _compartment()),
        )


def test_full_network_rejects_duplicate_species_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(), _species()),
        )


def test_full_network_rejects_duplicate_reaction_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(),),
            reactions=(_reaction(), _reaction()),
        )


def test_full_network_rejects_species_with_undefined_compartment():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(),
            species=(_species(compartment_id="does-not-exist"),),
        )


def test_full_network_rejects_reaction_participant_with_undefined_species():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(),
            reactions=(_reaction(),),
        )


def test_full_network_never_performs_mass_balance_or_graph_validation():
    """A network with an isolated, disconnected reaction and no mass-balance
    check must still construct successfully -- that analysis is Agent 3's job."""
    network = FullNetwork(
        network_id="n1",
        name="test network",
        compartments=(_compartment(),),
        species=(_species(),),
        reactions=(_reaction(),),
    )
    assert network.network_id == "n1"


# --- ReactionEnzymeAssociation (Increment 2) --------------------------------------------------


def _enzyme_association(**overrides) -> ReactionEnzymeAssociation:
    merged = {
        "association_id": "e1",
        "reaction_id": "r1",
        "protein_id": "p1",
    } | overrides
    return ReactionEnzymeAssociation(**merged)


def test_enzyme_association_requires_non_empty_association_id():
    with pytest.raises(ValueError):
        _enzyme_association(association_id="")


def test_enzyme_association_requires_non_empty_reaction_id():
    with pytest.raises(ValueError):
        _enzyme_association(reaction_id="")


def test_enzyme_association_allows_protein_and_complex_both_absent():
    """Mirrors CuratedReactionEnzymeAssociation: 'expected', never enforced."""
    association = _enzyme_association(protein_id=None, complex_id=None)
    assert association.protein_id is None
    assert association.complex_id is None


def test_enzyme_association_is_frozen_dataclass():
    assert dataclasses.is_dataclass(ReactionEnzymeAssociation)
    assert ReactionEnzymeAssociation.__dataclass_params__.frozen is True


# --- FullNetwork: enzyme_associations/regulatory_interactions/kinetic_measurements ------------


def _regulation(**overrides) -> CuratedRegulatoryInteraction:
    merged = {
        "id": "reg1",
        "regulator_type": "compound",
        "target_type": "reaction",
        "effect": "INHIBITION",
        "target_id": "r1",
    } | overrides
    return CuratedRegulatoryInteraction(**merged)


def _kinetic_measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km1",
        "parameter_type": "KM",
        "value": Decimal("0.5"),
        "unit": "mM",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def test_full_network_carries_enzyme_associations():
    network = FullNetwork(
        network_id="n1",
        name="test network",
        compartments=(_compartment(),),
        species=(_species(),),
        reactions=(_reaction(enzyme_association_ids=("e1",)),),
        enzyme_associations=(_enzyme_association(),),
    )
    assert network.enzyme_associations[0].association_id == "e1"


def test_full_network_rejects_duplicate_enzyme_association_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(),),
            reactions=(_reaction(),),
            enzyme_associations=(_enzyme_association(), _enzyme_association()),
        )


def test_full_network_rejects_enzyme_association_with_undefined_reaction():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(),),
            reactions=(_reaction(),),
            enzyme_associations=(_enzyme_association(reaction_id="does-not-exist"),),
        )


def test_full_network_rejects_reaction_with_undefined_enzyme_association_id():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(),),
            reactions=(_reaction(enzyme_association_ids=("does-not-exist",)),),
        )


def test_full_network_carries_regulatory_interactions():
    network = FullNetwork(
        network_id="n1",
        name="test network",
        compartments=(_compartment(),),
        species=(_species(),),
        reactions=(_reaction(regulatory_interaction_ids=("reg1",)),),
        regulatory_interactions=(_regulation(),),
    )
    assert network.regulatory_interactions[0].id == "reg1"


def test_full_network_rejects_duplicate_regulatory_interaction_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            regulatory_interactions=(_regulation(), _regulation()),
        )


def test_full_network_rejects_regulation_targeting_undefined_reaction():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            regulatory_interactions=(_regulation(target_id="does-not-exist"),),
        )


def test_full_network_rejects_reaction_with_undefined_regulatory_interaction_id():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            compartments=(_compartment(),),
            species=(_species(),),
            reactions=(_reaction(regulatory_interaction_ids=("does-not-exist",)),),
        )


def test_full_network_never_validates_regulation_of_unresolvable_entity_type():
    """A 'protein' regulator/target has no first-class registry in FullNetwork -- never rejected."""
    network = FullNetwork(
        network_id="n1",
        name="test network",
        regulatory_interactions=(
            _regulation(
                regulator_type="protein",
                regulator_id="does-not-exist-anywhere",
                target_type="protein",
                target_id="also-does-not-exist",
            ),
        ),
    )
    assert network.regulatory_interactions[0].regulator_id == "does-not-exist-anywhere"


def test_full_network_carries_kinetic_measurements():
    network = FullNetwork(
        network_id="n1",
        name="test network",
        kinetic_measurements=(_kinetic_measurement(),),
    )
    assert network.kinetic_measurements[0].id == "km1"


def test_full_network_rejects_duplicate_kinetic_measurement_ids():
    with pytest.raises(ValueError):
        FullNetwork(
            network_id="n1",
            name="test network",
            kinetic_measurements=(_kinetic_measurement(), _kinetic_measurement()),
        )


def test_full_network_never_converts_kinetic_measurement_to_parameter():
    """Structural guard: FullNetwork carries CuratedKineticMeasurement verbatim, never a
    ParameterSpecification-shaped object."""
    network = FullNetwork(
        network_id="n1",
        name="test network",
        kinetic_measurements=(_kinetic_measurement(),),
    )
    assert isinstance(network.kinetic_measurements[0], CuratedKineticMeasurement)


# --- "Unresolved Kinetic Evidence Disclosure" increment: plural protein_ids ------------------
#
# Real Integration Pilot 1 Run 7/8, Pilot 2 Run 2: Agent 1's own real handoff can report
# that one kinetic measurement is applicable to more than one protein (yeast's real
# FAS1/FAS2 heterodimer, sharing one EC number). CuratedKineticMeasurement.protein_id's
# single-value shape could only ever record one of them; protein_ids is the new,
# authoritative, deterministic, complete representation.


def test_plural_protein_ids_are_preserved_verbatim():
    measurement = _kinetic_measurement(protein_id=None, protein_ids=("fas2", "fas1"))
    assert set(measurement.protein_ids) == {"fas1", "fas2"}


def test_protein_ids_are_deterministically_ordered_regardless_of_input_order():
    forward = _kinetic_measurement(protein_id=None, protein_ids=("fas2", "fas1"))
    backward = _kinetic_measurement(protein_id=None, protein_ids=("fas1", "fas2"))
    assert forward.protein_ids == backward.protein_ids == ("fas1", "fas2")


def test_protein_ids_never_arbitrarily_narrowed_to_one():
    measurement = _kinetic_measurement(protein_id=None, protein_ids=("fas1", "fas2"))
    assert len(measurement.protein_ids) == 2
    assert measurement.protein_id is None  # never arbitrarily set to either one


def test_single_protein_id_derives_protein_ids_automatically_backward_compatible():
    """Existing single-protein construction (protein_id set, protein_ids omitted
    entirely) needs no change and remains fully backward compatible."""
    measurement = _kinetic_measurement(protein_id="p1")
    assert measurement.protein_ids == ("p1",)


def test_protein_ids_defaults_to_empty_when_neither_supplied():
    measurement = _kinetic_measurement(protein_id=None)
    assert measurement.protein_ids == ()


def test_protein_ids_deduplicated_defensively():
    measurement = _kinetic_measurement(protein_id=None, protein_ids=("fas1", "fas1", "fas2"))
    assert measurement.protein_ids == ("fas1", "fas2")


def test_protein_ids_rejects_non_string_tuple():
    with pytest.raises(TypeError):
        _kinetic_measurement(protein_id=None, protein_ids=(1, 2))
