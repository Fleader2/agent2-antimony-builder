"""Tests for Module Decomposition (Increment 7): ``app.agent2.modules``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, assembles it
into a ``FullNetwork``, characterizes it, assigns kinetic laws, declares
parameters, assesses boundaries, then calls
``decompose_network(network, assignments, parameters, boundaries)`` on the
result -- matching ``tests/agent2/test_boundaries.py``'s own convention.
Each fixture is deliberately built to land on one specific
``BoundaryLikelihood`` (confirmed empirically against the actual,
already-implemented Increment 6 rule catalog), never assumed.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.modules import ModuleDecompositionReferenceError, decompose_network
from app.agent2.modules.types import ModuleDecompositionSet
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    BoundaryLikelihood,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    InterModuleBoundaryInterface,
    ModuleDecomposition,
    ModuleSpecification,
)
from app.agent2.version import MODULE_DECOMPOSITION_POLICY_VERSION

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


def _empty_network_handoff() -> Agent1CuratedKnowledgeViewContract:
    return _handoff()


def _linear_chain_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """R1: a -> b, R2: b -> c. Confirmed LOW (no supporting or opposing evidence beyond a
    weakly-connected default)."""
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


def _single_isolated_reaction_handoff() -> Agent1CuratedKnowledgeViewContract:
    """One reaction, no neighbor -- never appears in any candidate boundary at all."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
    )


def _branch_point_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1: a -> x; R2: x -> y; R3: x -> z. Both boundary::r1::r2 and boundary::r1::r3
    confirmed MEDIUM (BRANCH_POINT support only, WEAK, no opposition)."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="x"), _compound(id="y"), _compound(id="z")),
        reactions=(_reaction(id="r1"), _reaction(id="r2"), _reaction(id="r3")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="x", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="x", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="x", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="z", role="PRODUCT"),
        ),
    )


def _transport_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1 (cyto) -> RT (transport, cyto->mito) -> R2 (mito). Both boundary::r1::rt and
    boundary::rt::r2 confirmed HIGH (COMPARTMENT_TRANSITION + TRANSPORT_INTERFACE, both
    MODERATE support, no opposition -- policy branch 4)."""
    return _handoff(
        compartments=(_compartment(), _compartment(id="mito", name="mitochondrion")),
        compounds=(_compound(id="glc"), _compound(id="x"), _compound(id="y")),
        reactions=(_reaction(id="r1"), _reaction(id="rt"), _reaction(id="r2")),
        reaction_participants=(
            _participant(
                reaction_id="r1", compound_id="x", role="REACTANT", compartment_id="cyto"
            ),
            _participant(
                reaction_id="r1", compound_id="glc", role="PRODUCT", compartment_id="cyto"
            ),
            _participant(
                reaction_id="rt", compound_id="glc", role="REACTANT", compartment_id="cyto"
            ),
            _participant(
                reaction_id="rt", compound_id="glc", role="PRODUCT", compartment_id="mito"
            ),
            _participant(
                reaction_id="r2", compound_id="glc", role="REACTANT", compartment_id="mito"
            ),
            _participant(reaction_id="r2", compound_id="y", role="PRODUCT", compartment_id="mito"),
        ),
    )


def _irreversible_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1 (reversible=False, catalyzed by p1) -> R2. Confirmed VERY_HIGH
    (IRREVERSIBLE_OUTPUT_ISOLATION, STRONG support, no opposition -- policy branch 3). The
    catalyst on R1 is not required for VERY_HIGH (reversibility alone triggers it) but makes
    R1 catalytically distinguished, so its Michaelis-Menten kinetic-law assignment declares
    real (placeholder) parameters -- needed by the parameter/kinetic-law ownership tests."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(id="r1", reversible=False), _reaction(id="r2")),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(reaction_id="r1", protein_id="p1"),),
    )


def _cycle_with_alternate_retained_path_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1 (reversible=False) -> R2 -> R3 -> R1, a 3-reaction cycle.

    Confirmed empirically: boundary::r1::r2 is VERY_HIGH
    (IRREVERSIBLE_OUTPUT_ISOLATION -- R1 is upstream there, and its own
    ``reversible=False`` fires); boundary::r2::r3 and boundary::r3::r1 are
    both LOW (R1 is *downstream* of R3, so R1's reversibility does not
    apply to that pair; no other evidence). The VERY_HIGH edge is
    therefore selected as a cut, but the retained r2-r3-r1 path keeps all
    three reactions in one connected component regardless -- exactly the
    "local cut decision does not guarantee global separation" case (see
    docs/10_module_decomposition.md, "Local boundary decisions versus
    global connectivity")."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="e"), _compound(id="f")),
        reactions=(
            _reaction(id="r1", reversible=False),
            _reaction(id="r2"),
            _reaction(id="r3"),
        ),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="e", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="f", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="f", role="REACTANT"),
            _participant(reaction_id="r3", compound_id="e", role="PRODUCT"),
        ),
    )


def _very_low_handoff() -> Agent1CuratedKnowledgeViewContract:
    """R1/R2, each catalyzed by a distinct protein (real, non-tentative Michaelis-Menten on
    both sides, same compartment, no branch/convergence, not transport). Confirmed VERY_LOW
    (STRONG_LOCAL_CONTINUITY, STRONG opposition, no support -- policy branch 1)."""
    return _handoff(
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
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r2", protein_id="p2"),
        ),
    )


def _disconnected_subnetworks_handoff() -> Agent1CuratedKnowledgeViewContract:
    """Two entirely separate mini-networks sharing no species at all -- r1/r2 vs r3/r4."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(
            _compound(id="a"),
            _compound(id="b"),
            _compound(id="c"),
            _compound(id="d"),
        ),
        reactions=(
            _reaction(id="r1"),
            _reaction(id="r2"),
            _reaction(id="r3"),
            _reaction(id="r4"),
        ),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r2", compound_id="a", role="PRODUCT"),
            _participant(reaction_id="r3", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r4", compound_id="b", role="PRODUCT"),
        ),
    )


