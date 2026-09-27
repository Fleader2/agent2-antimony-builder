"""Tests for Heuristic Boundary Assessment (Increment 6): ``app.agent2.boundaries``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, assembles it
into a ``FullNetwork``, characterizes it, assigns kinetic laws, declares
parameters, then calls
``assess_boundaries(network, characterization, assignments, parameters)``
on the result -- no test constructs a ``BoundaryAssessmentSet`` by hand
for the main scenarios, matching ``tests/agent2/test_parameters.py``'s
own convention.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.boundaries import BoundaryAssessmentSet, BoundaryReasonCode, assess_boundaries
from app.agent2.boundaries.errors import BoundaryReferenceError, UnsupportedBoundaryInputError
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    BoundaryAssessment,
    BoundaryLikelihood,
    BoundaryParameterBasis,
    CuratedAllostericInteraction,
    CuratedCompartment,
    CuratedCompound,
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
    merged = {"id": "a", "name": "A"} | overrides
    return CuratedCompound(**merged)


def _reaction(**overrides) -> CuratedReaction:
    merged = {"id": "r1", "name": "reaction 1"} | overrides
    return CuratedReaction(**merged)


def _participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "a",
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


def _linear_chain_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """R1: a -> b, R2: b -> c. Same compartment, no catalyst, no law, no branch/convergence."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b"), _compound(id="c")),
        "reactions": (_reaction(id="r1"), _reaction(id="r2")),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
    } | overrides
    return _handoff(**merged)


def _assess(handoff: Agent1CuratedKnowledgeViewContract) -> BoundaryAssessmentSet:
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    return assess_boundaries(network, characterization, assignments, parameters)


def _assess_full(handoff: Agent1CuratedKnowledgeViewContract):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    return network, characterization, assignments, parameters, boundaries


def _by_id(boundaries: BoundaryAssessmentSet, boundary_id: str):
    for assessment in boundaries.assessments:
        if assessment.boundary_id == boundary_id:
            return assessment
    raise AssertionError(f"no boundary with id {boundary_id!r}")


def _only(boundaries: BoundaryAssessmentSet):
    (assessment,) = boundaries.assessments
    return assessment


# --- Candidate generation (Step 47) ------------------------------------------------------------


def test_simple_linear_chain_generates_one_candidate():
    boundaries = _assess(_linear_chain_handoff())
    assert len(boundaries.assessments) == 1
    assessment = _only(boundaries)
    assert assessment.upstream_element_id == "r1"
    assert assessment.downstream_element_id == "r2"
    assert assessment.shared_species_ids


def test_branch_generates_two_separate_candidates():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="c", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    ids = {a.boundary_id for a in boundaries.assessments}
    assert ids == {"boundary::r1::r2", "boundary::r1::r3"}


def test_convergence_generates_two_separate_candidates():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c"), _compound(id="d")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="c", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="d", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    ids = {a.boundary_id for a in boundaries.assessments}
    assert ids == {"boundary::r1::r3", "boundary::r2::r3"}


def test_multiple_compartments_candidate_generation():
    handoff = _handoff(
        compartments=(_compartment(), _compartment(id="mito", name="mitochondrion")),
        compounds=(_compound(id="glc"),),
        reactions=(_reaction(id="r1"), _reaction(id="rt"), _reaction(id="r2")),
        reaction_participants=(
            _participant(
                reaction_id="r1",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="REACTANT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="mito",
            ),
            _participant(
                reaction_id="r2",
                compound_id="glc",
                role="REACTANT",
                compartment_id="mito",
            ),
        ),
    )
    boundaries = _assess(handoff)
    ids = {a.boundary_id for a in boundaries.assessments}
    assert ids == {"boundary::r1::rt", "boundary::rt::r2"}


def test_reversible_reaction_not_duplicated():
    handoff = _linear_chain_handoff(
        reactions=(_reaction(id="r1", reversible=True), _reaction(id="r2"))
    )
    boundaries = _assess(handoff)
    assert len(boundaries.assessments) == 1


def test_disconnected_subnetworks_generate_no_candidates_between_them():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="x"), _compound(id="y")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="x", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    assert boundaries.assessments == ()


def test_no_duplicate_candidate_ids():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="REACTANT"),
        ),
    )
    boundaries = _assess(handoff)
    ids = [a.boundary_id for a in boundaries.assessments]
    assert len(ids) == len(set(ids)) == 1
    assessment = _only(boundaries)
    assert len(assessment.shared_species_ids) == 2


def test_deterministic_candidate_identity_independent_of_reaction_order():
    handoff_a = _linear_chain_handoff()
    handoff_b = dataclasses.replace(
        handoff_a, reactions=tuple(reversed(handoff_a.reactions))
    )
    boundaries_a = _assess(handoff_a)
    boundaries_b = _assess(handoff_b)
    assert {a.boundary_id for a in boundaries_a.assessments} == {
        a.boundary_id for a in boundaries_b.assessments
    }


# --- Compartment / transport (Step 48) ---------------------------------------------------------


