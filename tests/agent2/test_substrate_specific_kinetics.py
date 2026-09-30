"""Tests for Substrate-Specific Kinetic Parameterization for Promiscuous Reactions.

Central rule under test: when kinetic evidence explicitly distinguishes different
substrate compounds for a promiscuous catalyst/reaction context, those measurements
belong to different substrate-conditioned kinetic-parameter concepts -- never merged,
never averaged, never treated as conflicting merely because their numeric values (or
even their tagged substrate identity) differ, and never mapped onto a species this
reaction does not itself declare as a reactant.

Every test builds an ``Agent1CuratedKnowledgeViewContract``, runs it through the real
pipeline (``assemble_full_network -> characterize_full_network -> assign_kinetic_laws
-> [resolve_enzyme_concentrations] -> declare_parameters``), matching every other
Agent 2 test file's own convention. Two fixtures are shaped directly after the two
real Pilot 4 evaluation reactions this increment fixes (see
``artifacts/pilots/yeast_fatty_acid_pilot4_post_attribution_evidence_utilization/
50_pilot4_post_attribution_report.md`` in the sibling ``agent1-biochemical-curator``
repository for the full real-data trace this mirrors):

* ``_ligase_style_handoff`` -- reaction ``10c1fab0-...`` (palmitate:CoA ligase, EC
  6.2.1.3): three reactants, real GotEnzymes2 kcat/Km evidence tagged to one genuine
  reactant substrate, and real GotEnzymes2 kcat/Km evidence tagged to the reaction's
  own *product* (the reverse-direction "substrate") -- the second must never be
  merged with, or treated as contradicting, the first.
* ``_acyltransferase_style_handoff`` -- reaction ``dc8db885-...`` (a promiscuous
  fatty-acid-elongation acyltransferase, EC 2.3.1.86): one reactant, real tagged Km
  evidence for it plus a pile of real *untagged* Km evidence from other sources (BRENDA/
  SABIO-RK), which must merge into the *same* single-substrate concept rather than being
  wrongly re-split into "tagged" vs. "untagged" and forced to ``PLACEHOLDER``.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import ParameterDeclarationSet, declare_parameters
from app.agent2.quantitative_context import resolve_enzyme_concentrations
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    ParameterSource,
)

# --- Fixtures --------------------------------------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.4", "organism_id": "org-1"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _compartment(**overrides) -> CuratedCompartment:
    return CuratedCompartment(**({"id": "cyto", "name": "cytosol"} | overrides))


def _compound(**overrides) -> CuratedCompound:
    return CuratedCompound(**({"id": "a", "name": "A"} | overrides))


def _reaction(**overrides) -> CuratedReaction:
    return CuratedReaction(**({"id": "r1", "name": "reaction 1"} | overrides))


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
        "id": "m1",
        "parameter_type": "KM",
        "value": Decimal("1"),
        "unit": "nM",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _ai_predicted_measurement(**overrides) -> CuratedKineticMeasurement:
    """A GotEnzymes2-style measurement: AI-predicted, with a canonical
    ``normalized_value``/``normalized_unit`` equal to the as-reported figure (real Pilot 4
    GotEnzymes2 evidence is always already reported in the canonical unit)."""
    merged = {"source": "GOTENZYMES"} | overrides
    merged.setdefault("normalized_value", merged.get("value", Decimal("1")))
    merged.setdefault("normalized_unit", merged.get("unit", "nM"))
    return _measurement(**merged)


def _declare(handoff: Agent1CuratedKnowledgeViewContract, *, use_enzyme_concentrations=False):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    enzyme_concentrations = (
        resolve_enzyme_concentrations(network) if use_enzyme_concentrations else None
    )
    parameters = declare_parameters(assignments, network, enzyme_concentrations)
    return network, assignments, parameters


def _by_id(declaration: ParameterDeclarationSet, parameter_id: str):
    for spec in declaration.parameter_specifications:
        if spec.parameter_id == parameter_id:
            return spec
    raise AssertionError(
        f"no parameter with id {parameter_id!r}; have "
        f"{sorted(s.parameter_id for s in declaration.parameter_specifications)}"
    )


def _has_id(declaration: ParameterDeclarationSet, parameter_id: str) -> bool:
    return any(s.parameter_id == parameter_id for s in declaration.parameter_specifications)


def _single_reactant_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """One reactant (``a``), one product (``b``), one catalyst (``p1``) -- confirmed
    Michaelis-Menten via the existing single-substrate heuristic."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b")),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(reaction_id="r1", protein_id="p1"),),
    } | overrides
    return _handoff(**merged)


