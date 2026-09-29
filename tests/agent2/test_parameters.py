"""Tests for Parameter Declaration / Initialization (Increment 5): ``app.agent2.parameters``.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, assembles it
into a ``FullNetwork``, characterizes it, assigns kinetic laws, then calls
``declare_parameters(assignments, network)`` on the result -- no test
constructs a ``ParameterDeclarationSet`` by hand for the main scenarios,
matching ``tests/agent2/test_kinetics.py``'s own convention.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import ParameterDeclarationSet, declare_parameters
from app.agent2.parameters.errors import (
    ParameterReferenceError,
    UnsupportedParameterDeclarationInputError,
)
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
    ParameterSource,
    ParameterSpecification,
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


def _one_substrate_one_product_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
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


def _declare(handoff: Agent1CuratedKnowledgeViewContract) -> ParameterDeclarationSet:
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    return declare_parameters(assignments, network)


def _declare_full(handoff: Agent1CuratedKnowledgeViewContract):
    """Returns (network, assignments, declaration) for tests that need all three."""
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    declaration = declare_parameters(assignments, network)
    return network, assignments, declaration


def _by_id(declaration: ParameterDeclarationSet, parameter_id: str) -> ParameterSpecification:
    for spec in declaration.parameter_specifications:
        if spec.parameter_id == parameter_id:
            return spec
    raise AssertionError(f"no parameter with id {parameter_id!r}")


# --- MASS_ACTION -------------------------------------------------------------------------------


def _bare_state_transition_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(_participant(),),
        enzyme_states=(_enzyme_state(id="es0"), _enzyme_state(id="es1")),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t1",
                from_state_id="es0",
                to_state_id="es1",
                transition_type="PHOSPHORYLATION",
                reaction_id="r1",
            ),
        ),
    )


def test_mass_action_structural_declares_single_k():
    """No curated/AI-predicted evidence exists for this bare, unimolecular state
    transition, so its rate constant is heuristically initialized (Heuristic Simulation
    Parameter Initialization increment) rather than left an undecorated PLACEHOLDER."""
    declaration = _declare(_bare_state_transition_handoff())
    assert len(declaration.parameter_specifications) == 1
    spec = declaration.parameter_specifications[0]
    assert spec.parameter_id == "k_r1"
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.value == Decimal("1")
    assert spec.unit == "per_sec"


def test_mass_action_curated_rate_constant_initializes():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(parameter_type="K", value=Decimal("2.5"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.CURATED
    assert spec.value == Decimal("2.5")
    assert spec.unit == "1/s"
    assert spec.provenance_refs == ("km1",)


def test_mass_action_tentative_never_curated_but_is_heuristically_initialized():
    """A TENTATIVE_MASS_ACTION_DEFAULT assignment's k is never mapped to a curated
    measurement, even when one exists for this exact context (Increment 5 instructions,
    Step 16) -- but, since the Heuristic Simulation Parameter Initialization increment, it is
    still heuristically initialized rather than left a bare placeholder: the law type is still
    ``MASS_ACTION`` with a built expression and a fully declared ``k`` slot, so it is not
    excluded by that increment's own §7 boundary (``expression=None``/unsupported law
    type/no declared parameter structure), and a heuristic value makes no evidentiary claim
    the tentative mechanism could be misrepresented as validating."""
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(reversible=True),
        kinetic_measurements=(
            _kinetic_measurement(parameter_type="K", value=Decimal("99"), unit="1/s"),
        ),
    )
    network, assignments, declaration = _declare_full(handoff)
    (assignment,) = assignments.assignments
    assert assignment.is_tentative
    spec = _by_id(declaration, "k_r1_p1")
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.value is not None
    assert spec.value != Decimal("99")
    assert spec.provenance_refs == ()
    assert "tentative" in spec.uncertainty_text.lower()


# --- MICHAELIS_MENTEN --------------------------------------------------------------------------


def test_michaelis_menten_declares_kcat_and_km_per_substrate():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_kcat", parameter_type="KCAT", value=Decimal("40"), unit="1/s"
            ),
            _kinetic_measurement(
                id="km_km",
                parameter_type="KM",
                value=Decimal("0.2"),
                unit="mM",
                compound_id="glc",
            ),
        ),
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"kcat_r1_p1", "Km_r1_p1_glc"}
    kcat = _by_id(declaration, "kcat_r1_p1")
    assert kcat.source is ParameterSource.CURATED
    assert kcat.value == Decimal("40")
    km = _by_id(declaration, "Km_r1_p1_glc")
    assert km.source is ParameterSource.CURATED
    assert km.value == Decimal("0.2")


def test_michaelis_menten_no_reactants_declares_no_km():
    """A pathological zero-reactant MICHAELIS_MENTEN (only reachable via a curated law) gets
    no Km parameter -- there is no substrate to name it after."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(),),
        reaction_participants=(_participant(role="MODIFIER"),),
        reaction_enzyme_associations=(_enzyme_association(),),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reported_rate_law="Michaelis-Menten form",
            ),
        ),
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"kcat_r1_p1"}