def _decompose(handoff: Agent1CuratedKnowledgeViewContract) -> ModuleDecompositionSet:
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    return decompose_network(network, assignments, parameters, boundaries)


def _decompose_full(handoff: Agent1CuratedKnowledgeViewContract):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    decomposition_set = decompose_network(network, assignments, parameters, boundaries)
    return network, assignments, parameters, boundaries, decomposition_set


def _module(decomposition_set: ModuleDecompositionSet, module_id: str) -> ModuleSpecification:
    for module in decomposition_set.module_specifications:
        if module.module_id == module_id:
            return module
    raise AssertionError(f"no module with id {module_id!r}")


def _module_containing(decomposition_set: ModuleDecompositionSet, reaction_id: str) -> str:
    for module in decomposition_set.module_specifications:
        if reaction_id in module.reaction_ids:
            return module.module_id
    raise AssertionError(f"no module contains reaction {reaction_id!r}")


# --- Empty / trivial networks ------------------------------------------------------------------


def test_empty_network_produces_no_modules():
    decomposition_set = _decompose(_empty_network_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.module_ids == ()
    assert decomposition_set.module_specifications == ()


def test_single_isolated_reaction_becomes_its_own_module():
    decomposition_set = _decompose(_single_isolated_reaction_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.module_ids == ("module_001",)
    module = decomposition_set.module_specifications[0]
    assert module.reaction_ids == ("r1",)
    assert decomposition.interfaces == ()


# --- Likelihood interpretation (Step 8) -----------------------------------------------------


def test_low_likelihood_never_cuts():
    decomposition_set = _decompose(_linear_chain_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.module_ids == ("module_001",)
    assert decomposition.boundary_assessment_ids == ()
    assert decomposition.candidate_boundary_ids == ()
    assert decomposition_set.module_specifications[0].reaction_ids == ("r1", "r2")


def test_very_low_likelihood_never_cuts():
    decomposition_set = _decompose(_very_low_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.module_ids == ("module_001",)
    assert decomposition.boundary_assessment_ids == ()
    assert decomposition_set.module_specifications[0].reaction_ids == ("r1", "r2")


def test_medium_likelihood_preserved_as_candidate_not_cut():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _branch_point_handoff()
    )
    for assessment in boundaries.assessments:
        assert assessment.likelihood is BoundaryLikelihood.MEDIUM
    (decomposition,) = decomposition_set.decompositions
    # MEDIUM is never auto-cut -- all three reactions remain in one module.
    assert decomposition.module_ids == ("module_001",)
    assert decomposition.boundary_assessment_ids == ()
    assert set(decomposition.candidate_boundary_ids) == {
        a.boundary_id for a in boundaries.assessments
    }
    # Preserved, not discarded: the module itself discloses the unresolved ambiguity.
    module = decomposition_set.module_specifications[0]
    assert any("candidate boundary" in a for a in module.assumptions)


def test_high_likelihood_cuts():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _transport_handoff()
    )
    for assessment in boundaries.assessments:
        assert assessment.likelihood is BoundaryLikelihood.HIGH
    (decomposition,) = decomposition_set.decompositions
    assert len(decomposition.module_ids) == 3
    assert set(decomposition.boundary_assessment_ids) == {
        a.boundary_id for a in boundaries.assessments
    }
    assert decomposition.candidate_boundary_ids == ()


def test_very_high_likelihood_cuts():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    (assessment,) = boundaries.assessments
    assert assessment.likelihood is BoundaryLikelihood.VERY_HIGH
    (decomposition,) = decomposition_set.decompositions
    assert len(decomposition.module_ids) == 2
    assert decomposition.boundary_assessment_ids == (assessment.boundary_id,)


# --- Module counts -----------------------------------------------------------------------------


def test_two_modules_via_a_single_cut():
    decomposition_set = _decompose(_irreversible_handoff())
    assert len(decomposition_set.module_specifications) == 2
    modules = {m.module_id: m.reaction_ids for m in decomposition_set.module_specifications}
    assert set(modules.values()) == {("r1",), ("r2",)}


def test_many_modules_via_multiple_cuts():
    decomposition_set = _decompose(_transport_handoff())
    assert len(decomposition_set.module_specifications) == 3
    reaction_sets = {m.reaction_ids for m in decomposition_set.module_specifications}
    assert reaction_sets == {("r1",), ("rt",), ("r2",)}


def test_disconnected_subnetworks_become_separate_modules():
    decomposition_set = _decompose(_disconnected_subnetworks_handoff())
    assert len(decomposition_set.module_specifications) == 2
    reaction_sets = {m.reaction_ids for m in decomposition_set.module_specifications}
    assert reaction_sets == {("r1", "r2"), ("r3", "r4")}
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.interfaces == ()


# --- Deterministic ids and repeated execution ---------------------------------------------------


def test_module_ids_are_deterministic_module_NNN():
    decomposition_set = _decompose(_transport_handoff())
    assert {m.module_id for m in decomposition_set.module_specifications} == {
        "module_001",
        "module_002",
        "module_003",
    }


def test_repeated_execution_is_fully_deterministic():
    handoff = _transport_handoff()
    first = _decompose(handoff)
    second = _decompose(handoff)
    assert first.decompositions == second.decompositions
    assert first.module_specifications == second.module_specifications


def test_decomposition_id_never_random():
    decomposition_set = _decompose(_linear_chain_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.decomposition_id == "decomposition::" + decomposition_set.network_id
    assert decomposition.policy_version == MODULE_DECOMPOSITION_POLICY_VERSION


# --- Interfaces (Step 11-12) ---------------------------------------------------------------------


def test_interface_created_at_every_cut_boundary():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    (assessment,) = boundaries.assessments
    (decomposition,) = decomposition_set.decompositions
    (interface,) = decomposition.interfaces
    assert isinstance(interface, InterModuleBoundaryInterface)
    assert interface.boundary_id == assessment.boundary_id
    assert interface.boundary_likelihood is BoundaryLikelihood.VERY_HIGH
    assert interface.shared_species_ids == assessment.shared_species_ids
    upstream_module = _module_containing(decomposition_set, "r1")
    downstream_module = _module_containing(decomposition_set, "r2")
    assert interface.upstream_module_id == upstream_module
    assert interface.downstream_module_id == downstream_module
    assert interface.upstream_module_id != interface.downstream_module_id


def test_interface_species_are_shared_references_never_duplicated():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    known_species_ids = {s.species_id for s in network.species}
    (decomposition,) = decomposition_set.decompositions
    for interface in decomposition.interfaces:
        for species_id in interface.shared_species_ids:
            assert species_id in known_species_ids


def test_no_interface_within_a_single_module():
    decomposition_set = _decompose(_linear_chain_handoff())
    (decomposition,) = decomposition_set.decompositions
    assert decomposition.interfaces == ()
    assert decomposition_set.module_specifications[0].boundary_interface_ids == ()


def test_module_boundary_interface_ids_reference_real_interfaces():
    decomposition_set = _decompose(_irreversible_handoff())
    (decomposition,) = decomposition_set.decompositions
    interface_ids = {i.interface_id for i in decomposition.interfaces}
    for module in decomposition_set.module_specifications:
        for interface_id in module.boundary_interface_ids:
            assert interface_id in interface_ids


# --- Local cut decision vs. global connectivity (retained-edge invariant) ----------------------
#
# Three distinct concepts (never conflated -- see docs/10_module_decomposition.md, "Local
# boundary decisions versus global connectivity"):
#   A. BoundaryAssessment       -- Increment 6's local, qualitative evidence for one interface.
#   B. selected boundary        -- this policy's local decision to remove a HIGH/VERY_HIGH edge
#                                   from the connectivity graph (ModuleDecomposition
#                                   .boundary_assessment_ids).
#   C. InterModuleBoundaryInterface -- the *global* outcome: exists only when that removal
#                                   actually left the two reactions in different final modules.


def test_retained_edge_cannot_bridge_final_modules():
    """Test A: a LOW/MEDIUM/VERY_LOW boundary directly connecting R1/R2 is always unioned, so
    R1/R2 always end up in the same final connected component, and that boundary can never
    itself become an InterModuleBoundaryInterface -- proven for both a LOW edge (plain linear
    chain) and a MEDIUM edge (branch point)."""
    for handoff, expected_likelihood in (
        (_linear_chain_handoff(), BoundaryLikelihood.LOW),
        (_branch_point_handoff(), BoundaryLikelihood.MEDIUM),
    ):
        network, assignments, parameters, boundaries, decomposition_set = _decompose_full(handoff)
        assert boundaries.assessments
        for assessment in boundaries.assessments:
            assert assessment.likelihood is expected_likelihood
            upstream_module = _module_containing(decomposition_set, assessment.upstream_element_id)
            downstream_module = _module_containing(
                decomposition_set, assessment.downstream_element_id
            )
            assert upstream_module == downstream_module
        (decomposition,) = decomposition_set.decompositions
        interface_boundary_ids = {i.boundary_id for i in decomposition.interfaces}
        assert not interface_boundary_ids & {a.boundary_id for a in boundaries.assessments}
        assert decomposition.interfaces == ()


def test_simple_selected_boundary_separates_into_two_modules():
    """Test B: a simple linear R1 --HIGH/VERY_HIGH--> R2 with no alternate path is selected,
    R1/R2 become different modules, and exactly one InterModuleBoundaryInterface exists."""
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    (assessment,) = boundaries.assessments
    assert assessment.likelihood is BoundaryLikelihood.VERY_HIGH
    (decomposition,) = decomposition_set.decompositions
    assert assessment.boundary_id in decomposition.boundary_assessment_ids
    assert _module_containing(decomposition_set, "r1") != _module_containing(
        decomposition_set, "r2"
    )
    (interface,) = decomposition.interfaces
    assert interface.boundary_id == assessment.boundary_id


def test_selected_boundary_fails_to_separate_because_of_alternate_retained_path():
    """Test C: R1 --VERY_HIGH--> R2, but an alternate retained path R2-R3-R1 (both LOW) keeps
    all three reactions in one final module despite the selected cut. The VERY_HIGH boundary
    remains fully auditable in boundary_assessment_ids -- it is never discarded merely because
    it did not end up separating anything -- and no interface is created for it."""
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _cycle_with_alternate_retained_path_handoff()
    )
    by_pair = {(a.upstream_element_id, a.downstream_element_id): a for a in boundaries.assessments}
    cut_assessment = by_pair[("r1", "r2")]
    retained_assessments = [by_pair[("r2", "r3")], by_pair[("r3", "r1")]]
    assert cut_assessment.likelihood is BoundaryLikelihood.VERY_HIGH
    for retained in retained_assessments:
        assert retained.likelihood not in (BoundaryLikelihood.HIGH, BoundaryLikelihood.VERY_HIGH)

    (decomposition,) = decomposition_set.decompositions
    # Selected: remains recorded even though it will not separate anything.
    assert cut_assessment.boundary_id in decomposition.boundary_assessment_ids
    # Global outcome: all three reactions land in exactly one module (the retained path wins).
    assert len(decomposition.module_ids) == 1
    assert _module_containing(decomposition_set, "r1") == _module_containing(
        decomposition_set, "r2"
    )
    assert _module_containing(decomposition_set, "r2") == _module_containing(
        decomposition_set, "r3"
    )
    # No interface exists for the selected-but-non-separating boundary, nor for the retained ones.
    assert decomposition.interfaces == ()
    interface_boundary_ids = {i.boundary_id for i in decomposition.interfaces}
    assert cut_assessment.boundary_id not in interface_boundary_ids
    # A selected boundary_id legally omitted from every interface -- never enforced 1:1.
    assert set(decomposition.boundary_assessment_ids) - interface_boundary_ids == {
        cut_assessment.boundary_id
    }


def test_medium_candidate_boundary_never_becomes_an_interface():
    """Test D: MEDIUM stays a candidate only -- no cut, no interface."""
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _branch_point_handoff()
    )
    (decomposition,) = decomposition_set.decompositions
    assert set(decomposition.candidate_boundary_ids) == {
        a.boundary_id for a in boundaries.assessments
    }
    assert decomposition.boundary_assessment_ids == ()
    assert decomposition.interfaces == ()


def test_validate_references_rejects_interface_for_a_retained_boundary():
    """Direct unit test of the defensive backstop (Step 13): a hand-crafted
    InterModuleBoundaryInterface pointing at a LOW-likelihood assessment must be rejected, even
    though decompose_network itself can never construct one (the interface loop only ever
    considers cut-eligible assessments)."""
    from app.agent2.modules.decomposer import _validate_references

    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _linear_chain_handoff()
    )
    (low_assessment,) = boundaries.assessments
    assert low_assessment.likelihood is BoundaryLikelihood.LOW
    bogus_interface = InterModuleBoundaryInterface(
        interface_id="interface::bogus",
        upstream_module_id="module_001",
        downstream_module_id="module_001_other",
        boundary_id=low_assessment.boundary_id,
        boundary_likelihood=low_assessment.likelihood,
    )
    bad_decomposition = dataclasses.replace(
        decomposition_set.decompositions[0], interfaces=(bogus_interface,)
    )
    bad_module = ModuleSpecification(
        module_id="module_001_other", name="other", reaction_ids=("r2",)
    )
    bad_set = dataclasses.replace(
        decomposition_set,
        decompositions=(bad_decomposition,),
        module_specifications=(*decomposition_set.module_specifications, bad_module),
    )
    with pytest.raises(ModuleDecompositionReferenceError):
        _validate_references(
            bad_set,
            network=network,
            kinetic_laws=assignments,
            parameters=parameters,
            boundaries=boundaries,
        )


