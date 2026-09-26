"""Tests for Kinetic-Law Assignment (Increment 4): ``app.agent2.kinetics``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, assembles it
into a ``FullNetwork``, characterizes it, then calls
``assign_kinetic_laws(characterization, network)`` on the result -- no
test constructs a ``KineticLawAssignmentSet`` by hand, matching
``tests/agent2/test_characterization.py``'s own convention.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import (
    KineticLawAssignmentSet,
    KineticLawAssignmentSource,
    KineticLawReasonCode,
    assign_kinetic_laws,
)
from app.agent2.kinetics.errors import KineticLawReferenceError
from app.agent2.network import assemble_full_network
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    KineticLawType,
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


def _enzyme_state_transition(**overrides) -> CuratedEnzymeStateTransition:
    merged = {
        "id": "trans1",
        "from_state_id": "es0",
        "to_state_id": "es1",
        "transition_type": "PHOSPHORYLATION",
    } | overrides
    return CuratedEnzymeStateTransition(**merged)


def _one_substrate_one_product_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
    """One compartment, glc->g6p, one reaction, enzymatic-eligible for Michaelis-Menten."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(), _compound(id="g6p", name="glucose-6-phosphate")),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
    )


def _assign(handoff: Agent1CuratedKnowledgeViewContract) -> KineticLawAssignmentSet:
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    return assign_kinetic_laws(characterization, network)


def _only(assignment_set: KineticLawAssignmentSet):
    (assignment,) = assignment_set.assignments
    return assignment


def _by_context(assignment_set: KineticLawAssignmentSet, **context):
    for assignment in assignment_set.assignments:
        if all(getattr(assignment, field) == value for field, value in context.items()):
            return assignment
    raise AssertionError(f"no assignment matches context {context!r}")


# --- Assignment source (Step 36) ------------------------------------------------------------


def test_assignment_source_vocabulary_is_exact():
    assert {member.value for member in KineticLawAssignmentSource} == {
        "CURATED_REPORTED",
        "DETERMINISTIC_STRUCTURAL",
        "HEURISTIC",
        "UNASSIGNED",
    }


def test_assignment_source_is_immutable_enum_member():
    with pytest.raises(AttributeError):
        KineticLawAssignmentSource.HEURISTIC.value = "OTHER"


# --- Curated reported laws (Step 37) ---------------------------------------------------------