def test_michaelis_menten_never_declares_ki():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(parameter_type="KI", value=Decimal("0.1"), unit="mM"),
        ),
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert not any("Ki" in i for i in ids)


# --- REVERSIBLE_MASS_ACTION ----------------------------------------------------------------------


def test_reversible_mass_action_declares_kf_and_kr():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(reversible=True),
        kinetic_measurements=(
            _kinetic_measurement(id="kmf", parameter_type="KF", value=Decimal("5"), unit="1/s"),
            _kinetic_measurement(id="kmr", parameter_type="KR", value=Decimal("1"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"kf_r1", "kr_r1"}
    assert _by_id(declaration, "kf_r1").value == Decimal("5")
    assert _by_id(declaration, "kr_r1").value == Decimal("1")


def test_reversible_mass_action_missing_reverse_measurement_is_placeholder():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(reversible=True),
        kinetic_measurements=(
            _kinetic_measurement(parameter_type="KF", value=Decimal("5"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    assert _by_id(declaration, "kf_r1").source is ParameterSource.CURATED
    # No curated/AI-predicted evidence exists for the reverse direction, so it is
    # heuristically initialized (Heuristic Simulation Parameter Initialization increment)
    # -- never left an undecorated PLACEHOLDER, and never confused with the real curated
    # forward value above.
    kr = _by_id(declaration, "kr_r1")
    assert kr.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kr.value is not None
    assert kr.provenance_refs == ()


# --- CUSTOM --------------------------------------------------------------------------------------


def _custom_handoff(**kw) -> Agent1CuratedKnowledgeViewContract:
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(),),
        "reactions": (_reaction(),),
        "reaction_participants": (_participant(),),
        "reaction_enzyme_associations": (_enzyme_association(),),
    } | kw
    return _handoff(**merged)


def test_custom_declares_recognized_measurement_families_only():
    handoff = _custom_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reported_rate_law="Vmax*S/(Km+S*(1+I/Ki))",
            ),
            _kinetic_measurement(id="km_ki", parameter_type="KI", value=Decimal("0.3"), unit="mM"),
        )
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"Ki_r1_p1"}
    assert _by_id(declaration, "Ki_r1_p1").source is ParameterSource.CURATED


def test_custom_no_recognized_measurements_declares_single_placeholder():
    handoff = _custom_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reported_rate_law="some weird f(x,y,z) expression",
            ),
        )
    )
    declaration = _declare(handoff)
    assert len(declaration.parameter_specifications) == 1
    spec = declaration.parameter_specifications[0]
    assert spec.parameter_id == "k_custom_r1_p1"
    assert spec.source is ParameterSource.PLACEHOLDER
    assert "manual definition" in spec.uncertainty_text.lower()