# --- Provenance and ownership (Steps 15-18) -----------------------------------------------------


def test_parameter_ownership_assigned_to_reactions_module():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    r1_params = {
        p.parameter_id for p in parameters.parameter_specifications if p.reaction_id == "r1"
    }
    assert r1_params  # r1's tentative mass-action default declares a placeholder "k"
    r1_module = _module(decomposition_set, _module_containing(decomposition_set, "r1"))
    assert r1_params <= set(r1_module.parameter_ids)
    other_module = _module(decomposition_set, _module_containing(decomposition_set, "r2"))
    assert not (r1_params & set(other_module.parameter_ids))


def test_kinetic_law_assignment_ownership_assigned_to_reactions_module():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    r1_module = _module(decomposition_set, _module_containing(decomposition_set, "r1"))
    r1_assignment_ids = {a.assignment_id for a in assignments.assignments if a.reaction_id == "r1"}
    assert r1_assignment_ids
    assert r1_assignment_ids <= set(r1_module.kinetic_law_assignment_ids)
    r2_module = _module(decomposition_set, _module_containing(decomposition_set, "r2"))
    assert not (r1_assignment_ids & set(r2_module.kinetic_law_assignment_ids))


def test_enzyme_state_ownership_never_split_across_modules():
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
        enzyme_states=(CuratedEnzymeState(id="es1", state_type="phosphorylated"),),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id=None, enzyme_state_id="es1"),
        ),
    )
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(handoff)
    r1_module = _module(decomposition_set, _module_containing(decomposition_set, "r1"))
    r2_module = _module(decomposition_set, _module_containing(decomposition_set, "r2"))
    assert "es1" in r1_module.enzyme_state_ids
    assert "es1" not in r2_module.enzyme_state_ids