def _two_reactant_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """Two reactants (``a``, ``b``), one product (``c``), one catalyst (``p1``) --
    curated reported law text explicitly naming Michaelis-Menten (matches
    ``test_macro_to_micro_reconstruction.py``'s own identical convention for forcing
    MICHAELIS_MENTEN classification on a multi-reactant context)."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b"), _compound(id="c")),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(reaction_id="r1", protein_id="p1"),),
        "kinetic_measurements": (
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
        ),
    } | overrides
    return _handoff(**merged)


def _ligase_style_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """Real Pilot 4 case 1: reaction ``10c1fab0-...`` (palmitate:CoA ligase, EC 6.2.1.3),
    simplified to its two most relevant reactants/products so forward molecularity == 2
    (Derivation C's own dimensional eligibility requirement; the real reaction has a
    third reactant, ATP, uninvolved in the substrate-conflict this fixture targets and
    omitted here purely to keep this test focused) -- two reactants (``fatty_acid``,
    ``coa``), two products (``acyl_coa``, ``ppi``), one catalyst. Real GotEnzymes2
    kcat/Km evidence tags the genuine reactant ``fatty_acid``; separate, equally real
    GotEnzymes2 kcat/Km evidence tags the product ``acyl_coa`` (the reverse-direction
    "substrate") -- this second group must never be treated as this reaction's own
    reactant-substrate evidence."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (
            _compound(id="fatty_acid"),
            _compound(id="coa"),
            _compound(id="acyl_coa"),
            _compound(id="ppi"),
        ),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="fatty_acid", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="coa", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="acyl_coa", role="PRODUCT"),
            _participant(reaction_id="r1", compound_id="ppi", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(reaction_id="r1", protein_id="p1"),),
        "kinetic_measurements": (
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
            _ai_predicted_measurement(
                id="kcat-fatty-acid",
                parameter_type="KCAT",
                value=Decimal("1.2409"),
                unit="1/s",
                compound_id="fatty_acid",
            ),
            _ai_predicted_measurement(
                id="km-fatty-acid",
                parameter_type="KM",
                value=Decimal("33700"),
                unit="nM",
                compound_id="fatty_acid",
            ),
            _ai_predicted_measurement(
                id="kcat-acyl-coa",
                parameter_type="KCAT",
                value=Decimal("1.4593"),
                unit="1/s",
                compound_id="acyl_coa",
            ),
            _ai_predicted_measurement(
                id="km-acyl-coa",
                parameter_type="KM",
                value=Decimal("15200"),
                unit="nM",
                compound_id="acyl_coa",
            ),
        ),
    } | overrides
    return _handoff(**merged)