def test_reported_mass_action_like_law_classified():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(_kinetic_measurement(reported_rate_law="k1 * glc"),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert assignment.reported_rate_law_text == "k1 * glc"
    assert assignment.source_measurement_ids == ("km1",)


def test_reported_michaelis_menten_like_law_classified():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(reported_rate_law="Michaelis-Menten: Vmax*S/(Km+S)"),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert assignment.reported_rate_law_text == "Michaelis-Menten: Vmax*S/(Km+S)"


def test_unclassifiable_reported_law_becomes_custom():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(_kinetic_measurement(reported_rate_law="Vmax*S/(Km+S)"),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.CUSTOM
    assert assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert assignment.reported_rate_law_text == "Vmax*S/(Km+S)"
    assert KineticLawReasonCode.CURATED_RATE_LAW_CUSTOM in assignment.reason_codes


def test_source_measurement_ids_preserved_exactly():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(_kinetic_measurement(id="km_x", reported_rate_law="k1 * glc"),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.source_measurement_ids == ("km_x",)


def test_heuristic_never_overrides_curated_law():
    """Even though this reaction is MM-eligible, a curated law must win."""
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(_kinetic_measurement(reported_rate_law="k1 * glc"),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN


# --- Multiple reported laws (Step 38) --------------------------------------------------------


def test_identical_reported_laws_across_measurements_share_one_assignment():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", reported_rate_law="k1 * glc"),
            _kinetic_measurement(id="km2", reported_rate_law="  K1   *   GLC  "),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.source_measurement_ids == ("km1", "km2")


def test_materially_distinct_reported_laws_left_unassigned():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", reported_rate_law="k1 * glc"),
            _kinetic_measurement(id="km2", reported_rate_law="k2 * glc * g6p"),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.UNASSIGNED
    assert assignment.assignment_source is KineticLawAssignmentSource.UNASSIGNED
    assert KineticLawReasonCode.MULTIPLE_DISTINCT_REPORTED_RATE_LAWS in assignment.reason_codes
    assert assignment.source_measurement_ids == ("km1", "km2")
    assert assignment.reported_rate_law_text is None


def test_state_specific_reported_laws_never_globalized():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(),),
            reactions=(_reaction(),),
            reaction_participants=(_participant(),),
        ),
        enzyme_states=(_enzyme_state(id="e"), _enzyme_state(id="ep")),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="e"),
            _enzyme_association(protein_id=None, enzyme_state_id="ep"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(id="km_ep", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
        ),
    )
    assignments = _assign(handoff)
    e_assignment = _by_context(assignments, enzyme_state_id="e")
    ep_assignment = _by_context(assignments, enzyme_state_id="ep")
    assert ep_assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert not ep_assignment.is_tentative
    # E has no law of its own -- it gets its own tentative default, never EP's curated law.
    assert e_assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert e_assignment.is_tentative
    assert e_assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert e_assignment.reported_rate_law_text is None
    assert e_assignment.source_measurement_ids == ()


def test_no_arbitrary_winner_when_reported_laws_conflict():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", reported_rate_law="alpha form"),
            _kinetic_measurement(id="km2", reported_rate_law="beta form"),
            _kinetic_measurement(id="km3", reported_rate_law="gamma form"),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.UNASSIGNED
    assert assignment.source_measurement_ids == ("km1", "km2", "km3")


# --- Deterministic structural rules (Step 39) ------------------------------------------------


def _bare_state_transition_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(_participant(),),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_state_transitions=(_enzyme_state_transition(reaction_id="r1"),),
    )


def test_simple_state_transition_assigned_mass_action():
    assignment = _only(_assign(_bare_state_transition_handoff()))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL
    assert assignment.reason_codes == (KineticLawReasonCode.SIMPLE_ELEMENTARY_TRANSITION,)


def test_reversible_elementary_transition_assigned_reversible_mass_action():
    assignment = _only(_assign(_bare_state_transition_handoff(reversible=True)))
    assert assignment.kinetic_law_type is KineticLawType.REVERSIBLE_MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL
    assert assignment.reason_codes == (
        KineticLawReasonCode.SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION,
    )


def test_structural_rule_does_not_apply_when_enzymatic():
    """The deterministic structural rule and the tentative default are mutually exclusive by
    construction (structural requires non-enzymatic; tentative requires enzymatic) -- an
    enzymatic state-transition reaction falls through to the tentative default instead."""
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        reaction_enzyme_associations=(_enzyme_association(),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.assignment_source is not KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.is_tentative


def test_structural_rule_does_not_apply_without_state_transition():
    handoff = _one_substrate_one_product_handoff()
    handoff = dataclasses.replace(handoff, reaction_enzyme_associations=())
    assignment = _only(_assign(handoff))
    assert assignment.assignment_source is not KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL


# --- Heuristic rules (Step 40) ----------------------------------------------------------------


def test_eligible_simple_enzymatic_reaction_gets_michaelis_menten():
    assignment = _only(_assign(_one_substrate_one_product_handoff()))
    assert assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.reason_codes == (KineticLawReasonCode.ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT,)
    # the conservative, more-justified heuristic is never tentative.
    assert not assignment.is_tentative
    assert assignment.unresolved_reasons == ()


def test_multiple_substrates_not_eligible_for_michaelis_menten():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="atp"), _compound(id="g6p")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="REACTANT", compound_id="atp"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    # falls to the tentative mass-action default, since nothing else disqualifies it
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.is_tentative
    assert KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in assignment.reason_codes


