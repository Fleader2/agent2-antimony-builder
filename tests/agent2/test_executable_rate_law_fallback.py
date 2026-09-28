"""Tests for the Executable Rate-Law Fallback increment.

Every test builds an ``Agent1CuratedKnowledgeViewContract`` and runs it through the full real
pipeline (``assemble_full_network`` -> ``characterize_full_network`` -> ``assign_kinetic_laws``
-> ``declare_parameters`` -> ``assess_boundaries`` -> ``decompose_network`` ->
``assemble_model_specification``), matching every other Agent 2 test file's own convention.
This file's own private fixtures deliberately mirror the shapes ``tests/agent2
/test_model_specification.py``'s own identical helpers already use (never imported, per this
codebase's per-test-file fixture convention).
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from app.agent2.antimony import generate_antimony
from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.model_specification import assemble_model_specification
from app.agent2.model_specification.mapping import (
    EXECUTABLE_RATE_LAW_FALLBACK,
    MULTI_SUBSTRATE_MM_SIMULATION_FALLBACK,
)
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    AntimonyArtifactReadiness,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    KineticLawType,
    ParameterSource,
)

# --- Fixtures ------------------------------------------------------------------------------


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


def _measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km1",
        "parameter_type": "KM",
        "value": Decimal("1"),
        "unit": "mM",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _assemble_full(handoff: Agent1CuratedKnowledgeViewContract):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    modules = decompose_network(network, assignments, parameters, boundaries)
    model = assemble_model_specification(network, assignments, parameters, boundaries, modules)
    return network, assignments, parameters, boundaries, modules, model


def _assemble(handoff: Agent1CuratedKnowledgeViewContract):
    return _assemble_full(handoff)[-1]


def _multi_substrate_mm_handoff(**reaction_overrides) -> Agent1CuratedKnowledgeViewContract:
    """Two reactants, one product, catalyzed, curated reported law text explicitly naming
    "Michaelis-Menten" -- the same real trigger condition as the real malonyl-CoA case:
    genuinely multi-substrate, so no single kcat/Km combining algebra is ever asserted."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b"), _compound(id="c")),
        reactions=(_reaction(**reaction_overrides),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="REACTANT"),
            _participant(compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
        kinetic_measurements=(_measurement(parameter_type="RATE_LAW", value=Decimal("0"),
                                            unit="n/a", reported_rate_law="Michaelis-Menten kinetics"),),
    )


def _single_substrate_mm_handoff() -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
    )


def _malonyl_coa_like_handoff() -> Agent1CuratedKnowledgeViewContract:
    """A Run-6-shaped regression mirroring the real yeast ACC1/malonyl-CoA:[acp]
    S-malonyltransferase reaction (Substrate-Anchored Michaelis-Menten Eligibility
    Refinement increment's own fixture): 2 reactants, 2 products, one real, literature-
    adjacent curated Km anchored to malonyl-CoA, uncurated (assumed) reversibility."""
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
            _measurement(
                id="km-malonyl",
                parameter_type="KM",
                value=Decimal("18.0"),
                unit="uM",
                compound_id="malonyl-coa",
            ),
        ),
    )


def _custom_handoff() -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        kinetic_measurements=(
            _measurement(
                parameter_type="RATE_LAW",
                value=Decimal("0"),
                unit="n/a",
                reported_rate_law="some_proprietary_fn(a, b)",
            ),
        ),
    )


# --- Eligibility / expression construction --------------------------------------------------


def test_multi_reactant_mm_with_no_expression_gets_a_fallback():
    model = _assemble(_multi_substrate_mm_handoff(reversible=False))
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MICHAELIS_MENTEN
    assert law.expression is not None
    assert law.has_expression


def test_single_substrate_mm_unchanged_no_fallback_parameters():
    model = _assemble(_single_substrate_mm_handoff())
    (law,) = model.kinetic_laws
    ids = {p.parameter_id for p in model.parameters}
    assert ids == {"kcat_r1_p1", "Km_r1_p1_a"}
    assert "-" not in law.expression
    assert law.expression == "kcat_r1_p1 * a::in::cyto / (Km_r1_p1_a + a::in::cyto)"