def _acyltransferase_style_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """Real Pilot 4 case 2: reaction ``dc8db885-...`` (a promiscuous fatty-acid-
    elongation acyltransferase, EC 2.3.1.86) -- one reactant (``a``), one product
    (``b``), one catalyst. Real tagged Km evidence for the one reactant, plus real
    *untagged* Km evidence from other sources (this reaction has only one reactant, so
    untagged evidence unambiguously means "this one reactant" -- existing, pre-increment
    policy), plus real evidence tagged to two compounds (``foreign_1``/``foreign_2``)
    that are not participants of this reaction at all (other elongation-cycle steps the
    same promiscuous catalyst also acts on, per the real attribution report)."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (
            _compound(id="a"),
            _compound(id="b"),
            _compound(id="foreign_1"),
            _compound(id="foreign_2"),
        ),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (_enzyme_association(reaction_id="r1", protein_id="p1"),),
        "kinetic_measurements": (
            _ai_predicted_measurement(
                id="kcat-a",
                parameter_type="KCAT",
                value=Decimal("1.4839"),
                unit="1/s",
                compound_id="a",
            ),
            _measurement(
                id="km-a-sabiork",
                parameter_type="KM",
                value=Decimal("118000"),
                unit="nM",
                compound_id="a",
                source="SABIORK",
            ),
            _ai_predicted_measurement(
                id="km-a-gotenzymes",
                parameter_type="KM",
                value=Decimal("31600"),
                unit="nM",
                compound_id="a",
            ),
            _measurement(
                id="km-untagged-1",
                parameter_type="KM",
                value=Decimal("830000"),
                unit="nM",
                compound_id=None,
                source="BRENDA",
            ),
            _measurement(
                id="km-untagged-2",
                parameter_type="KM",
                value=Decimal("175000"),
                unit="nM",
                compound_id=None,
                source="SABIORK",
            ),
            _ai_predicted_measurement(
                id="kcat-foreign-1",
                parameter_type="KCAT",
                value=Decimal("17.7"),
                unit="1/s",
                compound_id="foreign_1",
            ),
            _ai_predicted_measurement(
                id="km-foreign-2",
                parameter_type="KM",
                value=Decimal("454200"),
                unit="nM",
                compound_id="foreign_2",
            ),
        ),
    } | overrides
    return _handoff(**merged)


# --- Real-shaped Pilot 4 regressions ---------------------------------------------------------


def test_pilot4_case1_ligase_style_kcat_resolves_from_the_mappable_reactant_only():
    """Reaction 10c1fab0-... regression: before this increment, the reactant-tagged and
    product-tagged kcat measurements were merged into one undifferentiated slot and
    forced to PLACEHOLDER (2 "different substrate/compound identities"). After this
    increment, the primary kcat slot resolves cleanly from the one reactant-mappable
    substrate; the product-tagged evidence is excluded, never merged in."""
    _, _, parameters = _declare(_ligase_style_handoff())
    kcat = _by_id(parameters, "kcat_r1_p1")
    assert kcat.source is ParameterSource.AI_PREDICTED
    assert kcat.value == Decimal("1.2409")
    assert kcat.provenance_refs == ("kcat-fatty-acid",)
    # The product-tagged measurement never contributes to this slot's value or provenance.
    assert "kcat-acyl-coa" not in kcat.provenance_refs


def test_pilot4_case1_ligase_style_km_per_reactant_unaffected():
    """Km already declares one slot per reactant (pre-existing policy, unaffected by this
    increment) -- the fatty_acid slot resolves from its own real tagged evidence; the
    other reactant (coa) has no evidence and falls to HEURISTIC_INITIALIZATION, never
    contaminated by the product-tagged acyl_coa evidence."""
    _, _, parameters = _declare(_ligase_style_handoff())
    km_fatty_acid = _by_id(parameters, "Km_r1_p1_fatty_acid")
    assert km_fatty_acid.source is ParameterSource.AI_PREDICTED
    assert km_fatty_acid.value == Decimal("33700")
    km_coa = _by_id(parameters, "Km_r1_p1_coa")
    assert km_coa.source is ParameterSource.HEURISTIC_INITIALIZATION
    assert not _has_id(parameters, "Km_r1_p1_acyl_coa")


def test_pilot4_case1_ligase_style_derivation_c_uses_only_the_anchored_substrate():
    """Derivation C (k_eff = kcat/Km) must use the fatty_acid-anchored kcat/Km pair only
    -- never the acyl_coa-tagged pair, and never a value mixing the two."""
    _, _, parameters = _declare(_ligase_style_handoff(), use_enzyme_concentrations=True)
    kf = _by_id(parameters, "kf_r1_p1")
    assert kf.source is ParameterSource.DERIVED_FROM_MACRO_KINETICS
    expected = Decimal("1.2409") / Decimal("33700")
    assert kf.value == expected
    assert set(kf.provenance_refs) == {"kcat-fatty-acid", "km-fatty-acid"}


def test_pilot4_case2_acyltransferase_style_km_merges_tagged_and_untagged():
    """Reaction dc8db885-... regression: before this increment, the one reactant's own
    real tagged Km evidence and the genuinely-generic untagged Km evidence (this
    reaction has only one reactant, so "untagged" is unambiguous) were wrongly re-split
    into two "different substrate identities" and forced to PLACEHOLDER. After this
    increment they consolidate into one concept and a real value is selected -- never
    averaged, never PLACEHOLDER. The separately-tagged AI-predicted (GotEnzymes2) Km for
    the same reactant is a distinct, lower-precedence concern (excluded from this
    experimental tier entirely, per pre-existing, unmodified policy) and is simply never
    consulted here, since real experimental evidence already resolves this slot."""
    _, _, parameters = _declare(_acyltransferase_style_handoff())
    km = _by_id(parameters, "Km_r1_p1_a")
    assert km.source is not ParameterSource.PLACEHOLDER
    assert km.value is not None
    assert set(km.provenance_refs) == {"km-a-sabiork", "km-untagged-1", "km-untagged-2"}
    assert "km-a-gotenzymes" not in km.provenance_refs
    # Never averaged: the selected value is exactly one of the real candidates.
    assert km.value in {Decimal("118000"), Decimal("830000"), Decimal("175000")}


def test_pilot4_case2_acyltransferase_style_kcat_resolves_cleanly():
    """The one reactant's own tagged kcat measurement resolves on its own -- the
    foreign-compound-tagged kcat measurement (a different elongation-cycle step this
    coarse reaction model does not represent) never contaminates it."""
    _, _, parameters = _declare(_acyltransferase_style_handoff())
    kcat = _by_id(parameters, "kcat_r1_p1")
    assert kcat.source is ParameterSource.AI_PREDICTED
    assert kcat.value == Decimal("1.4839")
    assert kcat.provenance_refs == ("kcat-a",)


def test_pilot4_case2_acyltransferase_style_foreign_evidence_disclosed_not_dropped_silently():
    """The foreign-compound-tagged measurements (belonging to a different reaction this
    coarse model does not represent) are excluded from every substrate-specific slot, but
    their exclusion is disclosed on ParameterDeclarationSet.assumptions rather than
    silently vanishing (task: "preserve the ambiguity explicitly rather than fabricating
    a mapping")."""
    _, _, parameters = _declare(_acyltransferase_style_handoff())
    joined = " ".join(parameters.assumptions)
    assert "kcat-foreign-1" in joined
    assert "km-foreign-2" in joined
    assert "foreign_1" in joined
    assert "foreign_2" in joined


# --- Coexisting substrate-specific concepts (synthetic, general-capability tests) ------------


def test_two_substrate_specific_kcat_values_coexist_without_conflict():
    """Two reactant compounds (a, b) each carry their own real, distinct, disagreeing
    kcat evidence -- both are preserved as separate, independently-resolved concepts,
    never merged into one PLACEHOLDER merely because their values differ."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("9"), unit="1/s", compound_id="b"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    kcat_a = _by_id(parameters, "kcat_r1_p1_a")
    kcat_b = _by_id(parameters, "kcat_r1_p1_b")
    assert kcat_a.value == Decimal("5")
    assert kcat_a.source is ParameterSource.CURATED
    assert kcat_b.value == Decimal("9")
    assert kcat_b.source is ParameterSource.CURATED
    assert kcat_a.provenance_refs == ("kcat-a",)
    assert kcat_b.provenance_refs == ("kcat-b",)


def test_two_substrate_specific_kcat_values_leave_primary_slot_a_disclosed_placeholder():
    """The one generic (unsuffixed) kcat slot every Michaelis-Menten law declares cannot
    represent two distinct substrate concepts at once -- it is left an explicit,
    disclosed PLACEHOLDER naming both substrates, never an arbitrary pick of one."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("9"), unit="1/s", compound_id="b"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    primary = _by_id(parameters, "kcat_r1_p1")
    assert primary.source is ParameterSource.PLACEHOLDER
    assert "kcat-a" in primary.provenance_refs
    assert "kcat-b" in primary.provenance_refs
    assert primary.uncertainty_text is not None
    assert "a" in primary.uncertainty_text and "b" in primary.uncertainty_text


def test_two_substrate_specific_km_values_are_already_separate_concepts():
    """Km already declares one slot per reactant (pre-existing policy) -- two distinct,
    disagreeing tagged Km values for a and b never conflict with each other."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="km-a", parameter_type="KM", value=Decimal("100"), unit="nM", compound_id="a"
            ),
            _measurement(
                id="km-b", parameter_type="KM", value=Decimal("9000"), unit="nM", compound_id="b"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    assert _by_id(parameters, "Km_r1_p1_a").value == Decimal("100")
    assert _by_id(parameters, "Km_r1_p1_b").value == Decimal("9000")


def test_matching_kcat_and_km_for_substrate_a_derive_only_substrate_as_k_eff():
    """kcat(a) + Km(a) derive k_eff(a) via Derivation C; kcat(b)/Km(b) never contribute
    to it, and no k_eff is derived "for b" at all (Derivation C is only ever computed
    once, for the law's own single anchor)."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("10"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="km-a", parameter_type="KM", value=Decimal("1000"), unit="nM", compound_id="a"
            ),
        )
    )
    _, _, parameters = _declare(handoff, use_enzyme_concentrations=True)
    kf = _by_id(parameters, "kf_r1_p1")
    assert kf.source is ParameterSource.DERIVED_FROM_MACRO_KINETICS
    assert kf.value == Decimal("10") / Decimal("1000")
    assert set(kf.provenance_refs) == {"kcat-a", "km-a"}


