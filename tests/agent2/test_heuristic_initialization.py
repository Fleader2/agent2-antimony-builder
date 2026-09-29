"""Tests for the Heuristic Simulation Parameter Initialization increment.

Every test builds an ``Agent1CuratedKnowledgeViewContract`` and runs it through the full real
pipeline (``assemble_full_network`` -> ``characterize_full_network`` -> ``assign_kinetic_laws``
-> ``declare_parameters``), matching every other Agent 2 test file's own convention -- no test
constructs a ``ParameterDeclarationSet``/``Initialization`` by hand for the pipeline-level
scenarios. A handful of pure unit tests at the bottom exercise
``app.agent2.parameters.heuristic_defaults`` directly, since the pipeline offers no way to
observe every molecularity in isolation.

This file's own private fixtures deliberately mirror (never import, per this codebase's own
per-test-file fixture convention -- see ``tests/agent2/test_parameters.py``'s and
``tests/agent2/test_model_specification.py``'s own identical helpers) the fixture shapes those
two files already use, so a reader who knows one file's fixtures immediately recognizes these.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import ParameterDeclarationSet, declare_parameters
from app.agent2.parameters.heuristic_defaults import (
    CANONICAL_UNIT_NM,
    CANONICAL_UNIT_NM_PER_S,
    CANONICAL_UNIT_PER_NMS,
    CANONICAL_UNIT_PER_SEC,
    REFERENCE_CONCENTRATION_NM,
    REFERENCE_RATE_PER_SEC,
    ParameterKind,
    heuristic_default_for_kind,
    mass_action_rate_default,
    mass_action_rate_unit,
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

# --- Fixtures ----------------------------------------------------------------------------------


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
        "parameter_type": "K",
        "value": Decimal("1"),
        "unit": "1/s",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _declare(handoff: Agent1CuratedKnowledgeViewContract) -> ParameterDeclarationSet:
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    return declare_parameters(assignments, network)


def _by_id(declaration: ParameterDeclarationSet, parameter_id: str) -> ParameterSpecification:
    for spec in declaration.parameter_specifications:
        if spec.parameter_id == parameter_id:
            return spec
    raise AssertionError(f"no parameter with id {parameter_id!r}")


def _unimolecular_state_transition_handoff(
    **kinetic_measurements_kw,
) -> Agent1CuratedKnowledgeViewContract:
    """A bare, non-enzymatic, unimolecular state-transition reaction (molecularity 1
    forward) -- Increment 4's own ``is_simple_elementary_transition`` structural rule
    assigns this ``MASS_ACTION``, non-tentative, with no catalyst context suffix."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(),),
        "reactions": (_reaction(),),
        "reaction_participants": (_participant(),),
        "enzyme_states": (
            CuratedEnzymeState(id="es0", state_type="PHOSPHORYLATED", protein_id="p1"),
            CuratedEnzymeState(id="es1", state_type="PHOSPHORYLATED", protein_id="p1"),
        ),
        "enzyme_state_transitions": (
            CuratedEnzymeStateTransition(
                id="t1",
                from_state_id="es0",
                to_state_id="es1",
                transition_type="PHOSPHORYLATION",
                reaction_id="r1",
            ),
        ),
    } | kinetic_measurements_kw
    return _handoff(**merged)


def _tentative_bimolecular_handoff(**kinetic_measurements_kw) -> Agent1CuratedKnowledgeViewContract:
    """Catalyzed, reversible, two reactants + one product -- confirmed empirically
    (Heuristic Simulation Parameter Initialization increment's own coverage evaluation) to
    assign ``MASS_ACTION``/``TENTATIVE_MASS_ACTION_DEFAULT`` with forward molecularity 2, the
    real network's own most common shape for a heuristically-initialized bimolecular
    parameter."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b"), _compound(id="c")),
        "reactions": (_reaction(reversible=True),),
        "reaction_participants": (
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="REACTANT"),
            _participant(compound_id="c", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(),),
    } | kinetic_measurements_kw
    return _handoff(**merged)


def _asymmetric_reversible_mass_action_handoff() -> Agent1CuratedKnowledgeViewContract:
    """A <=> C + D: forward molecularity 1, reverse molecularity 2 -- the two directions of
    one ``REVERSIBLE_MASS_ACTION`` law must never be related through a fabricated equilibrium
    and must each carry their own, independently-derived unit (increment instructions §5)."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="c"), _compound(id="d")),
        reactions=(_reaction(reversible=True),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="c", role="PRODUCT"),
            _participant(compound_id="d", role="PRODUCT"),
        ),
        kinetic_measurements=(
            _measurement(
                id="km_law",
                parameter_type="RATE_LAW",
                value=Decimal("0"),
                unit="n/a",
                reported_rate_law="kf * a - kr * c * d",
            ),
        ),
    )


