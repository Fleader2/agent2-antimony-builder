"""Tests for the Identifiability-Aware Macroscopic-to-Microscopic Kinetic Reconstruction
increment (``app.agent2.parameters.reconstruction``, and its wiring into
``app.agent2.parameters.builder``/``app.agent2.model_specification``).

Every test builds an ``Agent1CuratedKnowledgeViewContract``, runs it through the real
pipeline (``assemble_full_network -> characterize_full_network -> assign_kinetic_laws ->
resolve_enzyme_concentrations -> declare_parameters``), matching every other Agent 2 test
file's own convention. Fixtures are shaped after this project's own real Run 7 sce00061
data (a single-substrate Michaelis-Menten context with real BRENDA/GotEnzymes2-style
KM/KCAT/VMAX evidence, and a two-reactant context matching the real malonyl-CoA:[acp]
S-malonyltransferase reaction) rather than idealized shapes convenient for this suite.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.parameters.types import IdentifiabilityStatus
from app.agent2.quantitative_context import resolve_enzyme_concentrations
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedExperimentalContext,
    CuratedKineticMeasurement,
    CuratedQuantitativeObservation,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    KineticLawType,
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


def _context(**overrides) -> CuratedExperimentalContext:
    merged = {
        "id": "ctx-1",
        "organism_id": "org-1",
        "strain": "BY4741",
        "classification": "REFERENCE",
        "source": "TEST",
    } | overrides
    return CuratedExperimentalContext(**merged)


def _concentration_observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-conc-1",
        "observation_type": "PROTEIN_CONCENTRATION",
        "value": Decimal("100"),
        "unit": "nM",
        "evidence_class": "REFERENCE_BASELINE",
        "protein_id": "p1",
        "organism_id": "org-1",
        "experimental_context_id": "ctx-1",
        "source": "TEST",
        "source_id": "test:conc-1",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


def _single_substrate_mm_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """One reaction, one substrate, one product, catalyzed by p1 -- confirmed
    Michaelis-Menten via the existing heuristic (no reported law needed)."""
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


def _two_reactant_mm_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """Two reactants, one product, curated reported law text explicitly naming
    "Michaelis-Menten" -- confirmed CURATED_REPORTED/MICHAELIS_MENTEN, reversibility
    unresolved -> the multi-substrate simulation fallback declares kf/kr (reversible
    branch), forward molecularity == 2 -- matches this project's own real malonyl-CoA:
    [acp] S-malonyltransferase reaction shape."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (_compound(id="a"), _compound(id="b"), _compound(id="c")),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="PRODUCT"),
        ),
        "kinetic_measurements": (
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
        ),
    } | overrides
    return _handoff(**merged)


def _three_reactant_mm_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """Three reactants -- forward molecularity == 3, dimensionally ineligible for
    Derivation C (per_nMs only matches molecularity == 2)."""
    merged = {
        "compartments": (_compartment(),),
        "compounds": (
            _compound(id="a"),
            _compound(id="b"),
            _compound(id="c"),
            _compound(id="d"),
        ),
        "reactions": (_reaction(id="r1"),),
        "reaction_participants": (
            _participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="b", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="c", role="REACTANT"),
            _participant(reaction_id="r1", compound_id="d", role="PRODUCT"),
        ),
        "kinetic_measurements": (
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
        ),
    } | overrides
    return _handoff(**merged)


def _declare(
    handoff: Agent1CuratedKnowledgeViewContract, *, use_enzyme_concentrations: bool = True
):
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    enzyme_concentrations = (
        resolve_enzyme_concentrations(network) if use_enzyme_concentrations else None
    )
    parameters = declare_parameters(assignments, network, enzyme_concentrations)
    return network, assignments, parameters


def _param(parameters, prefix: str):
    (spec,) = (p for p in parameters.parameter_specifications if p.name.startswith(f"{prefix}_"))
    return spec


# --- Derivation A: direct kcat always wins, never re-derived ---------------------------------


def test_direct_kcat_preserved_never_rederived():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(id="kcat-1", parameter_type="KCAT", value=Decimal("5"), unit="per_sec"),
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("999"),
                unit="nM_per_s",
                normalized_value=Decimal("999"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    assert kcat.source is ParameterSource.CURATED
    assert kcat.value == Decimal("5")


# --- Derivation B: kcat = Vmax / [E]_total ----------------------------------------------------


def test_vmax_over_enzyme_concentration_derives_kcat():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    assert kcat.source is ParameterSource.DERIVED_FROM_MACRO_KINETICS
    assert kcat.value == Decimal("5")  # 500 nM_per_s / 100 nM
    assert kcat.unit == "per_sec"


def test_reconstructed_kcat_beats_heuristic_fallback():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    unusable = (ParameterSource.HEURISTIC_INITIALIZATION, ParameterSource.PLACEHOLDER)
    assert kcat.source not in unusable


def test_ai_predicted_vmax_dependency_preserved_in_derived_kcat():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-ai-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
                source="GOTENZYMES",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    assert kcat.source is ParameterSource.DERIVED_FROM_MACRO_KINETICS
    assert "GotEnzymes2" in kcat.uncertainty_text
    assert "vmax-ai-1" in kcat.provenance_refs


def test_incompatible_protein_context_never_combined():
    """The enzyme concentration is resolved for a *different* protein (p2), never p1 --
    task Sec 5's own "do not combine unrelated proteins": Derivation B must not fire."""
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(protein_id="p2"),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    assert kcat.source is ParameterSource.HEURISTIC_INITIALIZATION


def test_no_enzyme_concentration_leaves_kcat_at_heuristic():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
            ),
        ),
    )
    _, _, parameters = _declare(handoff, use_enzyme_concentrations=False)
    kcat = _param(parameters, "kcat")
    assert kcat.source is ParameterSource.HEURISTIC_INITIALIZATION