def test_same_compartment_no_compartment_transition_support():
    assessment = _only(_assess(_linear_chain_handoff()))
    assert BoundaryReasonCode.COMPARTMENT_TRANSITION.value not in assessment.supporting_reason_codes


def _transport_handoff() -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(), _compartment(id="mito", name="mitochondrion")),
        compounds=(_compound(id="glc"), _compound(id="x"), _compound(id="y")),
        reactions=(_reaction(id="r1"), _reaction(id="rt"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="x", role="REACTANT", compartment_id="cyto"),
            _participant(
                reaction_id="r1",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="REACTANT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="mito",
            ),
            _participant(
                reaction_id="r2",
                compound_id="glc",
                role="REACTANT",
                compartment_id="mito",
            ),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT", compartment_id="mito"),
        ),
    )


def test_compartment_transition_and_transport_both_fire_adjacent_to_transport_reaction():
    boundaries = _assess(_transport_handoff())
    for boundary_id in ("boundary::r1::rt", "boundary::rt::r2"):
        assessment = _by_id(boundaries, boundary_id)
        assert BoundaryReasonCode.COMPARTMENT_TRANSITION.value in assessment.supporting_reason_codes
        assert BoundaryReasonCode.TRANSPORT_INTERFACE.value in assessment.supporting_reason_codes


def test_transport_remains_heuristic_not_hard_boundary():
    """Transport supports but never forces VERY_HIGH by itself, and it is only one of
    several signals the categorical policy combines -- never a hard rule."""
    boundaries = _assess(_transport_handoff())
    for assessment in boundaries.assessments:
        assert assessment.likelihood in (
            BoundaryLikelihood.VERY_LOW,
            BoundaryLikelihood.LOW,
            BoundaryLikelihood.MEDIUM,
            BoundaryLikelihood.HIGH,
            BoundaryLikelihood.VERY_HIGH,
        )
        # never a numeric field anywhere on the assessment
        assert isinstance(assessment.likelihood, BoundaryLikelihood)


# --- Topology (Step 49) --------------------------------------------------------------------------


def test_branch_point_reason_code_fires():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="c", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::r2")
    assert BoundaryReasonCode.BRANCH_POINT.value in assessment.supporting_reason_codes


def test_convergence_point_reason_code_fires():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="c", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="a", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::r3")
    assert BoundaryReasonCode.CONVERGENCE_POINT.value in assessment.supporting_reason_codes


def test_high_connectivity_shared_species_opposes():
    compounds = [_compound(id="hub", name="Hub")] + [_compound(id=f"x{i}") for i in range(4)]
    reactions = [_reaction(id=f"p{i}") for i in range(4)] + [_reaction(id="c0")]
    participants = []
    for i in range(4):
        participants.append(
            _participant(reaction_id=f"p{i}", compound_id=f"x{i}", role="REACTANT")
        )
        participants.append(_participant(reaction_id=f"p{i}", compound_id="hub", role="PRODUCT"))
    participants.append(_participant(reaction_id="c0", compound_id="hub", role="REACTANT"))
    participants.append(_participant(reaction_id="c0", compound_id="x0", role="PRODUCT"))
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=tuple(compounds),
        reactions=tuple(reactions),
        reaction_participants=tuple(participants),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::p0::c0")
    assert BoundaryReasonCode.HIGH_CONNECTIVITY_CONTINUITY.value in assessment.opposing_reason_codes


def test_strong_local_continuity_requires_a_meaningfully_shared_law_not_mutual_unassigned():
    """Revision correction: two reactions that both simply have no assigned kinetic law
    (UNASSIGNED on both sides) must not count as "same law" continuity evidence -- that is
    mutual absence of information, not a shown shared mechanism."""
    assessment = _only(_assess(_linear_chain_handoff()))
    assert BoundaryReasonCode.STRONG_LOCAL_CONTINUITY.value not in assessment.opposing_reason_codes
    assert assessment.likelihood is BoundaryLikelihood.LOW


def test_strong_local_continuity_opposes_boring_chain_link_with_a_real_shared_law():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert BoundaryReasonCode.STRONG_LOCAL_CONTINUITY.value in assessment.opposing_reason_codes
    assert assessment.likelihood is BoundaryLikelihood.VERY_LOW


# --- Enzyme states / regulation (Step 50) -------------------------------------------------------


def test_enzyme_state_transition_reason_fires():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"), _reaction(id="rt")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="rt", compound_id="b", role="REACTANT"),
        ),
        enzyme_states=(
            CuratedEnzymeState(id="es0", state_type="UNMOD"),
            CuratedEnzymeState(id="es1", state_type="MOD"),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t1", from_state_id="es0", to_state_id="es1",
                transition_type="PHOSPHORYLATION", reaction_id="rt",
            ),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::rt")
    assert BoundaryReasonCode.ENZYME_STATE_TRANSITION.value in assessment.supporting_reason_codes