def _single_substrate_mm_handoff(**kinetic_measurements_kw) -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(_enzyme_association(),),
        **kinetic_measurements_kw,
    )


def _custom_handoff(**kinetic_measurements_kw) -> Agent1CuratedKnowledgeViewContract:
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(),),
        reactions=(_reaction(),),
        reaction_participants=(_participant(),),
        reaction_enzyme_associations=(_enzyme_association(),),
        **kinetic_measurements_kw,
    )


# --- Precedence: real evidence is never overwritten ---------------------------------------------


def test_literature_derived_value_never_overwritten_by_heuristic():
    """A Km reported with a ``publication_id`` (-> ``LITERATURE_DERIVED``) keeps its exact
    reported value/unit; the co-declared kcat, which has no evidence at all, is
    heuristically initialized -- confirming both the never-overwrite rule and §6's mixed
    curated+initialized resolution in one fixture."""
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="km_km",
                parameter_type="KM",
                value=Decimal("0.2"),
                unit="mM",
                compound_id="a",
                publication_id="pub-1",
            ),
        )
    )
    declaration = _declare(handoff)
    km = _by_id(declaration, "Km_r1_p1_a")
    assert km.source is ParameterSource.LITERATURE_DERIVED
    assert km.value == Decimal("0.2")
    assert km.unit == "mM"
    assert km.provenance_refs == ("km_km",)

    kcat = _by_id(declaration, "kcat_r1_p1")
    assert kcat.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kcat.value == REFERENCE_RATE_PER_SEC
    assert kcat.unit == CANONICAL_UNIT_PER_SEC