def test_declare_parameters_accepts_no_enzyme_concentrations_argument_at_all():
    """Full backward compatibility: an existing caller that never passes
    ``enzyme_concentrations`` gets identical behavior to before this increment."""
    handoff = _single_substrate_mm_handoff()
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    assert parameters.microscopic_constraints == ()


# --- Derivation C: k_eff = kcat/Km for a genuine two-reactant encounter ----------------------


def test_k_eff_from_kcat_km_for_two_reactant_context():
    handoff = _two_reactant_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
            _measurement(id="kcat-1", parameter_type="KCAT", value=Decimal("10"), unit="per_sec"),
            _measurement(
                id="km-1", parameter_type="KM", value=Decimal("1000"), unit="nM", compound_id="a"
            ),
        )
    )
    _, assignments, parameters = _declare(handoff)
    (assignment,) = assignments.assignments
    assert assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN
    kf = _param(parameters, "kf")
    assert kf.source is ParameterSource.DERIVED_FROM_MACRO_KINETICS
    assert kf.value == Decimal("10") / Decimal("1000")
    assert kf.unit == "per_nMs"


def test_k_eff_rejected_for_three_reactant_context():
    """Task's own explicit "do not apply generically to arbitrary multi-reactant
    reactions" -- forward molecularity == 3 is dimensionally ineligible."""
    handoff = _three_reactant_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="reported-law",
                parameter_type="OTHER",
                reported_rate_law="Michaelis-Menten kinetics",
            ),
            _measurement(id="kcat-1", parameter_type="KCAT", value=Decimal("10"), unit="per_sec"),
            _measurement(
                id="km-1", parameter_type="KM", value=Decimal("1000"), unit="nM", compound_id="a"
            ),
        )
    )
    _, _, parameters = _declare(handoff)
    kf = _param(parameters, "kf")
    assert kf.source is ParameterSource.HEURISTIC_INITIALIZATION


# --- Derivation D: Km + kcat constraint, never a unique kf/kr -------------------------------


def test_km_kcat_constraint_recorded_never_a_point_value():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(id="kcat-1", parameter_type="KCAT", value=Decimal("5"), unit="per_sec"),
            _measurement(id="km-1", parameter_type="KM", value=Decimal("1000"), unit="nM"),
        )
    )
    _, _, parameters = _declare(handoff)
    (constraint,) = parameters.microscopic_constraints
    assert constraint.status is IdentifiabilityStatus.PARTIALLY_CONSTRAINED
    assert constraint.constraint_expression == "kf * Km = kr + kcat"
    # Never a declared kf/kr ParameterSpecification for the MICHAELIS_MENTEN assignment --
    # the constraint is disclosure-only.
    assert not any(
        p.name.startswith("kf_") or p.name.startswith("kr_")
        for p in parameters.parameter_specifications
    )


def test_no_constraint_when_kcat_is_only_heuristic():
    """No real constraint is worth disclosing when kcat itself was never resolved to a
    genuine value -- IdentifiabilityStatus.INSUFFICIENT_EVIDENCE, no MicroscopicConstraint
    at all (never a constraint built from a fabricated heuristic number)."""
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(id="km-1", parameter_type="KM", value=Decimal("1000"), unit="nM"),
        )
    )
    _, _, parameters = _declare(handoff)
    assert parameters.microscopic_constraints == ()


# --- Determinism / no overwrite ---------------------------------------------------------------


def test_reconstruction_is_deterministic():
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("500"),
                unit="nM_per_s",
                normalized_value=Decimal("500"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, first = _declare(handoff)
    _, _, second = _declare(handoff)
    assert first == second


def test_curated_km_and_kcat_never_overwritten_by_available_macro_reconstruction():
    """Even though a Vmax + enzyme concentration combination is available and would
    produce a *different* kcat, a genuinely curated, direct kcat measurement always wins
    (Derivation A) -- and the already-curated Km is likewise never touched by anything
    this increment adds."""
    handoff = _single_substrate_mm_handoff(
        kinetic_measurements=(
            _measurement(id="kcat-1", parameter_type="KCAT", value=Decimal("42"), unit="per_sec"),
            _measurement(id="km-1", parameter_type="KM", value=Decimal("777"), unit="nM"),
            _measurement(
                id="vmax-1",
                parameter_type="VMAX",
                value=Decimal("999999"),
                unit="nM_per_s",
                normalized_value=Decimal("999999"),
                normalized_unit="nM_per_s",
            ),
        ),
        quantitative_observations=(_concentration_observation(),),
        experimental_contexts=(_context(),),
    )
    _, _, parameters = _declare(handoff)
    kcat = _param(parameters, "kcat")
    km = _param(parameters, "Km")
    assert kcat.source is ParameterSource.CURATED
    assert kcat.value == Decimal("42")
    assert km.source is ParameterSource.CURATED
    assert km.value == Decimal("777")