def test_allostery_blocks_automatic_michaelis_menten_eligibility():
    from app.agent2.types import CuratedAllostericInteraction

    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="g6p")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="allo1", enzyme_state_id="es1", ligand_compound_id="glc", effect="ACTIVATOR"
            ),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    # allostery no longer forces UNASSIGNED -- a tentative default keeps the model runnable.
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.is_tentative
    assert (
        KineticLawReasonCode.REGULATORY_KINETIC_EFFECT_NOT_MODELED in assignment.unresolved_reasons
    )
    assert KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED in assignment.unresolved_reasons


def test_multiple_catalytic_states_not_automatically_eligible():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="g6p")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        enzyme_states=(_enzyme_state(id="e"), _enzyme_state(id="ep")),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="e"),
            _enzyme_association(protein_id=None, enzyme_state_id="ep"),
        ),
    )
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 2
    for assignment in assignments.assignments:
        # not automatically MICHAELIS_MENTEN -- but a tentative default keeps each state
        # independently runnable rather than forcing a global UNASSIGNED.
        assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
        assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
        assert assignment.is_tentative
        assert KineticLawReasonCode.MULTIPLE_CATALYTIC_STATES in assignment.unresolved_reasons
    assert {a.enzyme_state_id for a in assignments.assignments} == {"e", "ep"}


def test_reversibility_conflict_not_eligible_for_michaelis_menten():
    """Reversible=True disqualifies MM, but still gets a tentative MASS_ACTION default --
    never REVERSIBLE_MASS_ACTION (that stays reserved for the structural rule, docs/07 sec 10)."""
    handoff = _one_substrate_one_product_handoff(reversible=True)
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.kinetic_law_type is not KineticLawType.REVERSIBLE_MASS_ACTION
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.is_tentative
    assert "reverse direction" in assignment.explanation


def test_hill_never_assigned_heuristically_allostery_leaves_unassigned():
    from app.agent2.types import CuratedAllostericInteraction

    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),), compounds=(_compound(),), reactions=(_reaction(),)
        ),
        reaction_participants=(_participant(),),
        enzyme_states=(_enzyme_state(),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="allo1", enzyme_state_id="es1", ligand_compound_id="glc", effect="ACTIVATOR"
            ),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.HILL
    # allostery is never converted into Hill kinetics -- the tentative default fires instead.
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.is_tentative
    assert (
        KineticLawReasonCode.REGULATORY_KINETIC_EFFECT_NOT_MODELED in assignment.unresolved_reasons
    )


# --- UNASSIGNED (Step 41) ---------------------------------------------------------------------


def test_unassigned_when_no_catalyst_no_rule_no_heuristic():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(), reaction_enzyme_associations=()
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.UNASSIGNED
    assert KineticLawReasonCode.INSUFFICIENT_CURATED_CONTEXT in assignment.unresolved_reasons


def test_unassigned_when_no_deterministic_rule_applies():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(), reaction_enzyme_associations=()
    )
    assignment = _only(_assign(handoff))
    assert assignment.assignment_source is KineticLawAssignmentSource.UNASSIGNED


def test_unassigned_on_conflicting_reported_laws_is_normal_output():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", reported_rate_law="k1 * glc"),
            _kinetic_measurement(id="km2", reported_rate_law="k2 * glc * g6p"),
        ),
    )
    assignment_set = _assign(handoff)
    assert isinstance(assignment_set, KineticLawAssignmentSet)
    assert _only(assignment_set).kinetic_law_type is KineticLawType.UNASSIGNED


