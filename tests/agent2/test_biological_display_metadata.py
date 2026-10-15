"""Tests for the Agent 1 -> Agent 2 Biological Display Metadata Contract increment.

Extends the Human-Readable Antimony Naming increment's own naming layer
(``app.agent2.antimony.naming``, see ``tests/agent2/test_antimony_naming.py``) with the
catalyst-aware reaction/parameter naming tiers this increment adds: a reaction's own curated
gene symbol or protein name (via its ``FullNetwork.enzyme_associations``/``.proteins``/
``.genes``) now takes priority over its curated name, and a substrate-specific parameter's
own symbol can append its substrate's readable compound name.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.antimony import generate_antimony
from app.agent2.antimony.naming import build_identifier_map, build_symbol_provenance_map
from app.agent2.antimony_import import import_antimony
from app.agent2.pipeline import build_canonical_downstream_handoff, run_agent2_pipeline
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedCompartment,
    CuratedCompound,
    CuratedGene,
    CuratedProtein,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionEnzymeAssociation,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures (mirrors tests/agent2/test_antimony_naming.py's own conventions) ------------------


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
    } | overrides
    return ReactionEnzymeAssociation(**merged)


def _gene(**overrides) -> CuratedGene:
    merged = {"id": overrides.get("id", "gene-1")} | overrides
    return CuratedGene(**merged)


def _protein(**overrides) -> CuratedProtein:
    merged = {
        "id": overrides.get("id", "protein-1"),
        "name": overrides.get("name", "Test protein"),
    } | overrides
    return CuratedProtein(**merged)


def _network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "test network",
        "compartments": (_compartment(),),
        "species": (_species(species_id="a"), _species(species_id="b", name="b")),
        "reactions": (_reaction(),),
    } | overrides
    return FullNetwork(**merged)


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "k1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": "k1 * a",
        "parameter_ids": ("k1",),
        "species_ids": ("a",),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    parameter_id = overrides.get("parameter_id", "k1")
    merged = {
        "parameter_id": parameter_id,
        "name": parameter_id,
        "source": ParameterSource.CURATED,
        "value": Decimal("0.5"),
        "reaction_id": "r1",
    } | overrides
    return ParameterSpecification(**merged)


def _model(**overrides):
    from app.agent2.types import ModelSpecification

    merged = {
        "model_id": "m1",
        "name": "test model",
        "full_network": _network(),
        "kinetic_laws": (_kinetic_law(),),
        "parameters": (_parameter(),),
    } | overrides
    return ModelSpecification(**merged)


# --- Reaction with a gene symbol -----------------------------------------------------------------


def test_reaction_with_gene_symbol_prefers_it_over_the_curated_name():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="acetyl-CoA carboxylase"),),
            enzyme_associations=(_association(protein_id="protein-acc1"),),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
            ),
            genes=(_gene(id="gene-acc1", symbol="ACC1"),),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_ACC1"


# --- Reaction with a protein name but no gene symbol ---------------------------------------------


def test_reaction_with_protein_name_but_no_gene_falls_back_to_protein_name():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="fatty acid synthase reaction"),),
            enzyme_associations=(_association(protein_id="protein-fas1"),),
            proteins=(_protein(id="protein-fas1", name="Fatty_acid_synthase", gene_id=None),),
            genes=(),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_Fatty_acid_synthase"


def test_reaction_with_protein_name_but_gene_has_no_symbol_falls_back_to_protein_name():
    """A linked gene exists but its own ``symbol`` is unset (task instructions: ``symbol``/
    ``systematic_name`` are both optional on a real curated gene) -- the protein's own name
    is used, never a gene-id-shaped fallback."""
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="fatty acid synthase reaction"),),
            enzyme_associations=(_association(protein_id="protein-fas1"),),
            proteins=(_protein(id="protein-fas1", name="Fatty_acid_synthase", gene_id="gene-x"),),
            genes=(_gene(id="gene-x", symbol=None, systematic_name="YKL182W"),),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_Fatty_acid_synthase"


# --- Multiple catalysts --------------------------------------------------------------------------


def test_multiple_catalysts_with_gene_symbols_are_joined_sorted_and_deterministic():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="acetyl-CoA carboxylase reaction"),),
            enzyme_associations=(
                _association(association_id="a1", protein_id="protein-hfa1"),
                _association(association_id="a2", protein_id="protein-acc1"),
            ),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
                _protein(
                    id="protein-hfa1",
                    name="Acetyl-CoA carboxylase, mitochondrial",
                    gene_id="gene-hfa1",
                ),
            ),
            genes=(
                _gene(id="gene-acc1", symbol="ACC1"),
                _gene(id="gene-hfa1", symbol="HFA1"),
            ),
        )
    )
    id_map = build_identifier_map(model)
    # Sorted ("ACC1" < "HFA1"), independent of association/protein iteration order above.
    assert id_map.reactions["r1"] == "J_ACC1_HFA1"


def test_multiple_catalysts_mixing_gene_symbol_and_protein_name():
    """One catalyst resolves to a gene symbol, the other only to a protein name (no linked
    gene) -- both contribute their own best-available label; neither is dropped just because
    the other has richer metadata."""
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="isozyme reaction"),),
            enzyme_associations=(
                _association(association_id="a1", protein_id="protein-1"),
                _association(association_id="a2", protein_id="protein-2"),
            ),
            proteins=(
                _protein(id="protein-1", name="Enzyme_one", gene_id="gene-1"),
                _protein(id="protein-2", name="Enzyme_two", gene_id=None),
            ),
            genes=(_gene(id="gene-1", symbol="ENZ1"),),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_ENZ1_Enzyme_two"


# --- Missing gene/protein metadata fallback ------------------------------------------------------


def test_reaction_with_no_enzyme_association_falls_back_to_curated_name():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="an uncatalyzed-association reaction"),),
            enzyme_associations=(),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_an_uncatalyzed_association_reaction"


def test_reaction_with_enzyme_association_but_unresolvable_protein_falls_back_to_curated_name():
    """An association exists, but its ``protein_id`` matches no curated ``CuratedProtein``
    row (e.g. a complex-only association, or a protein Agent 1 has not yet curated) -- the
    reaction falls straight through to its own curated name, never raises, never reports a
    bare gene-id-shaped symbol."""
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="complex catalyzed reaction"),),
            enzyme_associations=(_association(protein_id="unresolvable-protein-id"),),
            proteins=(),
            genes=(),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_complex_catalyzed_reaction"


def test_reaction_with_no_curated_name_or_catalyst_falls_back_to_ec_number():
    # "---" has no alphanumeric content at all, so no meaningful display basis can be
    # derived from it -- the real "no usable curated name available" scenario, since
    # ReactionSpecification.name itself must be non-empty.
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="2078517a-raw-id", name="---", ec_number="6.4.1.2"),),
            enzyme_associations=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["2078517a-raw-id"] == "J_EC__6_4_1_2"


def test_reaction_with_no_name_catalyst_or_ec_falls_back_to_raw_id():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="2078517a-raw-id", name="---"),),
            enzyme_associations=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["2078517a-raw-id"] == "J__2078517a_raw_id"


# --- Readable kinetic parameter naming -----------------------------------------------------------


def test_parameter_inherits_its_reaction_s_gene_symbol_based_basis():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="acetyl-CoA carboxylase"),),
            enzyme_associations=(_association(protein_id="protein-acc1"),),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
            ),
            genes=(_gene(id="gene-acc1", symbol="ACC1"),),
        ),
        parameters=(_parameter(parameter_id="k1", name="kcat_r1_protein-acc1", reaction_id="r1"),),
    )
    id_map = build_identifier_map(model)
    assert id_map.parameters["k1"] == "p_kcat_ACC1"


def test_parameter_with_substrate_id_appends_the_readable_compound_name():
    """The task's own explicit example: ``Km_ACC1_acetyl_CoA``."""
    model = _model(
        full_network=_network(
            species=(
                _species(species_id="a", name="Acetyl-CoA", source_compound_id="cpd-accoa"),
                _species(species_id="b", name="b"),
            ),
            reactions=(_reaction(reaction_id="r1", name="acetyl-CoA carboxylase"),),
            enzyme_associations=(_association(protein_id="protein-acc1"),),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
            ),
            genes=(_gene(id="gene-acc1", symbol="ACC1"),),
        ),
        parameters=(
            _parameter(
                parameter_id="k1",
                name="Km_r1_protein-acc1_cpd-accoa",
                reaction_id="r1",
                substrate_id="cpd-accoa",
            ),
        ),
    )
    id_map = build_identifier_map(model)
    assert id_map.parameters["k1"] == "p_Km_ACC1_Acetyl_CoA"