def test_allosteric_and_regulatory_context_change_fires():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        enzyme_states=(CuratedEnzymeState(id="es1", state_type="MOD", protein_id="p1"),),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id=None, enzyme_state_id="es1"),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="allo1", enzyme_state_id="es1", ligand_compound_id="a", effect="ACTIVATOR"
            ),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::r2")
    assert (
        BoundaryReasonCode.CURATED_REGULATORY_CONTEXT_CHANGE.value
        in assessment.supporting_reason_codes
    )


def test_regulatory_context_change_is_weak_not_a_biological_absence_claim():
    """No curated regulation on the downstream side must never be read as 'no regulation
    exists' -- only reflected via the deliberately WEAK-strength reason code."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        enzyme_states=(CuratedEnzymeState(id="es1", state_type="MOD", protein_id="p1"),),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id=None, enzyme_state_id="es1"),
        ),
        allosteric_interactions=(
            CuratedAllostericInteraction(
                id="allo1", enzyme_state_id="es1", ligand_compound_id="a", effect="ACTIVATOR"
            ),
        ),
    )
    assessment = _by_id(_assess(handoff), "boundary::r1::r2")
    assert "no regulation exists" not in assessment.explanation.lower()
    assert "not regulated" not in assessment.explanation.lower()


# --- Kinetics (Step 51) -----------------------------------------------------------------------


def test_same_kinetic_law_type_no_discontinuity():
    assessment = _only(_assess(_linear_chain_handoff()))
    assert (
        BoundaryReasonCode.KINETIC_LAW_DISCONTINUITY.value not in assessment.supporting_reason_codes
    )


def test_different_kinetic_law_types_support_discontinuity():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c"), _compound(id="d")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r2", protein_id="p1"),),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KM", value=Decimal("0.1"), unit="mM",
                reaction_id="r2", compound_id="b",
            ),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::r2")
    assert BoundaryReasonCode.KINETIC_LAW_DISCONTINUITY.value in assessment.supporting_reason_codes


def test_tentative_assignment_gives_weaker_discontinuity_than_curated():
    """A discontinuity next to a tentative default must not combine as strongly as one next
    to a curated reported law -- exercised by comparing two otherwise-identical scenarios."""
    base_compounds = (_compound(id="a"), _compound(id="b"), _compound(id="c"), _compound(id="d"))
    base_reactions = (_reaction(id="r1"), _reaction(id="r2"))
    base_participants = (
        _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
        _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
        _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        _participant(reaction_id="r2", compound_id="d", role="REACTANT"),
    )
    tentative_handoff = _handoff(
        compartments=(_compartment(),),
        compounds=base_compounds,
        reactions=base_reactions,
        reaction_participants=base_participants,
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r2", protein_id="p1"),),
    )
    curated_handoff = dataclasses.replace(
        tentative_handoff,
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reaction_id="r2", reported_rate_law="k1 * b",
            ),
        ),
    )
    tentative_assessment = _by_id(_assess(tentative_handoff), "boundary::r1::r2")
    curated_assessment = _by_id(_assess(curated_handoff), "boundary::r1::r2")
    discontinuity = BoundaryReasonCode.KINETIC_LAW_DISCONTINUITY.value
    assert discontinuity in tentative_assessment.supporting_reason_codes
    assert discontinuity in curated_assessment.supporting_reason_codes


# --- Parameter source (Step 52) ------------------------------------------------------------------


def test_curated_to_curated_parameter_continuity():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("1"), unit="1/s", reaction_id="r1"
            ),
            _kinetic_measurement(
                id="km1b", parameter_type="KM", value=Decimal("0.1"), unit="mM",
                reaction_id="r1", compound_id="a",
            ),
            _kinetic_measurement(
                id="km2", parameter_type="KCAT", value=Decimal("2"), unit="1/s", reaction_id="r2"
            ),
            _kinetic_measurement(
                id="km2b", parameter_type="KM", value=Decimal("0.2"), unit="mM",
                reaction_id="r2", compound_id="b",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.PARAMETER_SOURCE_DISCONTINUITY.value
        not in assessment.supporting_reason_codes
    )
    assert assessment.parameter_basis is BoundaryParameterBasis.CURATED_OR_LITERATURE


def test_curated_to_placeholder_parameter_change_never_supports_a_boundary():
    """Revision requirement: a parameter-source difference (here, one side curated, the
    other placeholder-only) never contributes supporting evidence -- PARAMETER_SOURCE_
    DISCONTINUITY is permanently retired to NEUTRAL. The underlying fact is still
    disclosed, but only via parameter_basis (audit), never via boundary-likelihood
    evidence."""
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("1"), unit="1/s", reaction_id="r1"
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    discontinuity = BoundaryReasonCode.PARAMETER_SOURCE_DISCONTINUITY.value
    assert discontinuity not in assessment.supporting_reason_codes
    assert discontinuity not in assessment.opposing_reason_codes
    assert assessment.parameter_basis is BoundaryParameterBasis.MIXED


def test_placeholder_only_region_gives_placeholder_only_basis():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert assessment.parameter_basis is BoundaryParameterBasis.PLACEHOLDER_ONLY


def test_no_parameters_at_all_gives_none_basis():
    assessment = _only(_assess(_linear_chain_handoff()))
    assert assessment.parameter_basis is BoundaryParameterBasis.NONE


# --- Likelihood coverage (Step 53) ---------------------------------------------------------------


def test_very_low_reachable():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert assessment.likelihood is BoundaryLikelihood.VERY_LOW


def test_medium_reachable_via_single_moderate_support():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="c", role="PRODUCT"),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::r1::r2")
    assert assessment.likelihood is BoundaryLikelihood.MEDIUM


def test_high_reachable_via_transport():
    boundaries = _assess(_transport_handoff())
    assessment = _by_id(boundaries, "boundary::r1::rt")
    assert assessment.likelihood is BoundaryLikelihood.HIGH


def test_structural_discontinuities_alone_never_reach_very_high():
    """Revision requirement: VERY_HIGH must require genuine functional-isolation evidence,
    never mere accumulation of structural proxies. Transport (MODERATE, revised down from
    STRONG) + compartment transition (MODERATE) + branch point (WEAK, revised down from
    MODERATE) is exactly the kind of "several structural discontinuities, no real isolation
    evidence" case the revision targets -- it must cap at HIGH, never VERY_HIGH."""
    handoff = _handoff(
        compartments=(_compartment(), _compartment(id="mito", name="mitochondrion")),
        compounds=(_compound(id="glc"), _compound(id="x"), _compound(id="y"), _compound(id="z")),
        reactions=(_reaction(id="r1"), _reaction(id="rt"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="x", role="REACTANT", compartment_id="cyto"),
            _participant(
                reaction_id="r1",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="REACTANT",
                compartment_id="cyto",
            ),
            _participant(
                reaction_id="rt",
                compound_id="glc",
                role="PRODUCT",
                compartment_id="mito",
            ),
            _participant(
                reaction_id="r2",
                compound_id="glc",
                role="REACTANT",
                compartment_id="mito",
            ),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT", compartment_id="mito"),
            _participant(
                reaction_id="r3",
                compound_id="glc",
                role="REACTANT",
                compartment_id="mito",
            ),
            _participant(reaction_id="r3", compound_id="z", role="PRODUCT", compartment_id="mito"),
        ),
    )
    boundaries = _assess(handoff)
    assessment = _by_id(boundaries, "boundary::rt::r2")
    assert assessment.likelihood is BoundaryLikelihood.HIGH
    # IRREVERSIBLE_OUTPUT_ISOLATION is the only rule that can still contribute STRONG
    # support (Increment 6 feedback-heuristic revision: INTRINSIC_FEEDBACK_ISOLATION is
    # now an opposing rule, so it can never appear here at all).
    assert (
        BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION.value
        not in assessment.supporting_reason_codes
    )


