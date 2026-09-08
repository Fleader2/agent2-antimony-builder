"""Tests for the enzyme regulatory state handoff contracts (Agent 1.x Increment B).

Covers ``CuratedEnzymeState``, ``CuratedEnzymeModification``,
``CuratedAllostericInteraction``, ``CuratedEnzymeStateTransition``, and
``CuratedKineticMeasurement.enzyme_state_id``. No database, no HTTP, no
Agent 1 runtime dependency.
"""

from __future__ import annotations

import dataclasses
import inspect
from decimal import Decimal

import pytest

from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedAllostericInteraction,
    CuratedEnzymeModification,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
)
from app.agent2.version import AGENT1_HANDOFF_VERSION

# --- Immutability ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        CuratedEnzymeState,
        CuratedEnzymeModification,
        CuratedAllostericInteraction,
        CuratedEnzymeStateTransition,
    ],
)
def test_enzyme_state_family_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


# --- CuratedEnzymeState --------------------------------------------------------------------------


def test_curated_enzyme_state_builds_with_protein():
    state = CuratedEnzymeState(id="es-1", state_type="MODIFIED", protein_id="p-1")
    assert state.protein_id == "p-1"
    assert state.complex_id is None


def test_curated_enzyme_state_builds_with_complex():
    state = CuratedEnzymeState(id="es-1", state_type="BASE", complex_id="c-1")
    assert state.complex_id == "c-1"


def test_curated_enzyme_state_rejects_empty_id():
    with pytest.raises(ValueError):
        CuratedEnzymeState(id="", state_type="BASE", protein_id="p-1")


def test_curated_enzyme_state_rejects_empty_state_type():
    with pytest.raises(ValueError):
        CuratedEnzymeState(id="es-1", state_type="", protein_id="p-1")


def test_curated_enzyme_state_never_conflates_protein_and_state_identity():
    """The state's own id is independent of the protein/complex id it names."""
    state = CuratedEnzymeState(id="es-1", state_type="MODIFIED", protein_id="p-1")
    assert state.id != state.protein_id


# --- CuratedEnzymeModification -------------------------------------------------------------------


def test_curated_enzyme_modification_builds():
    modification = CuratedEnzymeModification(
        id="em-1",
        enzyme_state_id="es-1",
        modification_type="PHOSPHORYLATION",
        residue="Ser",
        residue_position=15,
    )
    assert modification.residue_position == 15


def test_curated_enzyme_modification_requires_enzyme_state_id():
    with pytest.raises(ValueError):
        CuratedEnzymeModification(
            id="em-1", enzyme_state_id="", modification_type="PHOSPHORYLATION"
        )


def test_curated_enzyme_modification_stoichiometry_must_be_decimal_not_float():
    with pytest.raises(TypeError):
        CuratedEnzymeModification(
            id="em-1",
            enzyme_state_id="es-1",
            modification_type="PHOSPHORYLATION",
            stoichiometry=1.5,  # type: ignore[arg-type]
        )


def test_curated_enzyme_modification_stoichiometry_accepts_decimal():
    modification = CuratedEnzymeModification(
        id="em-1",
        enzyme_state_id="es-1",
        modification_type="PHOSPHORYLATION",
        stoichiometry=Decimal("2"),
    )
    assert modification.stoichiometry == Decimal("2")


# --- CuratedAllostericInteraction -----------------------------------------------------------------


def test_curated_allosteric_interaction_builds():
    interaction = CuratedAllostericInteraction(
        id="ai-1", enzyme_state_id="es-1", ligand_compound_id="cmpd-1", effect="ACTIVATOR"
    )
    assert interaction.effect == "ACTIVATOR"


def test_curated_allosteric_interaction_requires_ligand_compound_id():
    with pytest.raises(ValueError):
        CuratedAllostericInteraction(
            id="ai-1", enzyme_state_id="es-1", ligand_compound_id="", effect="ACTIVATOR"
        )


def test_curated_allosteric_interaction_never_carries_a_numeric_kinetic_value():
    """Binding fact and kinetic consequence remain separate -- no value/unit field exists."""
    params = inspect.signature(CuratedAllostericInteraction).parameters
    for forbidden in ("value", "unit", "km", "kcat"):
        assert forbidden not in params


# --- CuratedEnzymeStateTransition -----------------------------------------------------------------