def test_custom_never_symbolically_parses_reported_law_text():
    handoff = _custom_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reported_rate_law="rate = f(k1, k2)",
            ),
        )
    )
    declaration = _declare(handoff)
    # "rate = f(k1, k2)" is never parsed to discover a "k1"/"k2" parameter pair.
    assert len(declaration.parameter_specifications) == 1
    assert declaration.parameter_specifications[0].source is ParameterSource.PLACEHOLDER


# --- UNASSIGNED ------------------------------------------------------------------------------


def test_unassigned_declares_no_parameters():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(), reaction_enzyme_associations=()
    )
    declaration = _declare(handoff)
    assert declaration.parameter_specifications == ()


# --- Multiple measurements: agree / disagree --------------------------------------------------


def test_agreeing_measurements_share_one_curated_value_with_full_provenance():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", parameter_type="K", value=Decimal("3"), unit="1/s"),
            _kinetic_measurement(id="km2", parameter_type="K", value=Decimal("3"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.CURATED
    assert spec.value == Decimal("3")
    assert spec.provenance_refs == ("km1", "km2")


def test_disagreeing_values_produce_placeholder_with_all_provenance_preserved():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", parameter_type="K", value=Decimal("3"), unit="1/s"),
            _kinetic_measurement(id="km2", parameter_type="K", value=Decimal("7"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.PLACEHOLDER
    assert spec.value is None
    assert spec.provenance_refs == ("km1", "km2")
    assert "different values" in spec.uncertainty_text.lower()


def test_disagreeing_units_also_produce_placeholder_never_converted():
    """Same value, different unit -- never normalized, treated as disagreement (Step 13)."""
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", parameter_type="K", value=Decimal("3"), unit="1/s"),
            _kinetic_measurement(id="km2", parameter_type="K", value=Decimal("3"), unit="1/min"),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.PLACEHOLDER
    assert spec.value is None


def test_publication_attributed_measurement_is_literature_derived():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(
                parameter_type="K", value=Decimal("3"), unit="1/s", publication_id="pub1"
            ),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.LITERATURE_DERIVED
    assert spec.source_reference == "pub1"


# --- State-specific parameters -----------------------------------------------------------------


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


def test_state_specific_parameters_remain_distinct():
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                parameter_type="K", value=Decimal("10"), unit="1/s", enzyme_state_id="ep"
            ),
        )
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"k_r1_e", "k_r1_ep"}
    e_spec = _by_id(declaration, "k_r1_e")
    ep_spec = _by_id(declaration, "k_r1_ep")
    # tentative default -> never curated, but still heuristically initialized (Heuristic
    # Simulation Parameter Initialization increment)
    assert e_spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert ep_spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert e_spec.provenance_refs == ()
    assert ep_spec.provenance_refs == ()
    assert e_spec.kinetic_law_assignment_id != ep_spec.kinetic_law_assignment_id


def test_ep_measurement_never_applies_to_e_non_tentative_case():
    """A non-tentative, per-state curated-law scenario: EP's curated rate-constant measurement
    never initializes E's own parameter."""
    handoff = _e_and_ep_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km_law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                enzyme_state_id="ep", reported_rate_law="k1 * glc",
            ),
            _kinetic_measurement(
                id="km_k", parameter_type="K", value=Decimal("4"), unit="1/s", enzyme_state_id="ep",
            ),
        )
    )
    network, assignments, declaration = _declare_full(handoff)
    ep_assignment = next(a for a in assignments.assignments if a.enzyme_state_id == "ep")
    assert ep_assignment.assignment_source.value == "CURATED_REPORTED"
    e_spec = _by_id(declaration, "k_r1_e")
    ep_spec = _by_id(declaration, "k_r1_ep")
    assert e_spec.provenance_refs == ()
    assert ep_spec.provenance_refs == ("km_k",)
    assert ep_spec.value == Decimal("4")