def test_compartment_ownership_reflects_reactions_actually_present():
    decomposition_set = _decompose(_transport_handoff())
    r1_module = _module(decomposition_set, _module_containing(decomposition_set, "r1"))
    rt_module = _module(decomposition_set, _module_containing(decomposition_set, "rt"))
    r2_module = _module(decomposition_set, _module_containing(decomposition_set, "r2"))
    assert r1_module.compartment_ids == ("cyto",)
    assert set(rt_module.compartment_ids) == {"cyto", "mito"}
    assert r2_module.compartment_ids == ("mito",)


def test_provenance_preserved_nothing_anonymous():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _irreversible_handoff()
    )
    for module in decomposition_set.module_specifications:
        assert module.reaction_ids
        assert module.source_boundary_ids
        for boundary_id in module.source_boundary_ids:
            assert boundary_id in {a.boundary_id for a in boundaries.assessments}


# --- Full-network-is-authoritative (Step 6) -----------------------------------------------------


def test_modules_reference_full_network_objects_never_copy_them():
    network, assignments, parameters, boundaries, decomposition_set = _decompose_full(
        _linear_chain_handoff()
    )
    module = decomposition_set.module_specifications[0]
    network_species_ids = {s.species_id for s in network.species}
    assert set(module.species_ids) <= network_species_ids
    network_reaction_ids = {r.reaction_id for r in network.reactions}
    assert set(module.reaction_ids) <= network_reaction_ids


