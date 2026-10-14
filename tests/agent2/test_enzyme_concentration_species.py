"""Tests for the Explicit Enzyme Concentration Representation increment.

Two layers, mirroring ``tests/agent2/test_enzyme_state_dynamics.py``'s own convention:

* Builder-level tests construct a ``FullNetwork`` directly to pin
  ``app.agent2.enzyme_concentration_species.build_enzyme_concentration_species``'s own
  dedup/skip/unresolved-handling rules exactly.
* Pipeline-level tests run the real, full ``run_agent2_pipeline`` (mirroring
  ``tests/agent2/test_model_specification.py``/``test_pipeline.py``) to confirm genuine
  end-to-end behavior: explicit enzyme species actually appear in the generated Antimony
  text, multiplied into a single-substrate Michaelis-Menten expression, named by gene
  symbol, and round-tripped through the canonical downstream handoff.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.antimony.naming import build_identifier_map, build_symbol_provenance_map
from app.agent2.enzyme_concentration_species import (
    EnzymeConcentrationSpeciesReferenceError,
    build_enzyme_concentration_species,
)
from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSource,
    KineticLawReasonCode,
)
from app.agent2.model_specification.mapping import build_expression_and_species
from app.agent2.pipeline import run_agent2_pipeline
from app.agent2.quantitative_context.types import (
    QuantitativeContextResolutionOutcome,
    QuantitativeContextResolutionSet,
)
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedCompartment,
    CuratedCompound,
    CuratedExperimentalContext,
    CuratedGene,
    CuratedProtein,
    CuratedQuantitativeObservation,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    EnzymeConcentration,
    EnzymeConcentrationBasis,
    FullNetwork,
    KineticLawRateScope,
    KineticLawType,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionEnzymeAssociation,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- FullNetwork-direct fixtures (builder-level tests) ------------------------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    compartment_id = overrides.get("compartment_id", "cyto")
    merged = {
        "compartment_id": compartment_id,
        "name": compartment_id,
        "source_scope": CompartmentSourceScope.AGENT1_CURATED,
        "source_entity_id": "agent1-c1",
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    species_id = overrides.get("species_id", "a")
    merged = {"species_id": species_id, "name": species_id, "compartment_id": "cyto"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "a",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    reaction_id = overrides.get("reaction_id", "r1")
    merged = {
        "reaction_id": reaction_id,
        "name": reaction_id,
        "participants": (
            _participant(species_id="a", role=ParticipantRole.REACTANT),
            _participant(species_id="b", role=ParticipantRole.PRODUCT),
        ),
        "reversible": False,
    } | overrides
    return ReactionSpecification(**merged)


def _association(**overrides) -> ReactionEnzymeAssociation:
    merged = {
        "association_id": overrides.get("association_id", "assoc-1"),
        "reaction_id": "r1",
        "protein_id": "p1",
    } | overrides
    return ReactionEnzymeAssociation(**merged)


def _protein(**overrides) -> CuratedProtein:
    merged = {"id": overrides.get("id", "p1"), "name": overrides.get("name", "Test protein")}
    merged |= overrides
    return CuratedProtein(**merged)


def _network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "test network",
        "compartments": (_compartment(), _compartment(compartment_id="mito")),
        "species": (_species(species_id="a"), _species(species_id="b", name="b")),
        "reactions": (_reaction(),),
        "enzyme_associations": (_association(),),
        "proteins": (_protein(),),
    } | overrides
    return FullNetwork(**merged)


def _concentration_set(**kwargs) -> QuantitativeContextResolutionSet:
    protein_id = kwargs.pop("protein_id", "p1")
    value = kwargs.pop("value", Decimal("100"))
    basis = kwargs.pop("basis", EnzymeConcentrationBasis.REFERENCE_CONCENTRATION)
    concentration = EnzymeConcentration(
        protein_id=protein_id, value=value, basis=basis, policy_version="test-policy"
    )
    outcome = QuantitativeContextResolutionOutcome(
        protein_id=protein_id, concentration=concentration
    )
    return QuantitativeContextResolutionSet(
        network_id=kwargs.pop("network_id", "n1"),
        policy_version="test-policy",
        outcomes=(outcome,),
    )


def _unresolved_set(*, protein_id: str = "p1", network_id: str = "n1"):
    outcome = QuantitativeContextResolutionOutcome(
        protein_id=protein_id,
        concentration=None,
        unresolved_reason_code="PROTEIN_CONCENTRATION_UNRESOLVED",
    )
    return QuantitativeContextResolutionSet(
        network_id=network_id, policy_version="test-policy", outcomes=(outcome,)
    )


# --- Builder-level tests ------------------------------------------------------------------------


def test_measured_concentration_used_directly_as_explicit_species_initial_value():
    network = _network()
    result = build_enzyme_concentration_species(
        network, _concentration_set(value=Decimal("250"))
    )
    (species,) = (s for s in result.network.species if s.source_protein_id == "p1")
    assert species.initial_concentration == Decimal("250")
    assert species.initialization_source is ParameterSource.LITERATURE_DERIVED
    assert species.compartment_id == "cyto"
    assert result.species_by_protein_and_compartment[("p1", "cyto")] == species.species_id


def test_unresolved_concentration_still_produces_explicit_species_with_no_numeric_value():
    network = _network()
    result = build_enzyme_concentration_species(network, _unresolved_set())
    (species,) = (s for s in result.network.species if s.source_protein_id == "p1")
    assert species.initial_concentration is None
    assert species.initialization_source is None
    assert any("could not be resolved" in a for a in species.assumptions)


def test_no_enzyme_concentrations_supplied_still_produces_explicit_species_unresolved():
    network = _network()
    result = build_enzyme_concentration_species(network)
    (species,) = (s for s in result.network.species if s.source_protein_id == "p1")
    assert species.initial_concentration is None


def test_species_deduplicated_across_multiple_reactions_in_same_compartment():
    network = _network(
        reactions=(_reaction(reaction_id="r1"), _reaction(reaction_id="r2")),
        enzyme_associations=(
            _association(association_id="a1", reaction_id="r1", protein_id="p1"),
            _association(association_id="a2", reaction_id="r2", protein_id="p1"),
        ),
    )
    result = build_enzyme_concentration_species(network, _concentration_set())
    enzyme_species = [s for s in result.network.species if s.source_protein_id == "p1"]
    assert len(enzyme_species) == 1
    assert result.species_by_protein_and_compartment[("p1", "cyto")] == enzyme_species[0].species_id


def test_multiple_isozymes_each_get_their_own_distinct_species():
    network = _network(
        proteins=(_protein(id="p1", name="Protein One"), _protein(id="p2", name="Protein Two")),
        enzyme_associations=(
            _association(association_id="a1", protein_id="p1"),
            _association(association_id="a2", protein_id="p2"),
        ),
    )
    result = build_enzyme_concentration_species(network)
    enzyme_species_ids = {
        s.source_protein_id for s in result.network.species if s.source_protein_id
    }
    assert enzyme_species_ids == {"p1", "p2"}
    assert result.species_by_protein_and_compartment[("p1", "cyto")] != (
        result.species_by_protein_and_compartment[("p2", "cyto")]
    )


def test_reaction_spanning_multiple_compartments_skips_that_catalytic_context():
    network = _network(
        species=(
            _species(species_id="a", compartment_id="cyto"),
            _species(species_id="b", compartment_id="mito"),
        ),
    )
    result = build_enzyme_concentration_species(network, _concentration_set())
    assert not any(s.source_protein_id == "p1" for s in result.network.species)
    assert result.species_by_protein_and_compartment == {}


def test_protein_not_exposed_in_network_proteins_is_skipped_never_fabricated():
    network = _network(proteins=())
    result = build_enzyme_concentration_species(network, _concentration_set())
    assert not any(s.source_protein_id == "p1" for s in result.network.species)


def test_requires_full_network():
    import pytest

    with pytest.raises(EnzymeConcentrationSpeciesReferenceError):
        build_enzyme_concentration_species("not a network")


def test_network_id_mismatch_raises():
    import pytest

    network = _network(network_id="n1")
    mismatched = _concentration_set(network_id="n2")
    with pytest.raises(EnzymeConcentrationSpeciesReferenceError):
        build_enzyme_concentration_species(network, mismatched)


# --- mapping.py-level tests: expression injection scope -----------------------------------------


def _mm_assignment(**overrides) -> KineticLawAssignment:
    merged = {
        "assignment_id": "asg-1",
        "reaction_id": "r1",
        "kinetic_law_type": KineticLawType.MICHAELIS_MENTEN,
        "assignment_source": KineticLawAssignmentSource.HEURISTIC,
        "policy_version": "test-policy",
        "protein_id": "p1",
        "reason_codes": (KineticLawReasonCode.ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT,),
        "explanation": "test fixture",
    } | overrides
    return KineticLawAssignment(**merged)


def _mm_parameters() -> tuple[ParameterSpecification, ...]:
    return (
        ParameterSpecification(
            parameter_id="kcat_r1",
            name="kcat_r1",
            source=ParameterSource.HEURISTIC_INITIALIZATION,
            kinetic_law_assignment_id="asg-1",
        ),
        ParameterSpecification(
            parameter_id="Km_r1_a",
            name="Km_r1_a",
            source=ParameterSource.HEURISTIC_INITIALIZATION,
            kinetic_law_assignment_id="asg-1",
        ),
    )


def test_single_substrate_mm_injects_explicit_enzyme_species_when_resolvable():
    reaction = _reaction()
    expression, species_ids, scope = build_expression_and_species(
        _mm_assignment(),
        reaction,
        _mm_parameters(),
        enzyme_species_lookup={("p1", "cyto"): "E_p1"},
        species_by_id={"a": _species(species_id="a"), "b": _species(species_id="b")},
    )
    assert expression == "kcat_r1 * E_p1 * a / (Km_r1_a + a)"
    assert "E_p1" in species_ids
    assert scope is KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION


def test_single_substrate_mm_stays_lumped_without_a_lookup():
    reaction = _reaction()
    expression, species_ids, scope = build_expression_and_species(
        _mm_assignment(), reaction, _mm_parameters()
    )
    assert expression == "kcat_r1 * a / (Km_r1_a + a)"
    assert "E_p1" not in species_ids
    assert scope is KineticLawRateScope.LUMPED_EFFECTIVE_RATE


def test_mass_action_never_injects_an_enzyme_species_even_when_resolvable():
    reaction = _reaction()
    assignment = _mm_assignment(kinetic_law_type=KineticLawType.MASS_ACTION)
    k_param = ParameterSpecification(
        parameter_id="k_r1",
        name="k_r1",
        source=ParameterSource.HEURISTIC_INITIALIZATION,
        kinetic_law_assignment_id="asg-1",
    )
    expression, species_ids, scope = build_expression_and_species(
        assignment,
        reaction,
        (k_param,),
        enzyme_species_lookup={("p1", "cyto"): "E_p1"},
        species_by_id={"a": _species(species_id="a"), "b": _species(species_id="b")},
    )
    assert "E_p1" not in (expression or "")
    assert "E_p1" not in species_ids
    assert scope is KineticLawRateScope.LUMPED_EFFECTIVE_RATE


# --- Pipeline-level (real, end-to-end) tests -----------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.7"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _curated_compartment(**overrides) -> CuratedCompartment:
    merged = {"id": "cyto", "name": "cytosol"} | overrides
    return CuratedCompartment(**merged)


def _curated_compound(**overrides) -> CuratedCompound:
    merged = {"id": "a", "name": "A"} | overrides
    return CuratedCompound(**merged)


def _curated_reaction(**overrides) -> CuratedReaction:
    reaction_id = overrides.get("id", "r1")
    merged = {"id": reaction_id, "name": reaction_id} | overrides
    return CuratedReaction(**merged)


def _curated_participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "a",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _curated_enzyme_association(**overrides) -> CuratedReactionEnzymeAssociation:
    merged = {"reaction_id": "r1", "protein_id": "p1", "relationship": "CATALYZES"} | overrides
    return CuratedReactionEnzymeAssociation(**merged)


def _curated_context(**overrides) -> CuratedExperimentalContext:
    merged = {
        "id": "ctx-1",
        "organism_id": "org-1",
        "strain": "BY4741",
        "classification": "REFERENCE",
        "source": "SGD",
    } | overrides
    return CuratedExperimentalContext(**merged)


def _reference_abundance_observation(**overrides) -> CuratedQuantitativeObservation:
    merged = {
        "id": "obs-abundance-1",
        "observation_type": "PROTEIN_ABUNDANCE",
        "value": Decimal("6670"),
        "unit": "molecules/cell",
        "evidence_class": "REFERENCE_BASELINE",
        "normalized_value": Decimal("6670"),
        "normalized_unit": "molecules_per_cell",
        "protein_id": "p1",
        "organism_id": "org-1",
        "source": "SGD",
        "source_id": "sgd-protein-abundance:S1",
    } | overrides
    return CuratedQuantitativeObservation(**merged)


def _single_substrate_mm_handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    """One single-reactant/single-product reaction, catalyzed by a gene-named protein with a
    resolvable (tier-5, reference-abundance-and-assumed-volume) concentration -- the Michaelis-
    Menten heuristic's own single-reactant path, exactly as ``test_model_specification.py``'s
    own ``_michaelis_menten_handoff`` confirms it is selected."""
    merged = {
        "compartments": (_curated_compartment(),),
        "compounds": (_curated_compound(id="a"), _curated_compound(id="b")),
        "reactions": (_curated_reaction(id="r1"),),
        "reaction_participants": (
            _curated_participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _curated_participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
        ),
        "reaction_enzyme_associations": (
            _curated_enzyme_association(reaction_id="r1", protein_id="p1"),
        ),
        "genes": (CuratedGene(id="g1", symbol="ACC1"),),
        "proteins": (CuratedProtein(id="p1", name="Acetyl-CoA carboxylase", gene_id="g1"),),
        "experimental_contexts": (_curated_context(),),
        "quantitative_observations": (_reference_abundance_observation(),),
    } | overrides
    return _handoff(**merged)


def test_pipeline_injects_explicit_gene_named_enzyme_species_into_mm_expression():
    result = run_agent2_pipeline(_single_substrate_mm_handoff())
    model = result.package.model_specification
    (species,) = (s for s in model.full_network.species if s.source_protein_id == "p1")
    assert species.initial_concentration is not None
    (law,) = (law for law in model.kinetic_laws if law.reaction_id == "r1")
    assert law.rate_law_scope is KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION
    assert species.species_id in law.species_ids
    kcat_id = next(p for p in law.parameter_ids if p.startswith("kcat") or "kcat" in p)
    assert f"{kcat_id} * {species.species_id} *" in law.expression

    id_map = build_identifier_map(model)
    assert id_map.species[species.species_id] == "s_ACC1_cytosol"


def test_pipeline_antimony_text_contains_explicit_enzyme_species_declaration():
    result = run_agent2_pipeline(_single_substrate_mm_handoff())
    antimony_text = result.package.full_antimony.antimony_text
    assert "species s_ACC1_cytosol in c_cytosol;" in antimony_text
    assert "s_ACC1_cytosol" in antimony_text
    assert "* s_ACC1_cytosol *" in antimony_text


def test_pipeline_falls_back_to_protein_name_when_no_gene_symbol_curated():
    handoff = _single_substrate_mm_handoff(
        genes=(),
        proteins=(CuratedProtein(id="p1", name="Acetyl-CoA carboxylase"),),
    )
    result = run_agent2_pipeline(handoff)
    model = result.package.model_specification
    (species,) = (s for s in model.full_network.species if s.source_protein_id == "p1")
    id_map = build_identifier_map(model)
    assert id_map.species[species.species_id] == "s_Acetyl_CoA_carboxylase_cytosol"


def test_missing_abundance_data_leaves_enzyme_species_explicit_but_unresolved():
    handoff = _single_substrate_mm_handoff(
        quantitative_observations=(), experimental_contexts=()
    )
    result = run_agent2_pipeline(handoff)
    model = result.package.model_specification
    (species,) = (s for s in model.full_network.species if s.source_protein_id == "p1")
    assert species.initial_concentration is None
    assert any("could not be resolved" in a for a in species.assumptions)
    # Readiness is unaffected: an unresolved enzyme concentration is a disclosed assumption,
    # never a blocker, mirroring every other unresolved-value convention in this codebase.
    (law,) = (law for law in model.kinetic_laws if law.reaction_id == "r1")
    assert law.rate_law_scope is KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION


def test_two_reactions_sharing_one_catalyst_in_one_compartment_reuse_one_species():
    handoff = _single_substrate_mm_handoff(
        compounds=(
            _curated_compound(id="a"),
            _curated_compound(id="b"),
            _curated_compound(id="c"),
        ),
        reactions=(_curated_reaction(id="r1"), _curated_reaction(id="r2")),
        reaction_participants=(
            _curated_participant(reaction_id="r1", compound_id="a", role="REACTANT"),
            _curated_participant(reaction_id="r1", compound_id="b", role="PRODUCT"),
            _curated_participant(reaction_id="r2", compound_id="b", role="REACTANT"),
            _curated_participant(reaction_id="r2", compound_id="c", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            _curated_enzyme_association(reaction_id="r1", protein_id="p1"),
            _curated_enzyme_association(reaction_id="r2", protein_id="p1"),
        ),
    )
    result = run_agent2_pipeline(handoff)
    model = result.package.model_specification
    enzyme_species = [s for s in model.full_network.species if s.source_protein_id == "p1"]
    assert len(enzyme_species) == 1
    laws = [law for law in model.kinetic_laws if law.reaction_id in ("r1", "r2")]
    assert len(laws) == 2
    for law in laws:
        assert law.rate_law_scope is KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION
        assert enzyme_species[0].species_id in law.species_ids


def test_multiple_isozymes_each_get_a_distinct_species_and_are_composed_additively():
    handoff = _single_substrate_mm_handoff(
        genes=(CuratedGene(id="g1", symbol="ACC1"), CuratedGene(id="g2", symbol="HFA1")),
        proteins=(
            CuratedProtein(id="p1", name="Acetyl-CoA carboxylase 1", gene_id="g1"),
            CuratedProtein(id="p2", name="Acetyl-CoA carboxylase 2", gene_id="g2"),
        ),
        reaction_enzyme_associations=(
            _curated_enzyme_association(reaction_id="r1", protein_id="p1"),
            _curated_enzyme_association(reaction_id="r1", protein_id="p2"),
        ),
        quantitative_observations=(
            _reference_abundance_observation(id="obs-1", protein_id="p1"),
            _reference_abundance_observation(id="obs-2", protein_id="p2", value=Decimal("1200")),
        ),
    )
    result = run_agent2_pipeline(handoff)
    model = result.package.model_specification
    species_by_protein = {
        s.source_protein_id: s for s in model.full_network.species if s.source_protein_id
    }
    assert set(species_by_protein) == {"p1", "p2"}
    assert species_by_protein["p1"].species_id != species_by_protein["p2"].species_id
    laws = [law for law in model.kinetic_laws if law.reaction_id == "r1"]
    assert len(laws) == 2
    assert {law.rate_law_scope for law in laws} == {
        KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION
    }
    referenced = {sid for law in laws for sid in law.species_ids}
    assert species_by_protein["p1"].species_id in referenced
    assert species_by_protein["p2"].species_id in referenced


def test_reversible_mass_action_with_known_enzyme_stays_lumped_never_silently_decomposed():
    """No decomposition basis exists for mass-action rate constants today (task's own §7) --
    a reversible, catalyzed reaction with full enzyme identity/abundance still gets an
    explicit enzyme species (identity disclosure, task §2/§6), but its own kinetic-law
    expression is never silently multiplied by it."""
    handoff = _single_substrate_mm_handoff(reactions=(_curated_reaction(id="r1", reversible=True),))
    result = run_agent2_pipeline(handoff)
    model = result.package.model_specification
    enzyme_species = [s for s in model.full_network.species if s.source_protein_id == "p1"]
    assert len(enzyme_species) == 1
    (law,) = (law for law in model.kinetic_laws if law.reaction_id == "r1")
    if law.law_type is KineticLawType.MICHAELIS_MENTEN:
        assert law.rate_law_scope is KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION
    else:
        assert law.rate_law_scope is KineticLawRateScope.LUMPED_EFFECTIVE_RATE
        assert enzyme_species[0].species_id not in law.species_ids


def test_semantic_round_trip_through_canonical_downstream_handoff():
    result = run_agent2_pipeline(_single_substrate_mm_handoff())
    model = result.package.model_specification
    handoff = result.downstream_handoff

    (species,) = (s for s in model.full_network.species if s.source_protein_id == "p1")
    species_dict = next(
        s for s in handoff["species"] if s["species_id"] == species.species_id
    )
    assert species_dict["source_protein_id"] == "p1"
    assert species_dict["source_compound_id"] is None

    (law,) = (law for law in model.kinetic_laws if law.reaction_id == "r1")
    law_dict = next(lw for lw in handoff["kinetic_laws"] if lw["reaction_id"] == "r1")
    assert law_dict["rate_law_scope"] == law.rate_law_scope.value == "EXPLICIT_ENZYME_CONCENTRATION"


def test_antimony_symbol_provenance_traces_enzyme_species_back_to_protein_id():
    result = run_agent2_pipeline(_single_substrate_mm_handoff())
    model = result.package.model_specification
    (species,) = (s for s in model.full_network.species if s.source_protein_id == "p1")
    records = build_symbol_provenance_map(model)
    (record,) = (r for r in records if r.canonical_id == species.species_id)
    assert record.agent1_entity_id == "p1"