def test_curated_enzyme_state_transition_builds():
    transition = CuratedEnzymeStateTransition(
        id="est-1", from_state_id="es-1", to_state_id="es-2", transition_type="MODIFICATION"
    )
    assert transition.reaction_id is None


def test_curated_enzyme_state_transition_optional_reaction_link():
    transition = CuratedEnzymeStateTransition(
        id="est-1",
        from_state_id="es-1",
        to_state_id="es-2",
        transition_type="MODIFICATION",
        reaction_id="r-1",
    )
    assert transition.reaction_id == "r-1"


def test_curated_enzyme_state_transition_requires_from_and_to_state():
    with pytest.raises(ValueError):
        CuratedEnzymeStateTransition(
            id="est-1", from_state_id="", to_state_id="es-2", transition_type="MODIFICATION"
        )


# --- CuratedKineticMeasurement.enzyme_state_id (Agent 1.x Increment B) ----------------------------


def test_curated_kinetic_measurement_enzyme_state_id_defaults_to_none():
    measurement = CuratedKineticMeasurement(
        id="km-1", parameter_type="KM", value=Decimal("0.5"), unit="mM"
    )
    assert measurement.enzyme_state_id is None


def test_curated_kinetic_measurement_preserves_enzyme_state_id():
    measurement = CuratedKineticMeasurement(
        id="km-1",
        parameter_type="KCAT",
        value=Decimal("32.0"),
        unit="1/s",
        enzyme_state_id="es-1",
    )
    assert measurement.enzyme_state_id == "es-1"


def test_state_specific_measurement_never_applies_to_other_states():
    """Two measurements naming different states are independent objects -- no shared identity."""
    measurement_a = CuratedKineticMeasurement(
        id="km-a", parameter_type="KCAT", value=Decimal("4.5"), unit="1/s", enzyme_state_id="es-1"
    )
    measurement_b = CuratedKineticMeasurement(
        id="km-b", parameter_type="KCAT", value=Decimal("32.0"), unit="1/s", enzyme_state_id="es-2"
    )
    assert measurement_a.enzyme_state_id != measurement_b.enzyme_state_id
    assert measurement_a.value != measurement_b.value


# --- Agent1CuratedKnowledgeViewContract -----------------------------------------------------------


def test_handoff_contract_carries_enzyme_state_family():
    view = Agent1CuratedKnowledgeViewContract(
        contract_version=AGENT1_HANDOFF_VERSION,
        enzyme_states=(CuratedEnzymeState(id="es-1", state_type="BASE", protein_id="p-1"),),
        enzyme_modifications=(
            CuratedEnzymeModification(
                id="em-1", enzyme_state_id="es-1", modification_type="PHOSPHORYLATION"
            ),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="ai-1", enzyme_state_id="es-1", ligand_compound_id="cmpd-1", effect="ACTIVATOR"
            ),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="est-1", from_state_id="es-1", to_state_id="es-2", transition_type="MODIFICATION"
            ),
        ),
    )
    assert view.enzyme_states[0].id == "es-1"
    assert view.enzyme_modifications[0].id == "em-1"
    assert view.allosteric_interactions[0].id == "ai-1"
    assert view.enzyme_state_transitions[0].id == "est-1"


def test_handoff_contract_enzyme_state_family_defaults_empty():
    view = Agent1CuratedKnowledgeViewContract(contract_version=AGENT1_HANDOFF_VERSION)
    assert view.enzyme_states == ()
    assert view.enzyme_modifications == ()
    assert view.allosteric_interactions == ()
    assert view.enzyme_state_transitions == ()


def test_handoff_version_updated_to_one_dot_two():
    assert AGENT1_HANDOFF_VERSION == "1.2"


# --- Scope safety: no parameter mapping, kinetic-law assignment, or model semantics ---------------


def test_enzyme_state_types_never_map_to_parameter_specification():
    """No field on any Curated* enzyme-state type names a ParameterSpecification/kinetic law."""
    for cls in (
        CuratedEnzymeState,
        CuratedEnzymeModification,
        CuratedAllostericInteraction,
        CuratedEnzymeStateTransition,
    ):
        field_names = {f.name for f in dataclasses.fields(cls)}
        for forbidden in (
            "parameter_id",
            "kinetic_law_id",
            "species_id",
            "antimony",
            "boundary_id",
            "module_id",
        ):
            assert forbidden not in field_names