def test_unassigned_on_conflicting_reported_laws_for_one_state_never_overridden_by_tentative():
    """A conflict on one specific catalytic state's own curated evidence stays UNASSIGNED for
    that state -- the tentative default never overrides a genuine curated contradiction."""
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),), compounds=(_compound(),), reactions=(_reaction(),)
        ),
        reaction_participants=(_participant(),),
        enzyme_states=(_enzyme_state(id="e"), _enzyme_state(id="ep")),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="e"),
            _enzyme_association(protein_id=None, enzyme_state_id="ep"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
            _kinetic_measurement(
                id="km2", enzyme_state_id="ep", reported_rate_law="k2 * glc * glc"
            ),
        ),
    )
    assignments = _assign(handoff)
    e_assignment = _by_context(assignments, enzyme_state_id="e")
    ep_assignment = _by_context(assignments, enzyme_state_id="ep")
    assert ep_assignment.kinetic_law_type is KineticLawType.UNASSIGNED
    assert (
        KineticLawReasonCode.MULTIPLE_DISTINCT_REPORTED_RATE_LAWS in ep_assignment.reason_codes
    )
    # E has no conflict of its own -- it still gets its own independent tentative default.
    assert e_assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert e_assignment.is_tentative


def test_unassigned_on_insufficient_context_is_not_an_error():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(),),
        reaction_participants=(_participant(),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.UNASSIGNED
    assert assignment.reason_codes


# --- State specificity (Step 42) --------------------------------------------------------------


def _e_and_ep_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(),),
        "reactions": (_reaction(),),
        "reaction_participants": (_participant(),),
        "enzyme_states": (_enzyme_state(id="e"), _enzyme_state(id="ep")),
        "reaction_enzyme_associations": (
            _enzyme_association(protein_id=None, enzyme_state_id="e"),
            _enzyme_association(protein_id=None, enzyme_state_id="ep"),
        ),
    } | overrides
    return _handoff(**merged)


def test_e_and_ep_remain_distinct_assignments():
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km_ep", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
        )
    )
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 2
    ids = {(a.enzyme_state_id) for a in assignments.assignments}
    assert ids == {"e", "ep"}


def test_law_reported_only_for_ep_never_applies_to_e():
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km_ep", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
        )
    )
    assignments = _assign(handoff)
    e_assignment = _by_context(assignments, enzyme_state_id="e")
    assert e_assignment.reported_rate_law_text is None
    assert e_assignment.assignment_source is not KineticLawAssignmentSource.CURATED_REPORTED


def test_distinct_states_can_have_distinct_assignment_sources():
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km_ep", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
        )
    )
    assignments = _assign(handoff)
    e_assignment = _by_context(assignments, enzyme_state_id="e")
    ep_assignment = _by_context(assignments, enzyme_state_id="ep")
    assert e_assignment.assignment_source != ep_assignment.assignment_source


def test_state_specific_measurement_does_not_globalize_law():
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km_ep", enzyme_state_id="ep", reported_rate_law="k1 * glc"),
        )
    )
    assignments = _assign(handoff)
    for assignment in assignments.assignments:
        if assignment.enzyme_state_id == "e":
            assert assignment.source_measurement_ids == ()


# --- Multiple catalysts (Step 43) --------------------------------------------------------------


def _two_isozyme_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(),),
        "reactions": (_reaction(),),
        "reaction_participants": (_participant(),),
        "reaction_enzyme_associations": (
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id="p2"),
        ),
    } | overrides
    return _handoff(**merged)


def test_two_isozymes_same_law_context_collapse_to_one_assignment():
    handoff = _two_isozyme_handoff()
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 1
    assert assignments.assignments[0].protein_id is None


def test_two_isozymes_different_reported_laws_stay_separate():
    handoff = _two_isozyme_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km1", protein_id="p1", reported_rate_law="k1 * glc"),
            _kinetic_measurement(id="km2", protein_id="p2", reported_rate_law="k2 * glc * glc"),
        )
    )
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 2
    p1_assignment = _by_context(assignments, protein_id="p1")
    p2_assignment = _by_context(assignments, protein_id="p2")
    assert p1_assignment.reported_rate_law_text != p2_assignment.reported_rate_law_text