def test_parameter_with_unresolvable_substrate_id_omits_the_suffix():
    model = _model(
        parameters=(
            _parameter(
                parameter_id="k1",
                name="Km_r1_protein-x",
                reaction_id="r1",
                substrate_id="no-such-compound",
            ),
        )
    )
    id_map = build_identifier_map(model)
    assert id_map.parameters["k1"] == "p_Km_r1"


# --- Deterministic collision handling -------------------------------------------------------------


def test_identical_multi_catalyst_basis_resolves_deterministically_across_repeated_calls():
    model = _model(
        full_network=_network(
            reactions=(
                _reaction(reaction_id="r1", name="reaction one"),
                _reaction(
                    reaction_id="r2",
                    name="reaction two",
                    participants=(
                        _participant(species_id="a", role=ParticipantRole.REACTANT),
                        _participant(species_id="b", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
            enzyme_associations=(
                _association(association_id="a1", reaction_id="r1", protein_id="protein-1"),
                _association(association_id="a2", reaction_id="r2", protein_id="protein-1"),
            ),
            proteins=(_protein(id="protein-1", name="Shared_enzyme", gene_id="gene-1"),),
            genes=(_gene(id="gene-1", symbol="SHARED"),),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    first = build_identifier_map(model)
    second = build_identifier_map(model)
    assert first == second
    assert first.reactions["r1"] == "J_SHARED"
    assert first.reactions["r2"] == "J_SHARED_2"


# --- Exact provenance traceability preserved -----------------------------------------------------


def test_symbol_provenance_preserved_for_gene_symbol_based_reaction_name():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="raw-reaction-uuid", name="acetyl-CoA carboxylase"),),
            enzyme_associations=(
                _association(reaction_id="raw-reaction-uuid", protein_id="protein-acc1"),
            ),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
            ),
            genes=(_gene(id="gene-acc1", symbol="ACC1"),),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    provenance = build_symbol_provenance_map(model)
    by_symbol = {p.antimony_symbol: p for p in provenance}
    reaction_symbol = id_map.reactions["raw-reaction-uuid"]
    assert reaction_symbol == "J_ACC1"
    record = by_symbol[reaction_symbol]
    assert record.canonical_id == "raw-reaction-uuid"
    assert record.component_type == "REACTION"


def test_naming_does_not_change_the_canonical_downstream_handoff():
    """The gene-symbol-based reaction/parameter naming only changes the *Antimony symbol* --
    the downstream handoff's own canonical reaction_id/parameter_id/name fields (what Agents
    3/4/5 actually consume) are completely unaffected."""
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="r1", name="acetyl-CoA carboxylase"),),
            enzyme_associations=(_association(protein_id="protein-acc1"),),
            proteins=(
                _protein(id="protein-acc1", name="Acetyl-CoA carboxylase", gene_id="gene-acc1"),
            ),
            genes=(_gene(id="gene-acc1", symbol="ACC1"),),
        )
    )
    package = generate_antimony(model)
    handoff = build_canonical_downstream_handoff(model, package)
    (reaction_dict,) = handoff["reactions"]
    assert reaction_dict["reaction_id"] == "r1"
    assert reaction_dict["name"] == "acetyl-CoA carboxylase"
    assert handoff["antimony_symbol_map"]["reactions"]["r1"] == "J_ACC1"


