"""Tests for the Multi-Measurement Kinetic Evidence Consolidation and Prioritization
increment: ``app.agent2.kinetics.evidence_consolidation``.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.kinetics.evidence_consolidation import (
    ConditionMatch,
    ConsolidationClassification,
    condition_match_for_measurement,
    consolidate_by_substrate,
    consolidate_concept,
    publication_years_for_network,
    reference_experimental_context_for_network,
)
from app.agent2.types import (
    CuratedExperimentalContext,
    CuratedKineticMeasurement,
    CuratedPublication,
    FullNetwork,
)

# --- Fixtures --------------------------------------------------------------------------------


def _m(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km1",
        "parameter_type": "KM",
        "value": Decimal("100"),
        "unit": "nM",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _ctx(**overrides) -> CuratedExperimentalContext:
    merged = {"id": "ctx1"} | overrides
    return CuratedExperimentalContext(**merged)


def _network(**overrides) -> FullNetwork:
    merged = {"network_id": "n1", "name": "n1"} | overrides
    return FullNetwork(**merged)


# --- Single-measurement behavior unchanged ----------------------------------------------------


def test_single_measurement_is_classified_single_and_selected():
    concept = consolidate_concept((_m(id="km1"),))
    assert concept.classification is ConsolidationClassification.SINGLE
    assert concept.selected_measurement_id == "km1"
    assert concept.measurement_ids == ("km1",)


# --- Two identical Km records -> eligible / corroborating -------------------------------------


def test_two_identical_measurements_are_corroborating_and_either_selectable():
    concept = consolidate_concept(
        (
            _m(id="km1", value=Decimal("100"), unit="nM"),
            _m(id="km2", value=Decimal("100"), unit="nM"),
        )
    )
    assert concept.classification is ConsolidationClassification.CORROBORATING
    assert concept.selected_measurement_id in ("km1", "km2")
    assert concept.measurement_ids == ("km1", "km2")


# --- Differing values, same context -> one concept, prioritized selection ---------------------


def test_differing_values_same_context_is_one_disagreeing_concept():
    concept = consolidate_concept(
        (
            _m(id="km1", value=Decimal("100"), unit="nM"),
            _m(id="km2", value=Decimal("500"), unit="nM"),
        )
    )
    assert concept.classification is ConsolidationClassification.DISAGREEING
    assert concept.selected_measurement_id is not None
    assert concept.measurement_ids == ("km1", "km2")


# --- All provenance preserved ------------------------------------------------------------------


def test_all_measurement_ids_preserved_regardless_of_classification():
    for classification_inputs in (
        (_m(id="km1"),),
        (_m(id="km1"), _m(id="km2")),
        (_m(id="km1"), _m(id="km2", value=Decimal("999"))),
        (_m(id="km1", organism_id="org1"), _m(id="km2", organism_id="org2")),
    ):
        concept = consolidate_concept(classification_inputs)
        assert concept.measurement_ids == tuple(sorted(m.id for m in classification_inputs))


# --- Incompatible experimental contexts (organism conflict) remain distinct -------------------


def test_organism_conflict_is_context_distinct_and_unselected():
    concept = consolidate_concept(
        (
            _m(id="km1", organism_id="org1", value=Decimal("100")),
            _m(id="km2", organism_id="org2", value=Decimal("100")),
        )
    )
    assert concept.classification is ConsolidationClassification.CONTEXT_DISTINCT
    assert concept.selected_measurement_id is None
    assert concept.measurement_ids == ("km1", "km2")


def test_unknown_organism_never_conflicts():
    """Unknown (None) organism on either side is a real absence of information, never a
    confirmed conflict -- mirrors classify_context_compatibility's own discipline."""
    concept = consolidate_concept(
        (
            _m(id="km1", organism_id="org1", value=Decimal("100")),
            _m(id="km2", organism_id=None, value=Decimal("100")),
        )
    )
    assert concept.classification is ConsolidationClassification.CORROBORATING


def test_every_candidate_incompatible_with_target_is_unresolved():
    concept = consolidate_concept(
        (
            _m(id="km1", organism_id="org2", value=Decimal("100")),
            _m(id="km2", organism_id="org2", value=Decimal("500")),
        ),
        target_organism_id="org1",
    )
    assert concept.classification is ConsolidationClassification.UNRESOLVED
    assert concept.selected_measurement_id is None
    assert concept.measurement_ids == ("km1", "km2")


# --- Different substrates remain separate concepts ---------------------------------------------


def test_consolidate_by_substrate_splits_by_compound_id():
    evidence = (
        _m(id="km-a", compound_id="glc", value=Decimal("100")),
        _m(id="km-b", compound_id="atp", value=Decimal("200")),
        _m(id="km-c", compound_id=None, value=Decimal("300")),
    )
    concepts = consolidate_by_substrate(evidence)
    assert len(concepts) == 3
    by_ids = {c.measurement_ids for c in concepts}
    assert by_ids == {("km-a",), ("km-b",), ("km-c",)}