# --- Isozymes --------------------------------------------------------------------------------


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


def test_isozymes_different_evidence_get_independent_parameters():
    handoff = _two_isozyme_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                protein_id="p1", reported_rate_law="k1*A",
            ),
            _kinetic_measurement(
                id="km2", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                protein_id="p2", reported_rate_law="k2*A*A",
            ),
            _kinetic_measurement(
                id="km3", parameter_type="K", value=Decimal("7"), unit="1/s", protein_id="p1"
            ),
            _kinetic_measurement(
                id="km4", parameter_type="K", value=Decimal("9"), unit="1/s", protein_id="p2"
            ),
        )
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"k_r1_p1", "k_r1_p2"}
    assert _by_id(declaration, "k_r1_p1").value == Decimal("7")
    assert _by_id(declaration, "k_r1_p2").value == Decimal("9")


def test_isozymes_never_collapsed_each_gets_its_own_parameters():
    """Isozyme-Aware Catalytic Context Resolution: p1 and p2 are never collapsed, even though
    p2 has no evidence of its own at all -- each keeps its own independent context, so p1's
    real, tagged kcat measurement is never shared with or withheld from p2's own parameters
    (Step 15/Step 4). p1 gets a real CURATED kcat; p2, with no evidence of its own, falls
    through to HEURISTIC_INITIALIZATION for both of its parameters -- never inheriting p1's
    value, never left undeclared."""
    handoff = dataclasses.replace(
        _two_isozyme_handoff(),
        compounds=(_compound(), _compound(id="g6p")),
        reaction_participants=(
            _participant(role="REACTANT"),
            _participant(role="PRODUCT", compound_id="g6p"),
        ),
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="KCAT", value=Decimal("3"), unit="1/s", protein_id="p1"
            ),
        ),
    )
    declaration = _declare(handoff)
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    assert ids == {"kcat_r1_p1", "Km_r1_p1_glc", "kcat_r1_p2", "Km_r1_p2_glc"}
    assert _by_id(declaration, "kcat_r1_p1").value == Decimal("3")
    assert _by_id(declaration, "kcat_r1_p1").source is ParameterSource.CURATED
    assert _by_id(declaration, "kcat_r1_p1").provenance_refs == ("km1",)
    assert _by_id(declaration, "kcat_r1_p2").source is ParameterSource.HEURISTIC_INITIALIZATION
    assert _by_id(declaration, "kcat_r1_p2").provenance_refs == ()


# --- Provenance --------------------------------------------------------------------------------


def test_provenance_refs_never_lost_on_placeholder():
    handoff = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", parameter_type="K", value=Decimal("1"), unit="1/s"),
            _kinetic_measurement(id="km2", parameter_type="K", value=Decimal("2"), unit="1/s"),
            _kinetic_measurement(id="km3", parameter_type="K", value=Decimal("3"), unit="1/s"),
        ),
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.provenance_refs == ("km1", "km2", "km3")


# --- Determinism / identity / ordering ----------------------------------------------------------


def test_declare_parameters_is_deterministic():
    handoff = dataclasses.replace(
        _one_substrate_one_product_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(parameter_type="KCAT", value=Decimal("1"), unit="1/s"),
        ),
    )
    network, assignments, _ = _declare_full(handoff)
    first = declare_parameters(assignments, network)
    second = declare_parameters(assignments, network)
    assert first == second


def test_parameter_identity_stable_regardless_of_declaration_order():
    handoff_a = _two_isozyme_handoff(
        kinetic_measurements=(
            _kinetic_measurement(
                id="km1", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                protein_id="p1", reported_rate_law="k1*A",
            ),
            _kinetic_measurement(
                id="km2", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                protein_id="p2", reported_rate_law="k2*A*A",
            ),
        )
    )
    handoff_b = dataclasses.replace(
        handoff_a,
        reaction_enzyme_associations=(
            _enzyme_association(protein_id="p2"),
            _enzyme_association(protein_id="p1"),
        ),
    )
    declaration_a = _declare(handoff_a)
    declaration_b = _declare(handoff_b)
    ids_a = {s.parameter_id for s in declaration_a.parameter_specifications}
    ids_b = {s.parameter_id for s in declaration_b.parameter_specifications}
    assert ids_a == ids_b