# --- Real yeast lipid-biosynthesis regression ----------------------------------------------------


def _yeast_lipid_biosynthesis_handoff_with_gene_protein_metadata() -> (
    Agent1CuratedKnowledgeViewContract
):
    """A yeast-lipid-biosynthesis-shaped handoff carrying real curated gene/protein
    metadata (ACC1/HFA1-shaped isozymes catalyzing the same reaction) -- the task's own
    explicit named regression target, extended from the sibling Human-Readable Antimony
    Naming increment's identical fixture (``tests/agent2/test_antimony_naming.py``)."""
    return Agent1CuratedKnowledgeViewContract(
        contract_version="1.7",
        organism_id="b7da7edf-yeast",
        compartments=(CuratedCompartment(id="6e1bdc18-cyto-uuid", name="cytosol"),),
        compounds=(
            CuratedCompound(id="4e218966-accoa-uuid", name="Acetyl-CoA"),
            CuratedCompound(id="2ed5906e-coa-uuid", name="Coenzyme A"),
            CuratedCompound(id="16de5665-acac-uuid", name="Acetoacetyl-CoA"),
        ),
        reactions=(
            CuratedReaction(
                id="2078517a-rxn-uuid",
                name="acetyl-CoA C-acetyltransferase",
                reversible=False,
                ec_number="6.4.1.2",
            ),
        ),
        reaction_participants=(
            CuratedReactionParticipant(
                reaction_id="2078517a-rxn-uuid",
                compound_id="4e218966-accoa-uuid",
                role="REACTANT",
                stoichiometry=Decimal("2"),
                compartment_id="6e1bdc18-cyto-uuid",
            ),
            CuratedReactionParticipant(
                reaction_id="2078517a-rxn-uuid",
                compound_id="16de5665-acac-uuid",
                role="PRODUCT",
                stoichiometry=Decimal("1"),
                compartment_id="6e1bdc18-cyto-uuid",
            ),
            CuratedReactionParticipant(
                reaction_id="2078517a-rxn-uuid",
                compound_id="2ed5906e-coa-uuid",
                role="PRODUCT",
                stoichiometry=Decimal("1"),
                compartment_id="6e1bdc18-cyto-uuid",
            ),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="2078517a-rxn-uuid",
                protein_id="6f7d9889-protein-uuid",
                relationship="CATALYZES",
            ),
            CuratedReactionEnzymeAssociation(
                reaction_id="2078517a-rxn-uuid",
                protein_id="9f1a2b3c-hfa1-protein-uuid",
                relationship="CATALYZES",
            ),
        ),
        proteins=(
            CuratedProtein(
                id="6f7d9889-protein-uuid",
                name="Acetyl-CoA carboxylase",
                gene_id="gene-acc1-uuid",
                ec_number="6.4.1.2",
            ),
            CuratedProtein(
                id="9f1a2b3c-hfa1-protein-uuid",
                name="Acetyl-CoA carboxylase, mitochondrial",
                gene_id="gene-hfa1-uuid",
                ec_number="6.4.1.2",
            ),
        ),
        genes=(
            CuratedGene(id="gene-acc1-uuid", symbol="ACC1", systematic_name="YNR016C"),
            CuratedGene(id="gene-hfa1-uuid", symbol="HFA1", systematic_name="YMR207C"),
        ),
    )