def test_consolidate_by_substrate_never_merges_across_compounds_even_when_values_agree():
    evidence = (
        _m(id="km-a", compound_id="glc", value=Decimal("100"), unit="nM"),
        _m(id="km-b", compound_id="atp", value=Decimal("100"), unit="nM"),
    )
    concepts = consolidate_by_substrate(evidence)
    assert len(concepts) == 2
    assert all(c.classification is ConsolidationClassification.SINGLE for c in concepts)


# --- Condition matching (Priority 2) ------------------------------------------------------------


def test_no_reference_context_is_conditions_unknown():
    assert condition_match_for_measurement(_m(), None) is ConditionMatch.CONDITIONS_UNKNOWN


def test_exact_match_against_reference_is_canonical():
    reference = _ctx(
        organism_id="org1", strain="S288C", temperature_c=Decimal("30"), ph=Decimal("7")
    )
    measurement = _m(
        organism_id="org1", strain="S288C", temperature_c=Decimal("30"), ph=Decimal("7")
    )
    assert (
        condition_match_for_measurement(measurement, reference)
        is ConditionMatch.CANONICAL_CONDITIONS
    )


def test_conflicting_condition_field_is_noncanonical():
    reference = _ctx(organism_id="org1", ph=Decimal("7"))
    measurement = _m(organism_id="org1", ph=Decimal("8"))
    assert (
        condition_match_for_measurement(measurement, reference)
        is ConditionMatch.NONCANONICAL_CONDITIONS
    )


def test_measurement_with_no_condition_fields_is_near_canonical_not_mismatched():
    """Neither side disagrees (the measurement reports nothing to disagree with) -- this
    mirrors classify_context_compatibility's own COMPATIBLE_REFERENCE precedent exactly:
    "at least one side reports a detail field the other leaves unset" is a compatible,
    not-fully-confirmed match, never a mismatch and never fully unknown."""
    reference = _ctx(organism_id="org1", ph=Decimal("7"))
    measurement = _m(organism_id="org1")
    assert (
        condition_match_for_measurement(measurement, reference)
        is ConditionMatch.NEAR_CANONICAL_CONDITIONS
    )


def test_neither_side_reports_any_condition_field_is_conditions_unknown():
    reference = _ctx(organism_id="org1")
    measurement = _m(organism_id="org1")
    assert (
        condition_match_for_measurement(measurement, reference)
        is ConditionMatch.CONDITIONS_UNKNOWN
    )


def test_partial_overlap_is_near_canonical():
    reference = _ctx(organism_id="org1", ph=Decimal("7"))
    measurement = _m(organism_id="org1", ph=Decimal("7"), temperature_c=Decimal("30"))
    assert (
        condition_match_for_measurement(measurement, reference)
        is ConditionMatch.NEAR_CANONICAL_CONDITIONS
    )


def test_exact_context_measurement_beats_unknown_context_measurement_in_selection():
    reference = _ctx(organism_id="org1", ph=Decimal("7"), temperature_c=Decimal("30"))
    exact = _m(
        id="km-exact",
        value=Decimal("100"),
        organism_id="org1",
        ph=Decimal("7"),
        temperature_c=Decimal("30"),
    )
    unknown = _m(id="km-unknown", value=Decimal("500"))
    concept = consolidate_concept((exact, unknown), reference_context=reference)
    assert concept.classification is ConsolidationClassification.DISAGREEING
    assert concept.selected_measurement_id == "km-exact"


def test_canonical_conditions_beats_noncanonical_regardless_of_which_is_alphabetically_first():
    reference = _ctx(organism_id="org1", ph=Decimal("7"))
    canonical = _m(id="km-z-canonical", value=Decimal("100"), organism_id="org1", ph=Decimal("7"))
    noncanonical = _m(
        id="km-a-noncanonical", value=Decimal("500"), organism_id="org1", ph=Decimal("8")
    )
    concept = consolidate_concept((canonical, noncanonical), reference_context=reference)
    assert concept.selected_measurement_id == "km-z-canonical"


# --- Publication recency (Priority 5) -- a disclosed, real data-availability gap ---------------


def test_canonical_condition_older_measurement_beats_newer_noncanonical_measurement():
    """Condition relevance (Priority 2) always outranks recency (Priority 5) -- a newer
    but noncanonical-condition measurement never wins over an older canonical one."""
    reference = _ctx(organism_id="org1", ph=Decimal("7"))
    older_canonical = _m(
        id="km-old",
        value=Decimal("100"),
        organism_id="org1",
        ph=Decimal("7"),
        publication_id="pub-old",
    )
    newer_noncanonical = _m(
        id="km-new",
        value=Decimal("500"),
        organism_id="org1",
        ph=Decimal("8"),
        publication_id="pub-new",
    )
    concept = consolidate_concept(
        (older_canonical, newer_noncanonical),
        reference_context=reference,
        publication_years={"pub-old": 2005, "pub-new": 2023},
    )
    assert concept.selected_measurement_id == "km-old"