def test_no_cross_substrate_pairing_when_km_and_kcat_disagree_on_which_substrate():
    """kcat is tagged to compound b, but Km's own anchor (the only reactant with Km
    evidence) is compound a -- Derivation C must never pair kcat(b) with Km(a); no
    k_eff is derived at all."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("10"), unit="1/s", compound_id="b"
            ),
            _measurement(
                id="km-a", parameter_type="KM", value=Decimal("1000"), unit="nM", compound_id="a"
            ),
        )
    )
    _, _, parameters = _declare(handoff, use_enzyme_concentrations=True)
    kf = _by_id(parameters, "kf_r1_p1")
    assert kf.source is ParameterSource.HEURISTIC_INITIALIZATION
    # The primary kcat slot is also never fabricated from the mismatched substrate --
    # it falls through cleanly to a heuristic default, since kcat(b) does not anchor to
    # Km's own substrate 'a' for this pairing, but is still kcat's own only mappable
    # substrate for the plain kcat slot itself (a real, independent, unmerged concept).
    kcat = _by_id(parameters, "kcat_r1_p1")
    assert kcat.provenance_refs == ("kcat-b",)


def test_generic_untagged_evidence_stays_distinct_from_substrate_specific_evidence():
    """For a multi-reactant context, generic (untagged) kcat evidence is never folded
    into a specific reactant's own concept when 2+ reactants each already have their own
    tagged evidence -- it is excluded from both substrate-specific slots rather than
    guessed onto either."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("9"), unit="1/s", compound_id="b"
            ),
            _measurement(
                id="kcat-untagged", parameter_type="KCAT", value=Decimal("42"), unit="1/s"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    kcat_a = _by_id(parameters, "kcat_r1_p1_a")
    kcat_b = _by_id(parameters, "kcat_r1_p1_b")
    assert "kcat-untagged" not in kcat_a.provenance_refs
    assert "kcat-untagged" not in kcat_b.provenance_refs


def test_untagged_kcat_merges_with_the_single_mappable_substrate():
    """Unlike Km/Ki, kcat is a property of the catalytic turnover itself -- when only
    one reactant compound has any tagged kcat evidence at all, genuinely generic
    (untagged) kcat evidence is compatible with it (it makes no competing substrate
    claim) and is folded into the same concept, corroborating rather than conflicting."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(id="kcat-untagged", parameter_type="KCAT", value=Decimal("5"), unit="1/s"),
        )
    )
    _, _, parameters = _declare(handoff)
    kcat = _by_id(parameters, "kcat_r1_p1")
    assert kcat.source is ParameterSource.CURATED
    assert kcat.value == Decimal("5")
    assert set(kcat.provenance_refs) == {"kcat-a", "kcat-untagged"}
    assert not _has_id(parameters, "kcat_r1_p1_a")


# --- Same-substrate consolidation, isozymes, determinism, single-substrate parity ------------


def test_same_substrate_multiple_measurements_still_use_existing_consolidation():
    """Two measurements tagged to the *same* substrate that disagree numerically still
    consolidate into one concept and select one real value -- never PLACEHOLDER merely
    because two same-substrate measurements disagree (pre-existing, unmodified
    consolidation policy, now correctly reached via ``already_substrate_scoped``)."""
    handoff = _single_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="km-1",
                parameter_type="KM",
                value=Decimal("100"),
                unit="nM",
                compound_id="a",
                source="SABIORK",
            ),
            _measurement(
                id="km-2",
                parameter_type="KM",
                value=Decimal("500"),
                unit="nM",
                compound_id="a",
                source="BRENDA",
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    km = _by_id(parameters, "Km_r1_p1_a")
    assert km.source is not ParameterSource.PLACEHOLDER
    assert km.value in {Decimal("100"), Decimal("500")}
    assert set(km.provenance_refs) == {"km-1", "km-2"}


def test_no_silent_averaging_of_disagreeing_same_substrate_evidence():
    """The selected value is always exactly one real candidate's own reported figure --
    never a computed average of the two."""
    handoff = _single_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="km-1",
                parameter_type="KM",
                value=Decimal("100"),
                unit="nM",
                compound_id="a",
                source="SABIORK",
            ),
            _measurement(
                id="km-2",
                parameter_type="KM",
                value=Decimal("500"),
                unit="nM",
                compound_id="a",
                source="BRENDA",
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    km = _by_id(parameters, "Km_r1_p1_a")
    assert km.value != Decimal("300")  # the average -- never produced


def test_different_isozymes_with_substrate_specific_evidence_remain_separate():
    """Two isozymes (p1, p2) catalyzing the same single-substrate reaction, each with
    its own tagged kcat evidence for the one reactant -- never collapsed into a shared
    concept, exactly mirroring the pre-existing isozyme-separation policy."""
    handoff = _single_reactant_handoff(
        reaction_enzyme_associations=(
            _enzyme_association(reaction_id="r1", protein_id="p1"),
            _enzyme_association(reaction_id="r1", protein_id="p2"),
        ),
        kinetic_measurements=(
            _measurement(
                id="kcat-p1",
                parameter_type="KCAT",
                value=Decimal("3"),
                unit="1/s",
                compound_id="a",
                protein_id="p1",
            ),
            _measurement(
                id="kcat-p2",
                parameter_type="KCAT",
                value=Decimal("11"),
                unit="1/s",
                compound_id="a",
                protein_id="p2",
            ),
        ),
    )
    _, _, parameters = _declare(handoff)
    assert _by_id(parameters, "kcat_r1_p1").value == Decimal("3")
    assert _by_id(parameters, "kcat_r1_p1").provenance_refs == ("kcat-p1",)
    assert _by_id(parameters, "kcat_r1_p2").value == Decimal("11")
    assert _by_id(parameters, "kcat_r1_p2").provenance_refs == ("kcat-p2",)


def test_multi_substrate_reaction_preserves_participant_identity_in_parameter_ids():
    """Every substrate-specific parameter id names the exact compound it concerns --
    never a positional or arbitrary label -- so Km/kcat slots for distinct reactants are
    always distinguishable and never accidentally aliased."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("9"), unit="1/s", compound_id="b"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    ids = {s.parameter_id for s in parameters.parameter_specifications}
    assert "kcat_r1_p1_a" in ids
    assert "kcat_r1_p1_b" in ids
    assert "Km_r1_p1_a" in ids
    assert "Km_r1_p1_b" in ids


def test_deterministic_ordering_and_provenance_across_repeated_declaration():
    """Declaring parameters twice from the identical input produces byte-identical
    parameter ids, values, and provenance ordering -- no randomness, no dict-iteration-
    order dependence."""
    handoff = _two_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
                source=None,
            ),
            _measurement(
                id="kcat-a", parameter_type="KCAT", value=Decimal("5"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="kcat-b", parameter_type="KCAT", value=Decimal("9"), unit="1/s", compound_id="b"
            ),
        )
    )
    _, _, first = _declare(handoff)
    _, _, second = _declare(handoff)
    assert first.parameter_specifications == second.parameter_specifications
    assert first.assumptions == second.assumptions


def test_single_substrate_reaction_shape_unchanged_by_this_increment():
    """A plain single-substrate reaction with one clean, unambiguous tagged kcat/Km pair
    declares exactly the same two parameters as before this increment -- no extra
    substrate-suffixed kcat slot, no PLACEHOLDER, no behavior change."""
    handoff = _single_reactant_handoff(
        kinetic_measurements=(
            _measurement(
                id="kcat-1", parameter_type="KCAT", value=Decimal("7"), unit="1/s", compound_id="a"
            ),
            _measurement(
                id="km-1", parameter_type="KM", value=Decimal("200"), unit="nM", compound_id="a"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    ids = {s.parameter_id for s in parameters.parameter_specifications}
    assert ids == {"kcat_r1_p1", "Km_r1_p1_a"}
    assert _by_id(parameters, "kcat_r1_p1").value == Decimal("7")
    assert _by_id(parameters, "kcat_r1_p1").source is ParameterSource.CURATED
    assert not parameters.assumptions