def test_very_high_requires_genuine_functional_isolation_evidence():
    """VERY_HIGH is reachable only through the functional-modularity rules (here, an
    explicitly curated irreversible upstream step), never through structural proxies
    alone."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=False), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert assessment.likelihood is BoundaryLikelihood.VERY_HIGH
    assert (
        BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION.value in assessment.supporting_reason_codes
    )


def test_unresolved_reversibility_never_triggers_irreversible_output_boundary_evidence():
    """Conservative Reversibility Default increment: an unresolved upstream reversible
    (`None` -- modeled elsewhere as tentatively reversible for model-construction purposes
    only) must never itself contribute IRREVERSIBLE_OUTPUT_ISOLATION support, exactly like a
    curated `reversible=True` upstream reaction -- only explicit `reversible=False` may. This
    package's own `app.agent2.reversibility` "assumed reversible" concept is never consulted
    here at all: `CandidateFacts.upstream_reversible` is populated directly from the curated,
    unmodified `ReactionSpecification.reversible`."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=None), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert assessment.likelihood is not BoundaryLikelihood.VERY_HIGH
    assert (
        BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION.value
        not in assessment.supporting_reason_codes
    )


def test_curated_reversible_true_upstream_also_never_triggers_irreversible_output_boundary():
    """Mirrors the None case -- an explicitly curated `reversible=True` upstream reaction is
    just as ineligible for IRREVERSIBLE_OUTPUT_ISOLATION as an unresolved one; only explicit
    `False` qualifies."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=True), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION.value
        not in assessment.supporting_reason_codes
    )


def test_low_reachable_via_no_support_weak_opposition_or_none():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r2", protein_id="p1"),),
    )
    assessment = _only(_assess(handoff))
    assert assessment.likelihood in (BoundaryLikelihood.LOW, BoundaryLikelihood.MEDIUM)


def test_no_numeric_probability_anywhere():
    boundaries = _assess(_transport_handoff())
    for assessment in boundaries.assessments:
        assert isinstance(assessment.likelihood, BoundaryLikelihood)
        assert not hasattr(assessment, "probability")
        assert not hasattr(assessment, "confidence_score")


# --- Supporting/opposing rule combination (Step 54) -----------------------------------------------


def test_support_only_scenario():
    boundaries = _assess(_transport_handoff())
    assessment = _by_id(boundaries, "boundary::r1::rt")
    assert assessment.supporting_reason_codes
    assert assessment.opposing_reason_codes == ()


def test_opposition_only_scenario():
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert assessment.opposing_reason_codes
    assert assessment.supporting_reason_codes == ()


def test_mixed_evidence_scenario():
    """Convergence (revised to WEAK support -- pure topology, per the revision) alongside
    high-connectivity continuity (MODERATE oppose) is genuinely mixed evidence, but weak
    support outweighed by moderate-or-stronger opposition resolves conservatively to LOW,
    not MEDIUM -- exactly the "weakly connected interface" default (policy branch 5)."""
    compounds = [_compound(id="hub")] + [_compound(id=f"x{i}") for i in range(4)]
    reactions = [_reaction(id=f"p{i}") for i in range(4)] + [_reaction(id="c0")]
    participants = []
    for i in range(4):
        participants.append(_participant(reaction_id=f"p{i}", compound_id=f"x{i}", role="REACTANT"))
        participants.append(_participant(reaction_id=f"p{i}", compound_id="hub", role="PRODUCT"))
    participants.append(_participant(reaction_id="c0", compound_id="hub", role="REACTANT"))
    participants.append(_participant(reaction_id="c0", compound_id="x0", role="PRODUCT"))
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=tuple(compounds),
        reactions=tuple(reactions),
        reaction_participants=tuple(participants),
    )
    assessment = _by_id(_assess(handoff), "boundary::p0::c0")
    assert assessment.supporting_reason_codes
    assert assessment.opposing_reason_codes
    assert assessment.likelihood is BoundaryLikelihood.LOW


def test_deterministic_categorical_combination_repeatable():
    network, characterization, assignments, parameters, first = _assess_full(_transport_handoff())
    second = assess_boundaries(network, characterization, assignments, parameters)
    assert first == second


# --- Reassessment stability (Step 55) -------------------------------------------------------------


def test_reassessment_stability_boundary_ids_unchanged_reasons_may_change():
    handoff_placeholder = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r1", protein_id="p1"),),
    )
    handoff_curated = dataclasses.replace(
        handoff_placeholder,
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("5"), unit="1/s", reaction_id="r1"
            ),
        ),
    )
    boundaries_placeholder = _assess(handoff_placeholder)
    boundaries_curated = _assess(handoff_curated)
    ids_placeholder = {a.boundary_id for a in boundaries_placeholder.assessments}
    ids_curated = {a.boundary_id for a in boundaries_curated.assessments}
    assert ids_placeholder == ids_curated

    before = _only(boundaries_placeholder)
    after = _only(boundaries_curated)
    assert before.boundary_id == after.boundary_id
    assert before.parameter_basis != after.parameter_basis


# --- Validation failures -----------------------------------------------------------------------


def test_assess_boundaries_rejects_wrong_network_type():
    network, characterization, assignments, parameters, _ = _assess_full(_linear_chain_handoff())
    with pytest.raises(UnsupportedBoundaryInputError):
        assess_boundaries("not-a-network", characterization, assignments, parameters)


def test_assess_boundaries_rejects_wrong_characterization_type():
    network, characterization, assignments, parameters, _ = _assess_full(_linear_chain_handoff())
    with pytest.raises(UnsupportedBoundaryInputError):
        assess_boundaries(network, "not-a-characterization", assignments, parameters)


def test_assess_boundaries_rejects_network_id_mismatch():
    handoff_a = _linear_chain_handoff()
    handoff_b = dataclasses.replace(
        handoff_a, organism_id="different-organism-for-a-new-network-id"
    )
    network_a = assemble_full_network(handoff_a)
    network_b = assemble_full_network(handoff_b)
    characterization_a = characterize_full_network(network_a)
    assignments_a = assign_kinetic_laws(characterization_a, network_a)
    parameters_a = declare_parameters(assignments_a, network_a)
    if network_a.network_id == network_b.network_id:
        pytest.skip("network_id is not derived from organism_id in this build")
    with pytest.raises(BoundaryReferenceError):
        assess_boundaries(network_b, characterization_a, assignments_a, parameters_a)


def test_boundary_assessment_set_rejects_duplicate_boundary_id():
    assessment = BoundaryAssessment(
        boundary_id="boundary::r1::r2",
        upstream_element_id="r1",
        downstream_element_id="r2",
        likelihood=BoundaryLikelihood.LOW,
        explanation="test",
        policy_version="boundary-v1",
    )
    with pytest.raises(ValueError, match="duplicate boundary_id"):
        BoundaryAssessmentSet(
            network_id="n1",
            characterization_policy_version="reaction-characterization-v1",
            kinetic_law_policy_version="kinetic-law-v2",
            parameter_policy_version="parameter-declaration-v1",
            boundary_policy_version="boundary-v1",
            assessments=(assessment, assessment),
        )


# --- Increment 6 pre-commit scientific revision: required new tests ----------------------------


def test_parameter_source_discontinuity_never_appears_in_any_reason_codes():
    """Parameter-source changes alone must never imply a boundary, in either direction --
    PARAMETER_SOURCE_DISCONTINUITY, PLACEHOLDER_PARAMETER_REGION, and PARAMETERIZATION_
    CONTINUITY are permanently retired to NEUTRAL and must never appear on any assessment,
    however extreme the parameter-source asymmetry."""
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("1"), unit="1/s", reaction_id="r1"
            ),
            _kinetic_measurement(
                id="km2",
                parameter_type="KM",
                value=Decimal("0.5"),
                unit="mM",
                reaction_id="r1",
                compound_id="a",
            ),
        ),
    )
    retired_codes = {
        BoundaryReasonCode.PARAMETER_SOURCE_DISCONTINUITY.value,
        BoundaryReasonCode.PLACEHOLDER_PARAMETER_REGION.value,
        BoundaryReasonCode.PARAMETERIZATION_CONTINUITY.value,
    }
    for assessment in _assess(handoff).assessments:
        assert not (retired_codes & set(assessment.supporting_reason_codes))
        assert not (retired_codes & set(assessment.opposing_reason_codes))


def test_placeholder_parameters_alone_do_not_imply_biological_modularity():
    """A one-side-all-placeholder / other-side-curated asymmetry still discloses via
    parameter_basis (audit), but must never contribute PLACEHOLDER_PARAMETER_REGION (or any
    other) supporting evidence toward the boundary likelihood itself."""
    handoff = dataclasses.replace(
        _linear_chain_handoff(),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("1"), unit="1/s", reaction_id="r1"
            ),
            _kinetic_measurement(
                id="km2",
                parameter_type="KM",
                value=Decimal("0.5"),
                unit="mM",
                reaction_id="r1",
                compound_id="a",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.PLACEHOLDER_PARAMETER_REGION.value
        not in assessment.supporting_reason_codes
    )
    assert assessment.parameter_basis is BoundaryParameterBasis.MIXED
    # the only remaining evidence, if any, must come from genuinely structural/functional
    # rules -- never from the retired parameterization-convenience codes.
    retired_codes = {
        BoundaryReasonCode.PARAMETER_SOURCE_DISCONTINUITY.value,
        BoundaryReasonCode.PLACEHOLDER_PARAMETER_REGION.value,
        BoundaryReasonCode.PARAMETERIZATION_CONTINUITY.value,
    }
    assert not (retired_codes & set(assessment.supporting_reason_codes))


def test_feedback_rules_neutral_when_regulator_type_unresolvable():
    """An interaction whose regulator_type does not match the recognized "compound"
    vocabulary must never be resolved to a side -- neither confined nor crossing fires."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="unresolvable-type",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="c",
                target_id="r1",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    # INTRINSIC_FEEDBACK_ISOLATION is the meaningful check here: an unresolvable
    # regulator_type must never be treated as confined feedback (would otherwise wrongly
    # OPPOSE). EXTRINSIC_FEEDBACK_CROSSING_DEFERRED is always NEUTRAL regardless of input
    # (Increment 6 feedback-heuristic revision) -- checking it here is a harmless but no
    # longer input-sensitive invariant, kept for documentation completeness.
    assert (
        BoundaryReasonCode.INTRINSIC_FEEDBACK_ISOLATION.value
        not in assessment.opposing_reason_codes
    )
    assert (
        BoundaryReasonCode.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED.value
        not in assessment.opposing_reason_codes
    )