# --- Validation (Step 20) ------------------------------------------------------------------------


def test_rejects_network_id_mismatch():
    network, assignments, parameters, boundaries, _ = _decompose_full(_linear_chain_handoff())
    mismatched = dataclasses.replace(parameters, network_id="other-network")
    with pytest.raises(ModuleDecompositionReferenceError):
        decompose_network(network, assignments, mismatched, boundaries)


def test_module_decomposition_set_rejects_duplicate_decomposition_ids():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test",
        policy_version="module-decomposition-v1",
        created_from_network_id="n1",
    )
    with pytest.raises(ValueError):
        ModuleDecompositionSet(
            network_id="n1",
            boundary_policy_version="boundary-v3",
            decomposition_policy_version="module-decomposition-v1",
            decompositions=(decomposition, decomposition),
        )


def test_module_decomposition_set_rejects_duplicate_module_ids():
    module = ModuleSpecification(module_id="mod-1", name="m", reaction_ids=("r1",))
    with pytest.raises(ValueError):
        ModuleDecompositionSet(
            network_id="n1",
            boundary_policy_version="boundary-v3",
            decomposition_policy_version="module-decomposition-v1",
            decompositions=(),
            module_specifications=(module, module),
        )


def test_module_decomposition_rejects_dangling_module_id_reference():
    with pytest.raises(ValueError):
        ModuleDecomposition(
            decomposition_id="d1",
            name="test",
            policy_version="module-decomposition-v1",
            created_from_network_id="n1",
            module_ids=("mod-1", "mod-1"),
        )


