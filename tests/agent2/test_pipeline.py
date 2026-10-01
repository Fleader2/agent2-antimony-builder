"""Tests for Agent 2's canonical orchestration entrypoint: ``app.agent2.pipeline``.

The simple fixtures mirror ``tests/agent2/test_model_specification.py``'s own
``_simple_two_reaction_handoff`` convention; the enzyme-state-dynamics fixture reuses
``tests/agent2/test_enzyme_state_dynamics.py``'s own already-passing "synthetic
phosphorylation regression" verbatim, to prove the two-pass wiring this module's own docstring
documents actually holds inside the real orchestrator, not just inside that file's own
hand-chained test.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.handoff.errors import MalformedHandoffPayloadError
from app.agent2.pipeline import build_canonical_downstream_handoff, run_agent2_pipeline
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedKineticMeasurement,
    CuratedQuantitativeObservation,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
)
from app.agent2.version import AGENT2_DOWNSTREAM_CONTRACT_VERSION

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


def _association(**overrides) -> CuratedReactionEnzymeAssociation:
    merged = {"reaction_id": "r1", "relationship": "CATALYZES"} | overrides
    return CuratedReactionEnzymeAssociation(**merged)


def _measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "m1",
        "parameter_type": "K",
        "value": Decimal("1"),
        "unit": "per_nMs",
        "reaction_id": "r1",
    } | overrides
    return CuratedKineticMeasurement(**merged)


def _simple_two_reaction_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
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


def _phosphorylation_regression_handoff() -> Agent1CuratedKnowledgeViewContract:
    """Reuses ``tests/agent2/test_enzyme_state_dynamics.py``'s own already-passing synthetic
    phosphorylation regression verbatim -- two states (``E``/``E_P``) of one protein (``p1``)
    both catalyze the same reaction ``r1``, connected by a curated transition pair, exercising
    the full two-pass enzyme-state-dynamics wiring this module's own docstring documents."""
    return _handoff(
        compartments=(_compartment(),),
        compounds=(_compound(id="a"), _compound(id="b")),
        reactions=(_reaction(id="r1"),),
        reaction_participants=(
            _participant(compound_id="a", role="REACTANT"),
            _participant(compound_id="b", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _association(protein_id="p1"),
            _association(enzyme_state_id="E"),
            _association(enzyme_state_id="E_P"),
        ),
        kinetic_measurements=(
            _measurement(
                id="m-e", enzyme_state_id="E", reported_rate_law="k1 * a", parameter_type="K"
            ),
        ),
        enzyme_states=(
            CuratedEnzymeState(
                id="E", state_type="unmodified", protein_id="p1", compartment_id="cyto"
            ),
            CuratedEnzymeState(
                id="E_P", state_type="phosphorylated", protein_id="p1", compartment_id="cyto"
            ),
        ),
        enzyme_state_transitions=(
            CuratedEnzymeStateTransition(
                id="t-phos", from_state_id="E", to_state_id="E_P", transition_type="phosphorylation"
            ),
            CuratedEnzymeStateTransition(
                id="t-dephos",
                from_state_id="E_P",
                to_state_id="E",
                transition_type="dephosphorylation",
            ),
        ),
        quantitative_observations=(
            CuratedQuantitativeObservation(
                id="obs-p1-total",
                observation_type="PROTEIN_CONCENTRATION",
                value=Decimal("100"),
                unit="nM",
                evidence_class="REFERENCE_BASELINE",
                protein_id="p1",
            ),
            CuratedQuantitativeObservation(
                id="obs-e-specific",
                observation_type="PROTEIN_CONCENTRATION",
                value=Decimal("30"),
                unit="nM",
                evidence_class="REFERENCE_BASELINE",
                enzyme_state_id="E",
            ),
        ),
    )


# --- Tests -------------------------------------------------------------------------------------


def test_accepts_a_contract_object_directly():
    handoff = _simple_two_reaction_handoff()
    result = run_agent2_pipeline(handoff)
    assert result.downstream_handoff["contract_version"] == AGENT2_DOWNSTREAM_CONTRACT_VERSION
    assert len(result.downstream_handoff["reactions"]) == 2


def test_accepts_a_plain_dict_and_matches_the_object_path_exactly():
    handoff = _simple_two_reaction_handoff()
    via_object = run_agent2_pipeline(handoff).downstream_handoff

    view_dict = {
        "contract_version": handoff.contract_version,
        "organism_id": handoff.organism_id,
        "compartments": [dataclasses.asdict(c) for c in handoff.compartments],
        # Agent 1's own real view names a compound's name field "canonical_name" --
        # translate_agent1_view_to_agent2 maps it to CuratedCompound's own "name" field; the
        # two are not spelled identically, unlike every other field here.
        "compounds": [{"id": c.id, "canonical_name": c.name} for c in handoff.compounds],
        "reactions": [dataclasses.asdict(r) for r in handoff.reactions],
        "reaction_participants": [dataclasses.asdict(p) for p in handoff.reaction_participants],
        "reaction_enzyme_associations": [],
        "regulatory_interactions": [],
        "kinetic_measurements": [],
        "enzyme_states": [],
        "enzyme_modifications": [],
        "allosteric_interactions": [],
        "enzyme_state_transitions": [],
        "experimental_contexts": [],
        "perturbations": [],
        "quantitative_observations": [],
        "claims": [],
        "evidence": [],
        "confidence_summaries": [],
        "publications": [],
    }
    via_dict = run_agent2_pipeline(view_dict).downstream_handoff
    assert via_dict == via_object


def test_does_not_mutate_its_input():
    handoff = _simple_two_reaction_handoff()
    before = dataclasses.replace(handoff)
    run_agent2_pipeline(handoff)
    assert handoff == before


def test_raises_on_malformed_dict_input():
    with pytest.raises(MalformedHandoffPayloadError):
        run_agent2_pipeline({"organism_id": "org-1"})  # missing required contract_version


def test_is_deterministic():
    handoff = _simple_two_reaction_handoff()
    first = run_agent2_pipeline(handoff).downstream_handoff
    second = run_agent2_pipeline(handoff).downstream_handoff
    assert first == second


def test_canonical_downstream_handoff_has_every_required_top_level_field():
    handoff = _simple_two_reaction_handoff()
    downstream = run_agent2_pipeline(handoff).downstream_handoff
    required_fields = {
        "contract_version",
        "model_id",
        "network_id",
        "antimony_text",
        "antimony_generator_version",
        "readiness",
        "unresolved_reaction_ids",
        "unresolved_kinetic_law_ids",
        "compartments",
        "species",
        "reactions",
        "kinetic_laws",
        "parameters",
        "model_assumptions",
    }
    assert required_fields <= downstream.keys()


def test_canonical_downstream_handoff_species_includes_initialization_source_key():
    handoff = _simple_two_reaction_handoff()
    downstream = run_agent2_pipeline(handoff).downstream_handoff
    assert downstream["species"]
    assert "initialization_source" in downstream["species"][0]


def test_canonical_downstream_handoff_parameters_include_bounds_and_fixed_keys():
    # The bare two-reaction handoff has no kinetic evidence at all, so it declares zero
    # parameters (correct, documented Agent 2 behavior for an UNASSIGNED law) -- the
    # phosphorylation-regression fixture has real kinetic evidence and declares real parameters.
    handoff = _phosphorylation_regression_handoff()
    downstream = run_agent2_pipeline(handoff).downstream_handoff
    assert downstream["parameters"]
    for key in ("lower_bound", "upper_bound", "fixed"):
        assert key in downstream["parameters"][0]


def test_enzyme_state_dynamics_two_pass_wiring_applies_inside_the_canonical_pipeline():
    """The central orchestration-correctness test: the enzyme-state-pool-conservation
    disclosure (only produced by the real two-pass wiring) must appear in the canonical
    pipeline's own output for a handoff that actually exercises it."""
    handoff = _phosphorylation_regression_handoff()
    result = run_agent2_pipeline(handoff)
    downstream = result.downstream_handoff

    assert any(
        a["category"] == "enzyme_state_dynamics"
        and a["reason_code"] == "ENZYME_STATE_POOL_CONSERVATION_APPLIED"
        for a in downstream["model_assumptions"]
    )
    assert result.package.model_specification.enzyme_state_pools
    assert result.package.model_specification.enzyme_state_concentrations


def test_build_canonical_downstream_handoff_is_a_pure_function_of_its_inputs():
    handoff = _simple_two_reaction_handoff()
    result = run_agent2_pipeline(handoff)
    rebuilt = build_canonical_downstream_handoff(result.package.model_specification, result.package)
    assert rebuilt == result.downstream_handoff