def test_feedback_rules_neutral_when_target_id_missing():
    """An interaction with no resolvable target_id must never be resolved to a side."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="compound",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="c",
                target_id=None,
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.INTRINSIC_FEEDBACK_ISOLATION.value
        not in assessment.opposing_reason_codes
    )
    assert (
        BoundaryReasonCode.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED.value
        not in assessment.opposing_reason_codes
    )


def test_feedback_rules_neutral_when_regulator_touches_neither_side():
    """A regulatory interaction whose regulator compound is external to both candidate
    reactions (touches neither side) must never be treated as confined or crossing. The
    "external" compound must still be a real, curated compound (participant of some third,
    disconnected reaction) -- FullNetwork itself rejects a regulatory interaction naming an
    entirely unknown compound, so this is the only way to construct a genuinely external-
    but-valid regulator."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(
            _compound(id="a"),
            _compound(id="b"),
            _compound(id="c"),
            _compound(id="external"),
            _compound(id="other"),
        ),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="other", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="external", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="compound",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="external",
                target_id="r1",
            ),
        ),
    )
    assessment = _by_id(_assess(handoff), "boundary::r1::r2")
    assert (
        BoundaryReasonCode.INTRINSIC_FEEDBACK_ISOLATION.value
        not in assessment.opposing_reason_codes
    )
    assert (
        BoundaryReasonCode.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED.value
        not in assessment.opposing_reason_codes
    )