def test_inter_module_boundary_interface_rejects_same_module_on_both_sides():
    with pytest.raises(ValueError):
        InterModuleBoundaryInterface(
            interface_id="i1",
            upstream_module_id="mod-1",
            downstream_module_id="mod-1",
            boundary_id="b1",
            boundary_likelihood=BoundaryLikelihood.HIGH,
        )


def test_inter_module_boundary_interface_requires_real_likelihood_enum():
    with pytest.raises(TypeError):
        InterModuleBoundaryInterface(
            interface_id="i1",
            upstream_module_id="mod-1",
            downstream_module_id="mod-2",
            boundary_id="b1",
            boundary_likelihood="HIGH",
        )


def test_module_decomposition_rejects_overlapping_selected_and_candidate_ids():
    with pytest.raises(ValueError):
        ModuleDecomposition(
            decomposition_id="d1",
            name="test",
            policy_version="module-decomposition-v1",
            created_from_network_id="n1",
            boundary_assessment_ids=("b1",),
            candidate_boundary_ids=("b1",),
        )


def test_module_specification_rejects_dangling_new_field_duplicates():
    with pytest.raises(ValueError):
        ModuleSpecification(
            module_id="mod-1",
            name="m",
            reaction_ids=("r1",),
            enzyme_state_ids=("es1", "es1"),
        )


# --- No numeric/probabilistic decomposition -----------------------------------------------------


def test_no_numeric_score_anywhere_in_decomposition():
    decomposition_set = _decompose(_transport_handoff())
    for decomposition in decomposition_set.decompositions:
        assert not hasattr(decomposition, "score")
        assert not hasattr(decomposition, "probability")
    for module in decomposition_set.module_specifications:
        assert not hasattr(module, "score")
        assert not hasattr(module, "probability")