def test_protein_general_and_state_specific_catalyst_kept_separate():
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),), compounds=(_compound(),), reactions=(_reaction(),)
        ),
        reaction_participants=(_participant(),),
        enzyme_states=(_enzyme_state(id="es1", protein_id="p2"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p1"),
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
    )
    assignments = _assign(handoff)
    # catalytic_enzyme_state_ids non-empty on the ReactionCharacterization means the whole
    # reaction is targeted per-state; the protein-general association is not separately
    # targeted in that case (see docs/07 sec 12) -- exactly one context: the state.
    assert {a.enzyme_state_id for a in assignments.assignments} == {"es1"}


def test_no_forced_global_collapse_when_isozyme_evidence_differs():
    handoff = _two_isozyme_handoff(
        kinetic_measurements=(
            _kinetic_measurement(id="km1", protein_id="p1", reported_rate_law="k1 * glc"),
        )
    )
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 2
    p1_assignment = _by_context(assignments, protein_id="p1")
    p2_assignment = _by_context(assignments, protein_id="p2")
    assert p1_assignment.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert p2_assignment.assignment_source is not KineticLawAssignmentSource.CURATED_REPORTED


# --- Determinism (Step 46) ---------------------------------------------------------------------


def test_assign_kinetic_laws_is_deterministic():
    handoff = _one_substrate_one_product_handoff()
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    first = assign_kinetic_laws(characterization, network)
    second = assign_kinetic_laws(characterization, network)
    assert first == second


def test_reordered_isozyme_associations_produce_equivalent_assignments():
    handoff_a = _two_isozyme_handoff()
    handoff_b = dataclasses.replace(
        handoff_a,
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p2"),
            _enzyme_association(protein_id="p1"),
        ),
    )
    laws_a = _assign(handoff_a)
    laws_b = _assign(handoff_b)
    assert {a.protein_id for a in laws_a.assignments} == {a.protein_id for a in laws_b.assignments}
    assert len(laws_a.assignments) == len(laws_b.assignments) == 1


# --- Network-id mismatch defensive check --------------------------------------------------------


def test_network_id_mismatch_raises_reference_error():
    handoff_a = _one_substrate_one_product_handoff()
    handoff_b = dataclasses.replace(
        handoff_a, organism_id="different-organism-for-a-new-network-id"
    )
    network_a = assemble_full_network(handoff_a)
    network_b = assemble_full_network(handoff_b)
    characterization_a = characterize_full_network(network_a)
    if network_a.network_id == network_b.network_id:
        pytest.skip("network_id is not derived from organism_id in this build")
    with pytest.raises(KineticLawReferenceError):
        assign_kinetic_laws(characterization_a, network_b)


# --- Tentative mass-action default (revision Steps 16-22) -----------------------------------


def test_tentative_mass_action_default_full_shape():
    """Step 16: an ordinary enzymatic reaction with no curated law and no stronger heuristic
    gets a fully-formed, explicitly tentative MASS_ACTION assignment."""
    handoff = dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(_compound(), _compound(id="atp"), _compound(id="g6p")),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="REACTANT", compound_id="atp"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert assignment.reason_codes == (KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT,)
    assert KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED in assignment.unresolved_reasons
    assert assignment.is_tentative
    for keyword in ("tentative", "provisional", "default"):
        assert keyword in assignment.explanation.lower()