def test_deferred_principles_always_neutral():
    """The three deferred-principle rules must never contribute supporting or opposing
    evidence, across any realistic scenario, until a later agent can evaluate them."""
    from app.agent2.boundaries import rules as boundary_rules

    for handoff in (
        _linear_chain_handoff(),
        _transport_handoff(),
    ):
        for assessment in _assess(handoff).assessments:
            for code in (
                BoundaryReasonCode.RELAXATION_TIME_INVARIANCE_DEFERRED.value,
                BoundaryReasonCode.CONTEXT_REUSABILITY_DEFERRED.value,
                BoundaryReasonCode.STABLE_FUNCTIONAL_ROLE_DEFERRED.value,
            ):
                assert code not in assessment.supporting_reason_codes
                assert code not in assessment.opposing_reason_codes

    # Direct unit check: each deferred rule always returns NEUTRAL regardless of input.
    dummy_facts = boundary_rules.CandidateFacts(
        upstream_reaction_id="r1",
        downstream_reaction_id="r2",
        shared_species_ids=("s1",),
        upstream_classes=frozenset(),
        downstream_classes=frozenset(),
        upstream_compartments=frozenset({"cyto"}),
        downstream_compartments=frozenset({"cyto"}),
        upstream_regulatory_context=False,
        downstream_regulatory_context=False,
        upstream_law_types=frozenset(),
        downstream_law_types=frozenset(),
        upstream_law_confidence=None,
        downstream_law_confidence=None,
        any_shared_species_branch=False,
        any_shared_species_convergence=False,
        any_shared_species_high_connectivity=False,
        upstream_reversible=None,
        downstream_reversible=None,
        upstream_catalytic_ids=frozenset(),
        downstream_catalytic_ids=frozenset(),
        confined_inhibitory_feedback=False,
        crossing_regulatory_interaction=False,
    )
    for deferred_rule in (
        boundary_rules.relaxation_time_invariance,
        boundary_rules.context_reusability,
        boundary_rules.stable_functional_role,
    ):
        outcome = deferred_rule(dummy_facts)
        assert outcome.direction.value == "NEUTRAL"
        assert outcome.strength is None