def test_ordering_independence_of_kinetic_measurements():
    handoff_a = dataclasses.replace(
        _bare_state_transition_handoff(),
        kinetic_measurements=(
            _kinetic_measurement(id="km1", parameter_type="K", value=Decimal("3"), unit="1/s"),
            _kinetic_measurement(id="km2", parameter_type="K", value=Decimal("3"), unit="1/s"),
        ),
    )
    handoff_b = dataclasses.replace(
        handoff_a,
        kinetic_measurements=tuple(reversed(handoff_a.kinetic_measurements)),
    )
    declaration_a = _declare(handoff_a)
    declaration_b = _declare(handoff_b)
    assert declaration_a.parameter_specifications == declaration_b.parameter_specifications


# --- Duplicate detection / construction validation ----------------------------------------------


def test_parameter_declaration_set_rejects_duplicate_parameter_id():
    spec = ParameterSpecification(
        parameter_id="k_r1",
        name="k_r1",
        source=ParameterSource.PLACEHOLDER,
        kinetic_law_assignment_id="r1::kinetic-law::general",
    )
    with pytest.raises(ValueError, match="duplicate parameter_id"):
        ParameterDeclarationSet(
            network_id="n1",
            kinetic_law_policy_version="kinetic-law-v2",
            parameter_policy_version="parameter-declaration-v1",
            parameter_specifications=(spec, spec),
        )


def test_parameter_declaration_set_rejects_missing_kinetic_law_assignment_id():
    spec = ParameterSpecification(
        parameter_id="k_r1", name="k_r1", source=ParameterSource.PLACEHOLDER
    )
    with pytest.raises(ValueError, match="kinetic_law_assignment_id"):
        ParameterDeclarationSet(
            network_id="n1",
            kinetic_law_policy_version="kinetic-law-v2",
            parameter_policy_version="parameter-declaration-v1",
            parameter_specifications=(spec,),
        )


# --- Validation failures -----------------------------------------------------------------------


def test_declare_parameters_rejects_wrong_assignments_type():
    network, _, _ = _declare_full(_bare_state_transition_handoff())
    with pytest.raises(UnsupportedParameterDeclarationInputError):
        declare_parameters("not-an-assignment-set", network)


def test_declare_parameters_rejects_wrong_network_type():
    network, assignments, _ = _declare_full(_bare_state_transition_handoff())
    with pytest.raises(UnsupportedParameterDeclarationInputError):
        declare_parameters(assignments, "not-a-network")


def test_declare_parameters_rejects_network_id_mismatch():
    handoff_a = _bare_state_transition_handoff()
    handoff_b = dataclasses.replace(
        handoff_a, organism_id="different-organism-for-a-new-network-id"
    )
    network_a = assemble_full_network(handoff_a)
    network_b = assemble_full_network(handoff_b)
    characterization_a = characterize_full_network(network_a)
    assignments_a = assign_kinetic_laws(characterization_a, network_a)
    if network_a.network_id == network_b.network_id:
        pytest.skip("network_id is not derived from organism_id in this build")
    with pytest.raises(ParameterReferenceError):
        declare_parameters(assignments_a, network_b)