def test_tentative_default_precedence_full_chain():
    """Step 17: curated > structural > Michaelis-Menten > tentative default > UNASSIGNED,
    exercised end to end on the same reaction shape with escalating knowledge removed."""
    base = {
        "compartments": (_compartment(),),
        "compounds": (_compound(), _compound(id="g6p")),
        "reactions": (_reaction(),),
        "reaction_participants": (
            _participant(role="REACTANT", compound_id="glc"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(),),
    }

    curated = _only(
        _assign(
            _handoff(
                **base, kinetic_measurements=(_kinetic_measurement(reported_rate_law="k1 * glc"),)
            )
        )
    )
    assert curated.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED

    mm = _only(_assign(_handoff(**base)))
    assert mm.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert not mm.is_tentative

    no_mm = dict(base)
    no_mm["reaction_participants"] = (
        _participant(role="REACTANT", compound_id="glc"),
        _participant(role="REACTANT", compound_id="glc"),
        _participant(role="PRODUCT", compound_id="g6p"),
    )
    tentative = _only(_assign(_handoff(**{**no_mm, "compounds": base["compounds"]})))
    assert tentative.kinetic_law_type is KineticLawType.MASS_ACTION
    assert tentative.is_tentative

    no_catalyst = dict(base)
    no_catalyst["reaction_enzyme_associations"] = ()
    unassigned = _only(_assign(_handoff(**no_catalyst)))
    assert unassigned.kinetic_law_type is KineticLawType.UNASSIGNED


def test_modified_enzyme_states_each_get_independent_tentative_defaults():
    """Step 19: E and E_P, neither with a curated law, each get their own tentative default;
    neither is collapsed and neither borrows the other's decision."""
    handoff = _e_and_ep_handoff()
    assignments = _assign(handoff)
    assert len(assignments.assignments) == 2
    e_assignment = _by_context(assignments, enzyme_state_id="e")
    ep_assignment = _by_context(assignments, enzyme_state_id="ep")
    for assignment in (e_assignment, ep_assignment):
        assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
        assert assignment.is_tentative
    assert e_assignment.assignment_id != ep_assignment.assignment_id


def test_multiple_isozymes_no_specific_law_each_get_tentative_default_not_global_unassigned():
    """Step 20: multiple catalyst contexts with no specific laws do not become globally
    UNASSIGNED -- here they still collapse (identical, empty evidence, existing policy), but
    remain a runnable tentative default rather than UNASSIGNED."""
    handoff = _two_isozyme_handoff()
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.is_tentative


def test_is_tentative_derived_marker_across_all_sources():
    """Step 22: ``is_tentative`` is True only for the tentative default; False for every other
    assignment_source/kinetic_law_type combination this package produces."""
    curated = _only(
        _assign(
            dataclasses.replace(
                _one_substrate_one_product_handoff(),
                kinetic_measurements=(_kinetic_measurement(reported_rate_law="k1 * glc"),),
            )
        )
    )
    assert curated.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
    assert curated.is_tentative is False

    structural = _only(_assign(_bare_state_transition_handoff()))
    assert structural.assignment_source is KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL
    assert structural.is_tentative is False

    mm = _only(_assign(_one_substrate_one_product_handoff()))
    assert mm.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert mm.is_tentative is False

    unassigned = _only(
        _assign(
            dataclasses.replace(
                _one_substrate_one_product_handoff(), reaction_enzyme_associations=()
            )
        )
    )
    assert unassigned.assignment_source is KineticLawAssignmentSource.UNASSIGNED
    assert unassigned.is_tentative is False

    tentative = _only(
        _assign(
            dataclasses.replace(
                _handoff(
                    compartments=(_compartment(),),
                    compounds=(_compound(), _compound(id="atp"), _compound(id="g6p")),
                    reactions=(_reaction(),),
                ),
                reaction_participants=(
                    _participant(role="REACTANT", compound_id="glc"),
                    _participant(role="REACTANT", compound_id="atp"),
                    _participant(role="PRODUCT", compound_id="g6p"),
                ),
                reaction_enzyme_associations=(_enzyme_association(),),
            )
        )
    )
    assert tentative.is_tentative is True


def test_tentative_default_is_immutable_and_reason_code_enforced():
    """The construction invariant: TENTATIVE_MASS_ACTION_DEFAULT always implies
    assignment_source=HEURISTIC, kinetic_law_type=MASS_ACTION, and a non-empty
    unresolved_reasons carrying KINETIC_MECHANISM_NOT_CURATED."""
    from app.agent2.kinetics import KineticLawAssignment

    with pytest.raises(ValueError, match="TENTATIVE_MASS_ACTION_DEFAULT"):
        KineticLawAssignment(
            assignment_id="r1::kinetic-law::general",
            reaction_id="r1",
            kinetic_law_type=KineticLawType.MICHAELIS_MENTEN,
            assignment_source=KineticLawAssignmentSource.HEURISTIC,
            policy_version="kinetic-law-v2",
            reason_codes=(KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT,),
            unresolved_reasons=(KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED,),
            explanation="test",
        )

    with pytest.raises(ValueError, match="unresolved_reasons must be empty"):
        KineticLawAssignment(
            assignment_id="r1::kinetic-law::general",
            reaction_id="r1",
            kinetic_law_type=KineticLawType.MASS_ACTION,
            assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
            policy_version="kinetic-law-v2",
            reason_codes=(KineticLawReasonCode.SIMPLE_ELEMENTARY_TRANSITION,),
            unresolved_reasons=(KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED,),
            explanation="test",
        )


# --- Substrate-Anchored Michaelis-Menten Eligibility Refinement (Real Integration Pilot 2
# Run 3 finding) -----------------------------------------------------------------------------


def _malonyl_coa_like_handoff(
    *, anchored_measurements: tuple[CuratedKineticMeasurement, ...] = ()
) -> Agent1CuratedKnowledgeViewContract:
    """Shaped exactly after the real, live malonyl-CoA:[acp] S-malonyltransferase reaction
    (Real Integration Pilot 2 Run 3): 2 reactants, 2 products, one catalyst, no reported law,
    no allostery, reversibility unknown."""
    return dataclasses.replace(
        _handoff(
            compartments=(_compartment(),),
            compounds=(
                _compound(id="malonyl-coa", name="Malonyl-CoA"),
                _compound(id="acp", name="Acyl-carrier protein"),
                _compound(id="coa", name="CoA"),
                _compound(id="malonyl-acp", name="Malonyl-[acp]"),
            ),
            reactions=(_reaction(),),
        ),
        reaction_participants=(
            _participant(role="REACTANT", compound_id="malonyl-coa"),
            _participant(role="REACTANT", compound_id="acp"),
            _participant(role="PRODUCT", compound_id="coa"),
            _participant(role="PRODUCT", compound_id="malonyl-acp"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
        kinetic_measurements=anchored_measurements,
    )


def _anchored_km(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km-malonyl",
        "parameter_type": "KM",
        "value": Decimal("18.0"),
        "unit": "uM",
        "reaction_id": "r1",
        "compound_id": "malonyl-coa",
    } | overrides
    return _kinetic_measurement(**merged)


def test_single_substrate_mm_unchanged_by_new_policy():
    """The pre-existing single-substrate/single-product heuristic path is untouched."""
    assignment = _only(_assign(_one_substrate_one_product_handoff()))
    assert assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert assignment.reason_codes == (KineticLawReasonCode.ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT,)


def test_multi_reactant_reaction_with_anchored_km_becomes_eligible():
    handoff = _malonyl_coa_like_handoff(anchored_measurements=(_anchored_km(),))
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    assert assignment.assignment_source is KineticLawAssignmentSource.HEURISTIC
    assert (
        KineticLawReasonCode.SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION
        in assignment.reason_codes
    )
    assert (
        KineticLawReasonCode.SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION
        in assignment.unresolved_reasons
    )
    # positively evidence-anchored, never conflated with the blind tentative default.
    assert not assignment.is_tentative


def test_multi_reactant_reaction_without_anchored_km_remains_conservative():
    handoff = _malonyl_coa_like_handoff(anchored_measurements=())
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is KineticLawType.MASS_ACTION
    assert assignment.is_tentative
    assert KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in assignment.reason_codes


def test_real_source_measurement_id_is_preserved():
    handoff = _malonyl_coa_like_handoff(anchored_measurements=(_anchored_km(id="km-real-18229"),))
    assignment = _only(_assign(handoff))
    assert assignment.source_measurement_ids == ("km-real-18229",)


def test_km_anchored_to_a_product_remains_ineligible():
    handoff = _malonyl_coa_like_handoff(
        anchored_measurements=(_anchored_km(id="km-product", compound_id="coa"),)
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.is_tentative


def test_vmax_alone_does_not_trigger_substrate_anchored_policy():
    handoff = _malonyl_coa_like_handoff(
        anchored_measurements=(
            _anchored_km(
                id="vmax-1", parameter_type="VMAX", compound_id="malonyl-coa", unit="1/s"
            ),
        )
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.is_tentative


def test_two_measurements_anchored_to_different_reactants_remains_ineligible():
    """Ambiguous evidence -- would imply a fuller multi-substrate characterization this
    policy does not attempt -- never arbitrarily picks one."""
    handoff = _malonyl_coa_like_handoff(
        anchored_measurements=(
            _anchored_km(id="km-malonyl", compound_id="malonyl-coa"),
            _anchored_km(id="km-acp", compound_id="acp", value=Decimal("5.0")),
        )
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.is_tentative


def test_conflicting_measurements_for_the_same_reactant_remain_conservative():
    handoff = _malonyl_coa_like_handoff(
        anchored_measurements=(
            _anchored_km(id="km-a", compound_id="malonyl-coa", value=Decimal("18.0")),
            _anchored_km(id="km-b", compound_id="malonyl-coa", value=Decimal("500.0")),
        )
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.is_tentative


def test_ambiguous_catalytic_context_remains_ineligible():
    """Multiple distinct catalytic enzyme states on the same reaction -- the same safety
    condition the plain Michaelis-Menten heuristic already enforces."""
    from app.agent2.types import CuratedEnzymeState

    handoff = _malonyl_coa_like_handoff(anchored_measurements=(_anchored_km(),))
    handoff = dataclasses.replace(
        handoff,
        enzyme_states=(
            CuratedEnzymeState(id="es1", state_type="BASE", protein_id="p1"),
            CuratedEnzymeState(id="es2", state_type="MODIFIED", protein_id="p1"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
            _enzyme_association(protein_id=None, enzyme_state_id="es2"),
        ),
    )
    assignment_set = _assign(handoff)
    for assignment in assignment_set.assignments:
        assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN


def test_allostery_blocks_substrate_anchored_eligibility_too():
    from app.agent2.types import CuratedAllostericInteraction, CuratedEnzymeState

    handoff = _malonyl_coa_like_handoff(anchored_measurements=(_anchored_km(),))
    handoff = dataclasses.replace(
        handoff,
        enzyme_states=(CuratedEnzymeState(id="es1", state_type="BASE", protein_id="p1"),),
        reaction_enzyme_associations=(
            _enzyme_association(protein_id=None, enzyme_state_id="es1"),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="ai1", enzyme_state_id="es1", ligand_compound_id="acp", effect="INHIBITOR"
            ),
        ),
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN
    assert assignment.is_tentative


def test_reversible_reaction_blocks_substrate_anchored_eligibility_too():
    handoff = _malonyl_coa_like_handoff(anchored_measurements=(_anchored_km(),))
    handoff = dataclasses.replace(
        handoff, reactions=(_reaction(reversible=True),)
    )
    assignment = _only(_assign(handoff))
    assert assignment.kinetic_law_type is not KineticLawType.MICHAELIS_MENTEN


def test_substrate_anchored_decision_is_deterministic_regardless_of_evidence_order():
    forward = _malonyl_coa_like_handoff(
        anchored_measurements=(
            _anchored_km(id="km-malonyl"),
            _anchored_km(id="km-other", compound_id="unrelated-compound-not-a-reactant"),
        )
    )
    reversed_order = dataclasses.replace(
        forward, kinetic_measurements=tuple(reversed(forward.kinetic_measurements))
    )
    a1 = _only(_assign(forward))
    a2 = _only(_assign(reversed_order))
    assert a1.kinetic_law_type == a2.kinetic_law_type == KineticLawType.MICHAELIS_MENTEN
    assert a1.source_measurement_ids == a2.source_measurement_ids == ("km-malonyl",)