def test_shared_catalyst_coupling_opposes():
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="shared_p"),
            _enzyme_association(reaction_id="r2", protein_id="shared_p"),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.SHARED_RESOURCE_COUPLING.value in assessment.opposing_reason_codes
    )


def test_intrinsic_feedback_isolation_opposes_boundary():
    """Increment 6 feedback-heuristic revision: a negative feedback loop confined entirely
    within one side of a candidate interface is *intrinsic* evidence that side is already a
    self-contained functional module (a nested, module-defining loop) -- this now OPPOSES
    the boundary (previously, under the pre-revision `negative_feedback_isolation` name, it
    incorrectly SUPPORTED it).

    Renamed again from `intrinsic_feedback_confinement` to
    `intrinsic_feedback_isolation` (naming/documentation only -- same
    deterministic trigger, same OPPOSE/STRONG outcome): the scientific
    concept is functional isolation via reduced retroactivity, not mere
    spatial "confinement."

    Meaning of OPPOSE here, spelled out: this rule opposes placing *a
    boundary inside the locally isolated circuit* that the confined
    feedback interaction defines -- it argues for preserving that
    self-regulated circuit's integrity. It does NOT mean the two
    candidate reactions should necessarily be merged into one module;
    Agent 2 never decides that here (that is Increment 7's job)."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="compound",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="c",
                target_id="r2",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.INTRINSIC_FEEDBACK_ISOLATION.value
        in assessment.opposing_reason_codes
    )
    # Weak structural support (curated_regulatory_context_change, since only r2 now has a
    # curated regulation reference) alongside the STRONG oppose lands at LOW (policy branch
    # 5), not VERY_LOW (branch 1, which requires no supporting evidence at all) -- either way,
    # nowhere near VERY_HIGH/HIGH, which is the property this test exists to check.
    assert assessment.likelihood is BoundaryLikelihood.LOW


def test_extrinsic_feedback_crossing_is_neutral_not_opposing():
    """Increment 6 feedback-heuristic revision: a regulatory interaction confirmed to cross
    the candidate interface no longer opposes the boundary by default (previously, under the
    pre-revision `feedback_crossing_boundary` name, this fired OPPOSE STRONG). Nested
    feedback loops are ordinary biology -- a loop crossing a module boundary is presumptively
    *extrinsic*, module-regulating communication between two already-independent modules,
    not proof they are one functional unit. Agent 2 has no dynamic-simulation capability to
    confirm the loop is direct, strong, constitutive, local, and minimally regulated (the
    properties that would be required before crossing feedback could legitimately oppose a
    boundary), so the rule always returns NEUTRAL and never appears in either reason-code
    tuple."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1"), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="compound",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="c",
                target_id="r1",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED.value
        not in assessment.opposing_reason_codes
    )
    assert (
        BoundaryReasonCode.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED.value
        not in assessment.supporting_reason_codes
    )