def test_ai_predicted_value_never_overwritten_by_heuristic():
    """A GotEnzymes2-sourced (AI-predicted) measurement resolves to ``AI_PREDICTED`` using
    its own canonical ``normalized_value``/``normalized_unit`` (Agent 1.x Increment C.12),
    never the generic heuristic default and never its own raw, source-specific reported
    figure."""
    handoff = _unimolecular_state_transition_handoff(
        kinetic_measurements=(
            CuratedKineticMeasurement(
                id="gm1",
                parameter_type="K",
                value=Decimal("500"),
                unit="mM/s",
                reaction_id="r1",
                source="GOTENZYMES",
                normalized_value=Decimal("0.5"),
                normalized_unit="per_nMs",
            ),
        )
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.AI_PREDICTED
    assert spec.value == Decimal("0.5")
    assert spec.unit == "per_nMs"
    assert spec.provenance_refs == ("gm1",)


def test_literature_derived_beats_ai_predicted_even_under_comparable_conditions():
    """Multi-Measurement Kinetic Evidence Consolidation and Prioritization increment:
    evidence-class ranking (experimental/literature > AI-predicted) is never folded into
    consolidation's own condition/completeness/recency priorities -- it remains enforced
    one level up by the pre-existing two-tier initializer split, so a literature-derived
    measurement always wins regardless of how favorably an AI-predicted candidate's own
    conditions might otherwise compare."""
    handoff = _unimolecular_state_transition_handoff(
        kinetic_measurements=(
            _measurement(
                id="km_lit", parameter_type="K", value=Decimal("2"), unit="1/s",
                publication_id="pub-1",
            ),
            CuratedKineticMeasurement(
                id="gm1",
                parameter_type="K",
                value=Decimal("500"),
                unit="mM/s",
                reaction_id="r1",
                source="GOTENZYMES",
                normalized_value=Decimal("0.5"),
                normalized_unit="per_nMs",
            ),
        )
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.LITERATURE_DERIVED
    assert spec.value == Decimal("2")
    assert spec.provenance_refs == ("km_lit",)


def test_disagreeing_evidence_is_resolved_and_never_overwritten_by_heuristic():
    """Two disagreeing curated measurements are strictly more informative than no evidence
    at all -- ``initialize_with_fallback`` must never silently discard that disagreement in
    favor of a lower-precedence heuristic guess. Multi-Measurement Kinetic Evidence
    Consolidation and Prioritization increment: they now consolidate and a representative
    is selected (deterministically, never a heuristic guess) rather than falling to
    PLACEHOLDER -- disagreement is disclosed in ``uncertainty_text``, and both ids are
    still preserved."""
    handoff = _unimolecular_state_transition_handoff(
        kinetic_measurements=(
            _measurement(id="km_a", parameter_type="K", value=Decimal("2"), unit="1/s"),
            _measurement(id="km_b", parameter_type="K", value=Decimal("9"), unit="1/s"),
        )
    )
    declaration = _declare(handoff)
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.CURATED
    assert spec.value == Decimal("2")
    assert spec.provenance_refs == ("km_a", "km_b")
    assert "differing values" in spec.uncertainty_text.lower()


# --- Placeholder initialization by parameter shape ----------------------------------------------


def test_placeholder_first_order_parameter_is_heuristically_initialized():
    declaration = _declare(_unimolecular_state_transition_handoff())
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.value == REFERENCE_RATE_PER_SEC
    assert spec.unit == CANONICAL_UNIT_PER_SEC
    assert spec.provenance_refs == ()


def test_placeholder_bimolecular_parameter_is_heuristically_initialized_in_per_nms():
    declaration = _declare(_tentative_bimolecular_handoff())
    spec = _by_id(declaration, "k_r1_p1")
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.unit == CANONICAL_UNIT_PER_NMS
    assert spec.value == REFERENCE_RATE_PER_SEC / REFERENCE_CONCENTRATION_NM
    assert spec.provenance_refs == ()


def test_placeholder_km_like_parameter_is_heuristically_initialized_in_nm():
    declaration = _declare(_single_substrate_mm_handoff())
    spec = _by_id(declaration, "Km_r1_p1_a")
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.unit == CANONICAL_UNIT_NM
    assert spec.value == REFERENCE_CONCENTRATION_NM
    assert spec.provenance_refs == ()


def test_reversible_forward_and_reverse_each_get_their_own_molecularity_and_unit():
    declaration = _declare(_asymmetric_reversible_mass_action_handoff())
    kf = _by_id(declaration, "kf_r1")
    kr = _by_id(declaration, "kr_r1")
    assert kf.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert kr.source is ParameterSource.HEURISTIC_INITIALIZATION
    # Forward molecularity 1 -> per_sec; reverse molecularity 2 -> per_nMs. Never related to
    # each other through a fabricated equilibrium constant.
    assert kf.unit == CANONICAL_UNIT_PER_SEC
    assert kf.value == REFERENCE_RATE_PER_SEC
    assert kr.unit == CANONICAL_UNIT_PER_NMS
    assert kr.value == REFERENCE_RATE_PER_SEC / REFERENCE_CONCENTRATION_NM


# --- Boundary: unsupported mechanisms and unresolved expressions are never initialized -----------


def test_custom_unsupported_mechanism_is_never_heuristically_initialized():
    """CUSTOM means an unsupported/unparsed kinetic mechanism -- no molecularity or
    dimension can be safely inferred, so its generic slot stays a bare PLACEHOLDER even
    though every other law type now receives a heuristic default (increment instructions
    §7)."""
    handoff = _custom_handoff(
        kinetic_measurements=(
            _measurement(
                id="km_law",
                parameter_type="RATE_LAW",
                value=Decimal("0"),
                unit="n/a",
                reported_rate_law="some weird f(x,y,z) expression",
            ),
        )
    )
    declaration = _declare(handoff)
    assert len(declaration.parameter_specifications) == 1
    spec = declaration.parameter_specifications[0]
    assert spec.source is ParameterSource.PLACEHOLDER
    assert spec.value is None


def test_no_parameter_specification_is_ever_calibrated_source():
    """``ParameterSource.CALIBRATED`` is reserved exclusively for a future Agent 4 -- this
    increment (and everything upstream of it) must never produce it."""
    for handoff in (
        _unimolecular_state_transition_handoff(),
        _tentative_bimolecular_handoff(),
        _asymmetric_reversible_mass_action_handoff(),
        _single_substrate_mm_handoff(),
        _custom_handoff(),
    ):
        declaration = _declare(handoff)
        assert all(
            spec.source is not ParameterSource.CALIBRATED
            for spec in declaration.parameter_specifications
        )


# --- Determinism and explicit provenance ---------------------------------------------------------


def test_heuristic_initialization_is_deterministic_across_repeated_runs():
    handoff = _tentative_bimolecular_handoff()
    first = _declare(handoff)
    second = _declare(handoff)
    assert first.parameter_specifications == second.parameter_specifications


def test_heuristic_initialization_carries_explicit_disclosed_provenance():
    declaration = _declare(_unimolecular_state_transition_handoff())
    spec = _by_id(declaration, "k_r1")
    assert spec.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert spec.provenance_refs == ()
    assert spec.source_reference is not None
    assert "heuristic-initialization" in spec.source_reference
    assert spec.uncertainty_text is not None
    assert "never a biochemical claim" in spec.uncertainty_text
    assert "calibration" in spec.uncertainty_text.lower()


# --- Mixed evidence set (Run-6-shaped) ------------------------------------------------------------


def _run6_shaped_handoff() -> Agent1CuratedKnowledgeViewContract:
    """A small network combining every evidence tier the real Pilot 2 Run 6 network itself
    contains after Agent 1.x C.9-C.12: one real literature-derived Km (mirroring the real
    malonyl-CoA measurement), one AI-predicted rate constant (mirroring a real GotEnzymes2
    hit), a bare unimolecular state-transition reaction with no evidence at all, a catalyzed
    bimolecular reaction with no evidence at all, and one substrate-anchored multi-substrate
    Michaelis-Menten reaction whose overall expression stays unresolved regardless of
    parameter initialization (§7/§8) -- exactly the real network's own shape (the real
    ACC1/malonyl-CoA-ACP reaction)."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(
            _compound(id="a"),
            _compound(id="b"),
            _compound(id="c"),
            _compound(id="d"),
            _compound(id="e"),
            _compound(id="f"),
        ),
        reactions=(
            _reaction(id="r_literature"),
            _reaction(id="r_ai_predicted"),
            _reaction(id="r_bimolecular", reversible=True),
            _reaction(id="r_multi_substrate"),
        ),
        reaction_participants=(
            _participant(reaction_id="r_literature", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r_literature", compound_id="b", role="PRODUCT"),
            _participant(reaction_id="r_ai_predicted", compound_id="c", role="REACTANT"),
            _participant(reaction_id="r_bimolecular", compound_id="c", role="REACTANT"),
            _participant(reaction_id="r_bimolecular", compound_id="d", role="REACTANT"),
            _participant(reaction_id="r_bimolecular", compound_id="e", role="PRODUCT"),
            _participant(reaction_id="r_multi_substrate", compound_id="d", role="REACTANT"),
            _participant(reaction_id="r_multi_substrate", compound_id="e", role="REACTANT"),
            _participant(reaction_id="r_multi_substrate", compound_id="a", role="PRODUCT"),
            _participant(reaction_id="r_multi_substrate", compound_id="f", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r_literature", protein_id="p1"),
            _enzyme_association(reaction_id="r_bimolecular", protein_id="p2"),
            _enzyme_association(reaction_id="r_multi_substrate", protein_id="p3"),
        ),
        enzyme_states=(
            CuratedEnzymeState(id="es0", state_type="PHOSPHORYLATED", protein_id="p4"),
            CuratedEnzymeState(id="es1", state_type="PHOSPHORYLATED", protein_id="p4"),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t_ai_predicted",
                from_state_id="es0",
                to_state_id="es1",
                transition_type="PHOSPHORYLATION",
                reaction_id="r_ai_predicted",
            ),
        ),
        kinetic_measurements=(
            _measurement(
                id="km_literature",
                reaction_id="r_literature",
                parameter_type="KM",
                value=Decimal("18.0"),
                unit="uM",
                compound_id="a",
                publication_id="pub-1",
            ),
            CuratedKineticMeasurement(
                id="km_ai",
                parameter_type="K",
                value=Decimal("500"),
                unit="mM/s",
                reaction_id="r_ai_predicted",
                source="GOTENZYMES",
                normalized_value=Decimal("0.5"),
                normalized_unit="per_nMs",
            ),
            _measurement(
                id="km_multi_substrate",
                reaction_id="r_multi_substrate",
                parameter_type="KM",
                value=Decimal("18.0"),
                unit="uM",
                compound_id="d",
            ),
        ),
    )


def test_run6_shaped_mixed_evidence_set_resolves_each_tier_correctly():
    network = assemble_full_network(_run6_shaped_handoff())
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    declaration = declare_parameters(assignments, network)

    by_id = {s.parameter_id: s for s in declaration.parameter_specifications}

    literature_km = by_id["Km_r_literature_p1_a"]
    assert literature_km.source is ParameterSource.LITERATURE_DERIVED
    assert literature_km.value == Decimal("18.0")

    literature_kcat = by_id["kcat_r_literature_p1"]
    assert literature_kcat.source is ParameterSource.HEURISTIC_INITIALIZATION

    ai_predicted = by_id["k_r_ai_predicted"]
    assert ai_predicted.source is ParameterSource.AI_PREDICTED
    assert ai_predicted.value == Decimal("0.5")
    assert ai_predicted.unit == "per_nMs"

    bimolecular = by_id["k_r_bimolecular_p2"]
    assert bimolecular.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert bimolecular.unit == CANONICAL_UNIT_PER_NMS

    multi_substrate_kcat = by_id["kcat_r_multi_substrate_p3"]
    assert multi_substrate_kcat.source is ParameterSource.HEURISTIC_INITIALIZATION

    anchored_km = by_id["Km_r_multi_substrate_p3_d"]
    assert anchored_km.source is ParameterSource.CURATED
    assert anchored_km.value == Decimal("18.0")

    unanchored_km = by_id["Km_r_multi_substrate_p3_e"]
    assert unanchored_km.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert unanchored_km.unit == CANONICAL_UNIT_NM

    # The multi-substrate reaction's own kinetic law still has no resolvable expression --
    # every one of its parameters now has a value, but that alone never makes an unresolved
    # multi-substrate rate law executable (§7/§8; confirmed at the Antimony layer in
    # tests/agent2/test_model_specification.py).
    (multi_substrate_law,) = (
        a for a in assignments.assignments if a.reaction_id == "r_multi_substrate"
    )
    assert multi_substrate_law.kinetic_law_type.value == "MICHAELIS_MENTEN"

    counts: dict[ParameterSource, int] = {}
    for spec in declaration.parameter_specifications:
        counts[spec.source] = counts.get(spec.source, 0) + 1
    assert counts[ParameterSource.LITERATURE_DERIVED] == 1
    assert counts[ParameterSource.CURATED] == 1
    assert counts[ParameterSource.AI_PREDICTED] == 1
    assert counts.get(ParameterSource.PLACEHOLDER, 0) == 0
    assert counts[ParameterSource.HEURISTIC_INITIALIZATION] == len(
        declaration.parameter_specifications
    ) - 3


# --- Pure unit tests: heuristic_defaults ----------------------------------------------------------


def test_mass_action_rate_unit_named_orders():
    assert mass_action_rate_unit(0) == CANONICAL_UNIT_NM_PER_S
    assert mass_action_rate_unit(1) == CANONICAL_UNIT_PER_SEC
    assert mass_action_rate_unit(2) == CANONICAL_UNIT_PER_NMS


def test_mass_action_rate_unit_higher_order_is_algebraic_never_a_new_named_unit():
    assert mass_action_rate_unit(3) == "nM^-2 s^-1"
    assert mass_action_rate_unit(4) == "nM^-3 s^-1"


def test_mass_action_rate_default_every_order_shares_one_characteristic_flux():
    """Every order's default value, multiplied by the reference concentration raised to its
    own reactant count, reproduces the identical characteristic flux -- the whole point of
    deriving every default from the same two reference constants rather than picking
    independent magic numbers per order."""
    characteristic_flux = REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM
    for n in range(0, 5):
        default = mass_action_rate_default(n)
        assert default.value * (REFERENCE_CONCENTRATION_NM**n) == characteristic_flux


def test_heuristic_default_for_kind_unsupported_kind_returns_none():
    assert heuristic_default_for_kind(ParameterKind.UNSUPPORTED) is None


def test_heuristic_default_for_kind_concentration_and_flux():
    concentration = heuristic_default_for_kind(ParameterKind.CONCENTRATION)
    assert concentration.value == REFERENCE_CONCENTRATION_NM
    assert concentration.unit == CANONICAL_UNIT_NM

    flux = heuristic_default_for_kind(ParameterKind.FLUX)
    assert flux.value == REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM
    assert flux.unit == CANONICAL_UNIT_NM_PER_S