def test_existing_mass_action_expression_unaffected():
    """A bare, unimolecular, non-enzymatic state transition -- MASS_ACTION's own expression
    construction is completely untouched by this increment (only the MICHAELIS_MENTEN branch
    of ``build_expression_and_species`` changed)."""
    handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"),),
        reactions=(_reaction(),),
        reaction_participants=(_participant(compound_id="a", role="REACTANT"),),
        enzyme_states=(
            CuratedEnzymeState(id="es0", state_type="PHOSPHORYLATED", protein_id="p1"),
            CuratedEnzymeState(id="es1", state_type="PHOSPHORYLATED", protein_id="p1"),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t1", from_state_id="es0", to_state_id="es1",
                transition_type="PHOSPHORYLATION", reaction_id="r1",
            ),
        ),
    )
    model = _assemble(handoff)
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.MASS_ACTION
    assert law.expression == "k_r1 * a::in::cyto"


def test_custom_unsupported_mechanism_remains_unresolved():
    """§2/§7: never applied to CUSTOM -- the raw text is preserved verbatim (pre-existing,
    unmodified policy), never touched by this increment's fallback."""
    model = _assemble(_custom_handoff())
    (law,) = model.kinetic_laws
    assert law.law_type is KineticLawType.CUSTOM
    assert law.expression == "some_proprietary_fn(a, b)"

    package = generate_antimony(model)
    assert package.full_antimony.readiness is not AntimonyArtifactReadiness.EXECUTABLE
    assert law.reaction_id in package.full_antimony.unresolved_reaction_ids


# --- Reversibility ---------------------------------------------------------------------------


def test_curated_irreversible_reaction_gets_forward_only_fallback():
    model = _assemble(_multi_substrate_mm_handoff(reversible=False))
    (law,) = model.kinetic_laws
    assert "-" not in law.expression
    parameter_ids = {p.parameter_id for p in model.parameters}
    assert "k_r1_p1" in parameter_ids
    assert "kf_r1_p1" not in parameter_ids
    assert "kr_r1_p1" not in parameter_ids
    (k,) = (p for p in model.parameters if p.parameter_id == "k_r1_p1")
    assert k.source is ParameterSource.HEURISTIC_INITIALIZATION


def test_curated_reversible_reaction_gets_forward_and_reverse_fallback():
    model = _assemble(_multi_substrate_mm_handoff(reversible=True))
    (law,) = model.kinetic_laws
    assert " - " in law.expression
    parameter_ids = {p.parameter_id for p in model.parameters}
    assert {"kf_r1_p1", "kr_r1_p1"}.issubset(parameter_ids)
    assert "k_r1_p1" not in parameter_ids


def test_assumed_reversible_reaction_gets_reversible_fallback_and_stays_disclosed():
    """Curated `reversible=None` -> assumed reversible for model-construction purposes only
    (increment §7: "assumed reversible -> reversible fallback, explicitly retaining the
    reversibility assumption")."""
    model = _assemble(_multi_substrate_mm_handoff())
    (law,) = model.kinetic_laws
    assert " - " in law.expression
    reason_codes = {a.reason_code for a in model.model_assumptions}
    assert "REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE" in reason_codes
    assert MULTI_SUBSTRATE_MM_SIMULATION_FALLBACK in reason_codes


def test_no_equilibrium_constant_ever_fabricated():
    for reversible in (True, False, None):
        model = _assemble(_multi_substrate_mm_handoff(reversible=reversible))
        parameter_ids = {p.parameter_id for p in model.parameters}
        assert not any("keq" in pid.lower() for pid in parameter_ids)