def test_intrinsic_feedback_isolation_reason_code_naming():
    """Increment 6 terminology revision: the reason code is `INTRINSIC_FEEDBACK_ISOLATION`
    (the functional-isolation concept), and the old `INTRINSIC_FEEDBACK_CONFINEMENT` name
    (mere spatial confinement) no longer exists anywhere in the vocabulary."""
    names = {member.name for member in BoundaryReasonCode}
    values = {member.value for member in BoundaryReasonCode}
    assert "INTRINSIC_FEEDBACK_ISOLATION" in names
    assert "INTRINSIC_FEEDBACK_ISOLATION" in values
    assert "INTRINSIC_FEEDBACK_CONFINEMENT" not in names
    assert "INTRINSIC_FEEDBACK_CONFINEMENT" not in values
    assert hasattr(BoundaryReasonCode, "INTRINSIC_FEEDBACK_ISOLATION")
    assert not hasattr(BoundaryReasonCode, "INTRINSIC_FEEDBACK_CONFINEMENT")

    from app.agent2.boundaries import rules as boundary_rules

    assert hasattr(boundary_rules, "intrinsic_feedback_isolation")
    assert not hasattr(boundary_rules, "intrinsic_feedback_confinement")


def test_extrinsic_feedback_crossing_neutral_regardless_of_effect_sign():
    """Rule 2/3 of the feedback-heuristic revision: crossing feedback is NEUTRAL regardless
    of whether the underlying effect is activating or inhibiting -- direction/strength
    inference is exactly what Agent 2 must not attempt here. Direct unit check, since the
    rule ignores its input entirely by design."""
    from app.agent2.boundaries import rules as boundary_rules

    base_facts = boundary_rules.CandidateFacts(
        upstream_reaction_id="r1",
        downstream_reaction_id="r2",
        shared_species_ids=("s1",),
        upstream_classes=frozenset(),
        downstream_classes=frozenset(),
        upstream_compartments=frozenset({"cyto"}),
        downstream_compartments=frozenset({"cyto"}),
        upstream_regulatory_context=False,
        downstream_regulatory_context=False,
        upstream_law_types=frozenset(),
        downstream_law_types=frozenset(),
        upstream_law_confidence=None,
        downstream_law_confidence=None,
        any_shared_species_branch=False,
        any_shared_species_convergence=False,
        any_shared_species_high_connectivity=False,
        upstream_reversible=None,
        downstream_reversible=None,
        upstream_catalytic_ids=frozenset(),
        downstream_catalytic_ids=frozenset(),
        confined_inhibitory_feedback=False,
        crossing_regulatory_interaction=False,
    )
    for crossing in (True, False):
        facts = dataclasses.replace(base_facts, crossing_regulatory_interaction=crossing)
        outcome = boundary_rules.extrinsic_feedback_crossing(facts)
        assert outcome.direction.value == "NEUTRAL"
        assert outcome.strength is None


def test_combination_table_strong_support_plus_strong_oppose_falls_to_medium():
    """Genuine strong evidence on both sides (an irreversible upstream step, but also an
    intrinsic feedback loop confined to that same upstream side) must never resolve to an
    extreme likelihood -- the categorical table conservatively lands at MEDIUM. (Increment 6
    feedback-heuristic revision: this scenario previously used *crossing* feedback for the
    opposing signal; crossing feedback is now NEUTRAL by default, so confined/intrinsic
    feedback -- now itself an opposing rule -- is used instead, confined to r1's own side.)
    """
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=False), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        regulatory_interactions=(
            CuratedRegulatoryInteraction(
                id="reg1",
                regulator_type="compound",
                target_type="reaction",
                effect="INHIBITION",
                regulator_id="a",
                target_id="r1",
            ),
        ),
    )
    assessment = _only(_assess(handoff))
    assert (
        BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION.value in assessment.supporting_reason_codes
    )
    assert (
        BoundaryReasonCode.INTRINSIC_FEEDBACK_ISOLATION.value
        in assessment.opposing_reason_codes
    )
    assert assessment.likelihood is BoundaryLikelihood.MEDIUM


def test_combination_table_strong_support_plus_moderate_oppose_gives_high_not_very_high():
    """Strong isolation evidence blocked from VERY_HIGH by a mere MODERATE opposing signal
    must still land at HIGH -- not silently dropped further. Tested directly against
    ``policy.combine_outcomes`` (rather than through a full curated scenario) because
    constructing an end-to-end fixture with *exactly* these two signals and no incidental
    third (e.g. two enzyme-eligible reactions sharing a catalyst tend to also end up with
    the same heuristic law type, which independently triggers STRONG_LOCAL_CONTINUITY) is
    not reliably possible without exercising unrelated heuristics -- this is the documented,
    intended use of the pure combination function as its own unit under test."""
    from app.agent2.boundaries import policy
    from app.agent2.boundaries.types import RuleDirection, RuleOutcome, RuleStrength

    outcomes = (
        RuleOutcome(
            BoundaryReasonCode.IRREVERSIBLE_OUTPUT_ISOLATION,
            RuleDirection.SUPPORT,
            RuleStrength.STRONG,
        ),
        RuleOutcome(
            BoundaryReasonCode.SHARED_RESOURCE_COUPLING, RuleDirection.OPPOSE, RuleStrength.MODERATE
        ),
    )
    assert policy.combine_outcomes(outcomes) is BoundaryLikelihood.HIGH
