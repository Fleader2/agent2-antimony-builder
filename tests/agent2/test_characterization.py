"""Tests for Reaction and Enzyme-State Characterization (Increment 3):
``app.agent2.characterization``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, assembles it
into a ``FullNetwork`` via ``assemble_full_network``, then calls
``characterize_full_network`` on the result -- no test constructs a
``FullNetwork``/``NetworkCharacterization`` by hand, matching
``tests/agent2/test_network_assembly.py``'s own convention.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from app.agent2.characterization import (
    CharacterizationFlag,
    NetworkCharacterization,
    ReactionClass,
    UnresolvedFeature,
    characterize_full_network,
)
from app.agent2.network import assemble_full_network
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
)

# --- Fixtures --------------------------------------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.2"} | overrides
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
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(
            _participant(role="REACTANT"),
            _participant(role="PRODUCT", compound_id="glc"),
        ),
    )


def _characterize(handoff: Agent1CuratedKnowledgeViewContract) -> NetworkCharacterization:
    return characterize_full_network(assemble_full_network(handoff))


def _reaction_characterization(handoff, reaction_id: str = "r1"):
    characterization = _characterize(handoff)
    (match,) = [
        rc for rc in characterization.reaction_characterizations if rc.reaction_id == reaction_id
    ]
    return match


# --- ReactionCharacterization basics (Step 36) ------------------------------------------------


def test_empty_network_characterizes_to_empty_tuples():
    characterization = _characterize(_handoff())
    assert characterization.reaction_characterizations == ()
    assert characterization.enzyme_state_characterizations == ()


def test_noncatalyzed_reaction_has_no_catalyst_information():
    rc = _reaction_characterization(_simple_reaction_handoff())
    assert rc.catalyst_association_ids == ()
    assert CharacterizationFlag.HAS_CATALYST not in rc.characterization_flags
    assert UnresolvedFeature.NO_CATALYST_INFORMATION in rc.unresolved_features
    assert ReactionClass.UNKNOWN in rc.reaction_classes


def test_enzymatic_reaction_classified_enzymatic():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    rc = _reaction_characterization(handoff)
    assert ReactionClass.ENZYMATIC in rc.reaction_classes
    assert CharacterizationFlag.HAS_CATALYST in rc.characterization_flags
    assert rc.catalytic_protein_ids == ("p1",)


def test_multiple_catalysts_flagged():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id="p2"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert len(rc.catalyst_association_ids) == 2
    assert CharacterizationFlag.MULTIPLE_CATALYSTS in rc.characterization_flags


def test_protein_general_catalyst_bucketed_correctly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    rc = _reaction_characterization(handoff)
    assert rc.catalytic_protein_ids == ("p1",)
    assert rc.catalytic_complex_ids == ()
    assert rc.catalytic_enzyme_state_ids == ()
    assert CharacterizationFlag.STATE_SPECIFIC_CATALYSIS not in rc.characterization_flags


def test_complex_general_catalyst_bucketed_correctly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(_enzyme_association(protein_id=None, complex_id="cx1"),),
    )
    rc = _reaction_characterization(handoff)
    assert rc.catalytic_complex_ids == ("cx1",)
    assert rc.catalytic_protein_ids == ()
    assert rc.catalytic_enzyme_state_ids == ()


def test_state_specific_catalyst_bucketed_correctly():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.catalytic_enzyme_state_ids == ("es1",)
    assert rc.catalytic_protein_ids == ()
    assert CharacterizationFlag.STATE_SPECIFIC_CATALYSIS in rc.characterization_flags


def test_reversible_true_preserved_and_flagged():
    rc = _reaction_characterization(_simple_reaction_handoff(reversible=True))
    assert rc.reversible is True
    assert CharacterizationFlag.REVERSIBILITY_KNOWN in rc.characterization_flags
    assert CharacterizationFlag.REVERSIBILITY_UNKNOWN not in rc.characterization_flags


def test_reversible_false_preserved_and_flagged():
    rc = _reaction_characterization(_simple_reaction_handoff(reversible=False))
    assert rc.reversible is False
    assert CharacterizationFlag.REVERSIBILITY_KNOWN in rc.characterization_flags


def test_reversible_none_flagged_unknown():
    rc = _reaction_characterization(_simple_reaction_handoff(reversible=None))
    assert rc.reversible is None
    assert CharacterizationFlag.REVERSIBILITY_UNKNOWN in rc.characterization_flags
    assert UnresolvedFeature.REVERSIBILITY_UNKNOWN in rc.unresolved_features


def test_participant_roles_preserved_and_ordered():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="atp")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="MODIFIER", compound_id="atp"),
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="PRODUCT", compound_id="glc", compartment_id="cyto"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert len(rc.participant_species_ids) == 3
    assert rc.participant_species_ids[0] == rc.modifier_species_ids[0]
    assert rc.reactant_species_ids and rc.product_species_ids
    assert CharacterizationFlag.PARTICIPANT_MODIFIERS_PRESENT in rc.characterization_flags


def test_multiple_compartments_flagged():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(), _compartment(id="mito", name="mitochondrion")),
            compounds=(_compound(),),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compartment_id="cyto"),
            _participant(role="PRODUCT", compartment_id="mito"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert CharacterizationFlag.MULTIPLE_COMPARTMENTS in rc.characterization_flags


# --- Enzyme regulatory states (Step 37) ---------------------------------------------------------


def test_phosphorylated_state_modification_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        enzyme_modifications=(_enzyme_modification(modification_type="PHOSPHORYLATION"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert CharacterizationFlag.HAS_MODIFIED_ENZYME_STATE in rc.characterization_flags
    characterization = _characterize(handoff)
    (esc,) = characterization.enzyme_state_characterizations
    assert esc.modification_ids == ("mod1",)


def test_acetylated_state_modification_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        enzyme_modifications=(_enzyme_modification(modification_type="ACETYLATION"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert CharacterizationFlag.HAS_MODIFIED_ENZYME_STATE in rc.characterization_flags


def test_cysteinylated_state_modification_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        enzyme_modifications=(_enzyme_modification(modification_type="CYSTEINYLATION"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert CharacterizationFlag.HAS_MODIFIED_ENZYME_STATE in rc.characterization_flags


def test_multiple_modifications_on_one_state_all_preserved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        enzyme_modifications=(
            _enzyme_modification(id="mod1", modification_type="PHOSPHORYLATION"),
            _enzyme_modification(id="mod2", modification_type="ACETYLATION", residue="Lys44"),
        ),
    )
    characterization = _characterize(handoff)
    (esc,) = characterization.enzyme_state_characterizations
    assert esc.modification_ids == ("mod1", "mod2")


def test_allosteric_activator_state_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        allosteric_interactions=(_allosteric_interaction(effect="ACTIVATOR"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.allosteric_interaction_ids == ("allo1",)
    assert CharacterizationFlag.HAS_ALLOSTERY in rc.characterization_flags
    network = assemble_full_network(handoff)
    assert network.allosteric_interactions[0].effect == "ACTIVATOR"


def test_allosteric_inhibitor_state_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        allosteric_interactions=(_allosteric_interaction(effect="INHIBITOR"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.allosteric_interaction_ids == ("allo1",)
    network = assemble_full_network(handoff)
    assert network.allosteric_interactions[0].effect == "INHIBITOR"


def test_linked_state_transition_characterized_on_reaction_and_state():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_state_transitions=(_enzyme_state_transition(reaction_id="r1"),),
    )
    rc = _reaction_characterization(handoff)
    assert rc.enzyme_state_transition_ids == ("trans1",)
    assert CharacterizationFlag.HAS_STATE_TRANSITION in rc.characterization_flags
    assert ReactionClass.STATE_TRANSITION in rc.reaction_classes
    characterization = _characterize(handoff)
    transition_owning_states = [
        esc for esc in characterization.enzyme_state_characterizations if esc.transition_ids
    ]
    assert len(transition_owning_states) == 2


def test_unlinked_state_transition_not_classified_as_reaction_state_transition():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_state_transitions=(_enzyme_state_transition(reaction_id=None),),
    )
    rc = _reaction_characterization(handoff)
    assert rc.enzyme_state_transition_ids == ()
    assert ReactionClass.STATE_TRANSITION not in rc.reaction_classes


def test_enzyme_state_never_conflated_with_parent_protein():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es1", protein_id="p1"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.catalytic_protein_ids == ()
    assert rc.catalytic_enzyme_state_ids == ("es1",)
    characterization = _characterize(handoff)
    (esc,) = characterization.enzyme_state_characterizations
    assert esc.enzyme_state_id == "es1"
    assert esc.parent_protein_id == "p1"
    assert esc.enzyme_state_id != esc.parent_protein_id


# --- Kinetic evidence (Step 38) ------------------------------------------------------------------


def test_no_kinetic_measurements_flagged_unresolved():
    rc = _reaction_characterization(_simple_reaction_handoff())
    assert rc.kinetic_measurement_ids == ()
    assert UnresolvedFeature.NO_KINETIC_MEASUREMENTS in rc.unresolved_features
    assert UnresolvedFeature.NO_STATE_SPECIFIC_KINETICS in rc.unresolved_features


def test_one_general_measurement_characterized():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), kinetic_measurements=(_kinetic_measurement(),)
    )
    rc = _reaction_characterization(handoff)
    assert rc.kinetic_measurement_ids == ("km1",)
    assert CharacterizationFlag.HAS_KINETIC_MEASUREMENTS in rc.characterization_flags
    assert UnresolvedFeature.NO_KINETIC_MEASUREMENTS not in rc.unresolved_features


def test_multiple_general_measurements_all_preserved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", value=Decimal("0.5")),
            _kinetic_measurement(id="km2", value=Decimal("1.5")),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.kinetic_measurement_ids == ("km1", "km2")


def test_state_specific_measurement_characterized_separately():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        kinetic_measurements=(_kinetic_measurement(enzyme_state_id="es1"),),
    )
    rc = _reaction_characterization(handoff)
    assert rc.kinetic_measurement_ids == ()
    assert rc.state_specific_kinetic_measurement_ids == ("km1",)
    assert CharacterizationFlag.HAS_STATE_SPECIFIC_KINETICS in rc.characterization_flags


def test_general_and_state_specific_measurements_coexist_independently():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(id="km_general"),
            _kinetic_measurement(id="km_state", enzyme_state_id="es1"),
        ),
    )
    rc = _reaction_characterization(handoff)
    assert rc.kinetic_measurement_ids == ("km_general",)
    assert rc.state_specific_kinetic_measurement_ids == ("km_state",)


def test_reported_rate_law_present_flagged():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(_kinetic_measurement(reported_rate_law="v = kcat*E*S"),),
    )
    rc = _reaction_characterization(handoff)
    assert rc.reported_rate_law_measurement_ids == ("km1",)
    assert CharacterizationFlag.HAS_REPORTED_RATE_LAW in rc.characterization_flags
    assert UnresolvedFeature.NO_REPORTED_RATE_LAW not in rc.unresolved_features


def test_reported_rate_law_absent_unresolved():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), kinetic_measurements=(_kinetic_measurement(),)
    )
    rc = _reaction_characterization(handoff)
    assert rc.reported_rate_law_measurement_ids == ()
    assert UnresolvedFeature.NO_REPORTED_RATE_LAW in rc.unresolved_features


def test_kinetic_measurement_values_never_transformed():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        kinetic_measurements=(_kinetic_measurement(value=Decimal("0.123456"), unit="uM"),),
    )
    network = assemble_full_network(handoff)
    characterize_full_network(network)
    assert network.kinetic_measurements[0].value == Decimal("0.123456")
    assert network.kinetic_measurements[0].unit == "uM"


# --- Uncertainty (Step 39) -----------------------------------------------------------------------


def test_catalyst_unknown_never_asserted_as_no_catalyst_exists():
    rc = _reaction_characterization(_simple_reaction_handoff())
    assert UnresolvedFeature.NO_CATALYST_INFORMATION.value == "NO_CATALYST_INFORMATION"
    assert "NO_CATALYST_INFORMATION" in [f.value for f in rc.unresolved_features]


def test_kinetics_unavailable_reported_as_unresolved_not_absent():
    rc = _reaction_characterization(_simple_reaction_handoff())
    assert UnresolvedFeature.NO_KINETIC_MEASUREMENTS in rc.unresolved_features


def test_catalyst_state_unspecified_when_general_catalyst_has_known_states():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(protein_id="p1"),),
        reaction_enzyme_associations=(_enzyme_association(protein_id="p1"),),
    )
    rc = _reaction_characterization(handoff)
    assert UnresolvedFeature.CATALYST_STATE_UNSPECIFIED in rc.unresolved_features
    assert UnresolvedFeature.ENZYME_STATE_CONTEXT_INCOMPLETE in rc.unresolved_features


def test_catalyst_state_unspecified_absent_when_no_known_states_exist():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), reaction_enzyme_associations=(_enzyme_association(),)
    )
    rc = _reaction_characterization(handoff)
    assert UnresolvedFeature.CATALYST_STATE_UNSPECIFIED not in rc.unresolved_features


def test_reversibility_unknown_never_guessed():
    rc = _reaction_characterization(_simple_reaction_handoff(reversible=None))
    assert UnresolvedFeature.REVERSIBILITY_UNKNOWN in rc.unresolved_features
    assert rc.reversible is None


def test_regulation_context_always_incomplete_even_with_curated_regulation():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(), regulatory_interactions=(_regulation(),)
    )
    rc = _reaction_characterization(handoff)
    assert rc.regulation_ids == ("reg1",)
    assert CharacterizationFlag.HAS_REGULATION in rc.characterization_flags
    assert UnresolvedFeature.REGULATION_CONTEXT_INCOMPLETE in rc.unresolved_features


def test_regulation_context_incomplete_even_with_no_curated_regulation():
    rc = _reaction_characterization(_simple_reaction_handoff())
    assert rc.regulation_ids == ()
    assert UnresolvedFeature.REGULATION_CONTEXT_INCOMPLETE in rc.unresolved_features


def test_no_reason_code_ever_asserts_regulation_does_not_exist():
    for feature in UnresolvedFeature:
        assert "NOT_REGULATED" not in feature.value
        assert "NO_REGULATION" not in feature.value
    characterization = _characterize(_simple_reaction_handoff())
    for phrase in ("no regulation exists", "not regulated", "does not exist biologically"):
        assert phrase not in " ".join(characterization.assumptions).lower()


# --- Deterministic output (Step 41) ---------------------------------------------------------------


def test_reordered_order_insensitive_associations_characterize_identically():
    handoff_a = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id="p2"),
        ),
    )
    handoff_b = dataclasses.replace(
        _simple_reaction_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p2"),
            _enzyme_association(protein_id="p1"),
        ),
    )
    rc_a = _reaction_characterization(handoff_a)
    rc_b = _reaction_characterization(handoff_b)
    assert rc_a.catalytic_protein_ids == rc_b.catalytic_protein_ids


def test_participant_order_never_reordered():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="pyr")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="PRODUCT", compound_id="pyr"),
            _participant(role="REACTANT", compound_id="glc"),
        ),
    )
    rc = _reaction_characterization(handoff)
    species_by_compound = {
        s.source_compound_id: s.species_id for s in assemble_full_network(handoff).species
    }
    assert rc.participant_species_ids == (
        species_by_compound["pyr"],
        species_by_compound["glc"],
    )


def test_characterize_full_network_is_deterministic():
    handoff = dataclasses.replace(
        _simple_reaction_handoff(),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_modifications=(_enzyme_modification(),),
        allosteric_interactions=(_allosteric_interaction(),),
        enzyme_state_transitions=(_enzyme_state_transition(reaction_id="r1"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        kinetic_measurements=(_kinetic_measurement(enzyme_state_id="es1"),),
        regulatory_interactions=(_regulation(),),
    )
    network = assemble_full_network(handoff)
    first = characterize_full_network(network)
    second = characterize_full_network(network)
    assert first == second


def test_reaction_and_enzyme_state_characterizations_sorted_by_id():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(),),
            reactions=(_reaction(id="r2"), _reaction(id="r1")),
        ),
        reaction_participants=(
            _participant(reaction_id="r2"),
            _participant(reaction_id="r1"),
        ),
        enzyme_states=(_enzyme_state(id="es2"), _enzyme_state(id="es1")),
    )
    characterization = _characterize(handoff)
    assert [rc.reaction_id for rc in characterization.reaction_characterizations] == ["r1", "r2"]
    assert [
        esc.enzyme_state_id for esc in characterization.enzyme_state_characterizations
    ] == ["es1", "es2"]