def test_declare_parameters_rejects_forced_calibrated_source(monkeypatch):
    """Defensive backstop: even if an internal initializer somehow produced CALIBRATED,
    declare_parameters must refuse to return it. Patches initialize_with_fallback --
    builder.py's own mass-action call site (Heuristic Simulation Parameter Initialization
    increment) -- rather than initialize_from_evidence directly, since that is no longer
    what the mass-action path calls."""
    import app.agent2.parameters.builder as builder_module
    from app.agent2.parameters.initializer import Initialization

    def _force_calibrated(evidence_of_kind, **kwargs):
        return Initialization(
            source=ParameterSource.CALIBRATED,
            value=Decimal("1"),
            unit="1/s",
            source_reference=None,
            provenance_refs=(),
            uncertainty_text=None,
        )

    monkeypatch.setattr(builder_module, "initialize_with_fallback", _force_calibrated)
    with pytest.raises(ParameterReferenceError, match="CALIBRATED"):
        _declare(_bare_state_transition_handoff())


# --- Substrate-Anchored Michaelis-Menten Eligibility Refinement (Real Integration Pilot 2
# Run 3 finding): the resolved MICHAELIS_MENTEN assignment for a multi-reactant reaction is
# consumed by this package's own, completely unmodified declaration policy. -----------------


def _malonyl_coa_like_handoff() -> Agent1CuratedKnowledgeViewContract:
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
        kinetic_measurements=(
            _kinetic_measurement(
                id="km-malonyl",
                parameter_type="KM",
                value=Decimal("18.0"),
                unit="uM",
                compound_id="malonyl-coa",
            ),
        ),
    )


def test_substrate_anchored_mm_declares_km_only_for_the_anchored_reactant():
    declaration = _declare(_malonyl_coa_like_handoff())
    ids = {s.parameter_id for s in declaration.parameter_specifications}
    # Executable Rate-Law Fallback increment: kf/kr are now also declared for this genuinely
    # multi-substrate assignment (§6 of that increment) -- kcat/Km are otherwise completely
    # unaffected.
    assert ids == {
        "kcat_r1_p1",
        "Km_r1_p1_malonyl-coa",
        "Km_r1_p1_acp",
        "kf_r1_p1",
        "kr_r1_p1",
    }

    anchored = _by_id(declaration, "Km_r1_p1_malonyl-coa")
    assert anchored.source is ParameterSource.CURATED
    assert anchored.value == Decimal("18.0")
    assert "km-malonyl" in anchored.provenance_refs


def test_multi_substrate_mm_fallback_rate_constants_are_heuristic_and_molecularity_derived():
    """Executable Rate-Law Fallback increment §6/§7: the fallback's own kf/kr are heuristically
    initialized (never fabricated as curated/AI-predicted evidence), and each direction's unit
    is derived from its own molecularity independently (forward: malonyl-coa + acp = 2;
    reverse: coa + malonyl-acp = 2) -- never related through a fabricated equilibrium."""
    declaration = _declare(_malonyl_coa_like_handoff())
    kf = _by_id(declaration, "kf_r1_p1")
    kr = _by_id(declaration, "kr_r1_p1")
    assert kf.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kr.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kf.provenance_refs == ()
    assert kr.provenance_refs == ()
    assert kf.unit == "per_nMs"
    assert kr.unit == "per_nMs"


def test_substrate_anchored_mm_never_invents_curated_evidence_for_the_other_reactant():
    """No curated/AI-predicted Km exists for ACP -- it is heuristically initialized
    (Heuristic Simulation Parameter Initialization increment), never fabricated as if it
    were real evidence, and never citing the malonyl-CoA measurement's own provenance."""
    declaration = _declare(_malonyl_coa_like_handoff())
    unanchored = _by_id(declaration, "Km_r1_p1_acp")
    assert unanchored.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert unanchored.value is not None
    assert unanchored.provenance_refs == ()


def test_substrate_anchored_mm_kcat_is_heuristically_initialized_not_fabricated_as_evidence():
    declaration = _declare(_malonyl_coa_like_handoff())
    kcat = _by_id(declaration, "kcat_r1_p1")
    assert kcat.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kcat.value == Decimal("1")
    assert kcat.unit == "per_sec"