def test_no_unsupported_mechanism_algebra_invented():
    """Never Hill (^, exponents), never anything beyond substituted species/parameter ids
    joined by ``*``/``-``/whitespace -- the smallest generic mass-action-style form only."""
    for reversible in (True, False, None):
        model = _assemble(_multi_substrate_mm_handoff(reversible=reversible))
        (law,) = model.kinetic_laws
        assert "^" not in law.expression
        assert "(" not in law.expression
        assert "/" not in law.expression


# --- Parameter reuse / provenance --------------------------------------------------------------


def test_fallback_parameters_are_heuristic_only_when_no_real_evidence_exists():
    model = _assemble(_multi_substrate_mm_handoff())
    fallback = {p.parameter_id: p for p in model.parameters if p.parameter_id in ("kf_r1_p1", "kr_r1_p1")}
    assert all(p.source is ParameterSource.HEURISTIC_INITIALIZATION for p in fallback.values())
    assert all(p.provenance_refs == () for p in fallback.values())


def test_fallback_reuses_real_curated_rate_constant_evidence_when_present():
    """§6/§2's own "reuse existing... where possible": a real curated KF measurement for this
    exact multi-substrate context is used, never overridden by a heuristic guess."""
    handoff = dataclasses.replace(
        _multi_substrate_mm_handoff(),
        kinetic_measurements=(
            _measurement(
                id="mm-law", parameter_type="RATE_LAW", value=Decimal("0"), unit="n/a",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
            _measurement(id="kf-real", parameter_type="KF", value=Decimal("2.5"), unit="1/s"),
        ),
    )
    model = _assemble(handoff)
    (kf,) = (p for p in model.parameters if p.parameter_id == "kf_r1_p1")
    assert kf.source is ParameterSource.CURATED
    assert kf.value == Decimal("2.5")
    assert kf.provenance_refs == ("kf-real",)


def test_real_literature_km_preserved_but_not_consumed_by_fallback():
    """§4: the real, curated malonyl-CoA-anchored Km is preserved exactly, remains present in
    the ModelSpecification, but is never referenced by the fallback expression (which uses
    only its own new kf/kr, over species ids, never a Km/kcat token)."""
    model = _assemble(_malonyl_coa_like_handoff())
    (anchored,) = (p for p in model.parameters if p.parameter_id == "Km_r1_p1_malonyl-coa")
    assert anchored.source is ParameterSource.CURATED
    assert anchored.value == Decimal("18.0")
    assert "km-malonyl" in anchored.provenance_refs

    (law,) = model.kinetic_laws
    assert "Km_r1_p1_malonyl-coa" not in law.expression
    assert "kcat_r1_p1" not in law.expression
    assert "Km_r1_p1_malonyl-coa" in law.parameter_ids  # preserved on the law regardless


# --- Antimony ----------------------------------------------------------------------------------


def test_antimony_becomes_executable_once_fallback_values_exist():
    model = _assemble(_multi_substrate_mm_handoff(reversible=False))
    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE


def test_real_malonyl_coa_regression_becomes_executable():
    """The exact real-network regression the increment exists for."""
    model = _assemble(_malonyl_coa_like_handoff())
    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE


# --- Disclosure ----------------------------------------------------------------------------------


def test_fallback_disclosure_is_machine_readable_and_specific():
    model = _assemble(_multi_substrate_mm_handoff())
    (law,) = model.kinetic_laws
    assert any(EXECUTABLE_RATE_LAW_FALLBACK in a for a in law.assumptions)
    fallback_assumptions = [
        a
        for a in model.model_assumptions
        if a.reason_code == MULTI_SUBSTRATE_MM_SIMULATION_FALLBACK
    ]
    assert len(fallback_assumptions) == 1
    statement = fallback_assumptions[0].statement.lower()
    assert "could not be expressed safely" in statement
    assert "never a claim about the true enzyme mechanism" in statement
    assert "calibration" in statement


# --- Determinism ---------------------------------------------------------------------------------


def test_fallback_construction_is_deterministic():
    handoff = _multi_substrate_mm_handoff()
    first = _assemble(handoff)
    second = _assemble(handoff)
    assert first.kinetic_laws == second.kinetic_laws
    assert first.parameters == second.parameters