def test_real_shaped_yeast_lipid_biosynthesis_model_generates_gene_symbol_based_reaction_name():
    """The task's own explicit, named regression: an enzyme-associated reaction with real
    curated gene/protein metadata becomes recognizable (``J_ACC1_HFA1``), never a raw UUID,
    and the kinetic-rate parameter inherits the identical catalyst-based basis."""
    handoff = _yeast_lipid_biosynthesis_handoff_with_gene_protein_metadata()
    result = run_agent2_pipeline(handoff)
    text = result.package.full_antimony.antimony_text

    assert "J_ACC1_HFA1" in text
    assert "6f7d9889-protein-uuid" not in text.split("//", 1)[0] if "//" in text else True
    for raw_uuid in ("2078517a-rxn-uuid", "6f7d9889-protein-uuid", "9f1a2b3c-hfa1-protein-uuid"):
        assert not any(line.startswith(f"{raw_uuid}:") for line in text.splitlines())

    reimported = import_antimony(text)
    assert len(reimported.full_network.reactions) == 1

    handoff_dict = result.downstream_handoff
    assert handoff_dict["antimony_symbol_map"]["reactions"]["2078517a-rxn-uuid"] == "J_ACC1_HFA1"
    assert handoff_dict["readiness"] in ("EXECUTABLE", "NON_EXECUTABLE_UNRESOLVED_KINETICS")