def test_newer_measurement_wins_when_otherwise_equivalent():
    """With condition match and completeness tied, the measurement naming the more
    recent primary publication year wins."""
    older = _m(id="km-old", value=Decimal("100"), publication_id="pub-old")
    newer = _m(id="km-new", value=Decimal("500"), publication_id="pub-new")
    concept = consolidate_concept(
        (older, newer), publication_years={"pub-old": 2005, "pub-new": 2023}
    )
    assert concept.selected_measurement_id == "km-new"


def test_no_publication_years_supplied_falls_through_to_deterministic_tie_break():
    """Every real call site in this repository passes no publication_years today (Agent
    2's own handoff has no publication year field) -- recency always ties, and selection
    falls through to the final source/source_id/id tie-break."""
    a = _m(id="km-a", value=Decimal("100"), publication_id="pub-a")
    b = _m(id="km-b", value=Decimal("500"), publication_id="pub-b")
    concept = consolidate_concept((a, b))
    assert concept.selected_measurement_id == "km-a"


# --- Deterministic tie-break ---------------------------------------------------------------


def test_tie_break_is_deterministic_and_repeatable():
    a = _m(id="km-b", value=Decimal("100"))
    b = _m(id="km-a", value=Decimal("500"))
    concept_1 = consolidate_concept((a, b))
    concept_2 = consolidate_concept((b, a))
    assert concept_1.selected_measurement_id == concept_2.selected_measurement_id == "km-a"


def test_tie_break_uses_source_before_id():
    a = _m(id="km-z", value=Decimal("100"), source="BRENDA")
    b = _m(id="km-a", value=Decimal("500"), source="SABIORK")
    concept = consolidate_concept((a, b))
    assert concept.selected_measurement_id == "km-z"


# --- Reference-context resolution ---------------------------------------------------------------


def test_reference_experimental_context_for_network_finds_the_one_reference_context():
    ctx = _ctx(id="ctx1", organism_id="org1", classification="REFERENCE")
    network = _network(organism_id="org1", experimental_contexts=(ctx,))
    assert reference_experimental_context_for_network(network) is ctx


def test_reference_experimental_context_for_network_none_when_zero_or_ambiguous():
    network_none = _network(organism_id="org1", experimental_contexts=())
    assert reference_experimental_context_for_network(network_none) is None

    ctx_a = _ctx(id="ctx-a", organism_id="org1", classification="REFERENCE")
    ctx_b = _ctx(id="ctx-b", organism_id="org1", classification="REFERENCE")
    network_ambiguous = _network(organism_id="org1", experimental_contexts=(ctx_a, ctx_b))
    assert reference_experimental_context_for_network(network_ambiguous) is None


def test_reference_experimental_context_for_network_ignores_other_organisms():
    ctx = _ctx(id="ctx1", organism_id="org2", classification="REFERENCE")
    network = _network(organism_id="org1", experimental_contexts=(ctx,))
    assert reference_experimental_context_for_network(network) is None


# --- Publication-years wiring (Publication Date Handoff increment) -----------------------------


def test_publication_years_for_network_builds_real_mapping():
    network = _network(
        publications=(
            CuratedPublication(id="pub-1", year=2005),
            CuratedPublication(id="pub-2", year=2020),
        )
    )
    assert publication_years_for_network(network) == {"pub-1": 2005, "pub-2": 2020}


def test_publication_years_for_network_omits_missing_years():
    network = _network(
        publications=(
            CuratedPublication(id="pub-1", year=2005),
            CuratedPublication(id="pub-2", year=None),
        )
    )
    assert publication_years_for_network(network) == {"pub-1": 2005}


def test_publication_years_for_network_empty_when_no_publications():
    assert publication_years_for_network(_network()) == {}


def test_real_publication_years_change_selection_end_to_end():
    """The real wiring, not just consolidate_concept's own direct publication_years
    parameter: a network with real CuratedPublication records changes which measurement
    consolidate_by_substrate selects, via publication_years_for_network."""
    older = _m(id="km-old", value=Decimal("100"), publication_id="pub-old")
    newer = _m(id="km-new", value=Decimal("500"), publication_id="pub-new")
    network = _network(
        publications=(
            CuratedPublication(id="pub-old", year=2005),
            CuratedPublication(id="pub-new", year=2023),
        )
    )
    years = publication_years_for_network(network)
    concept = consolidate_concept((older, newer), publication_years=years)
    assert concept.selected_measurement_id == "km-new"
