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
    FullNetwork,
    ParticipantRole,
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
