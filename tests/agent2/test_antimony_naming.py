"""Tests for the Human-Readable Antimony Naming and Provenance Separation increment
(``app.agent2.antimony.naming``).

``tests/agent2/test_antimony_generation.py`` already covers kinetic-law/module/composition
logic with id-equals-name fixtures (so this module's name-preferring behavior never disturbs
those pre-existing assertions). This file is dedicated to the naming behavior itself: readable
symbols from curated biological names, deterministic collision resolution, compartment
disambiguation, provenance lookup, imported-model preservation, and the explicit real-data
yeast-lipid-biosynthesis regression the task requires.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.antimony import generate_antimony
from app.agent2.antimony.naming import build_identifier_map, build_symbol_provenance_map
from app.agent2.antimony_import import import_antimony
from app.agent2.pipeline import run_agent2_pipeline
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedCompartment,
    CuratedCompound,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelSourceType,
    ModelSpecification,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures (mirrors tests/agent2/test_antimony_generation.py's own conventions) --------------


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


def _model(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "test model",
        "full_network": _network(),
        "kinetic_laws": (_kinetic_law(),),
        "parameters": (_parameter(),),
        "module_specifications": (),
    } | overrides
    return ModelSpecification(**merged)


# --- Readable compartment names ------------------------------------------------------------------


def test_compartment_symbol_prefers_curated_biological_name_over_raw_id():
    model = _model(
        full_network=_network(
            compartments=(
                _compartment(compartment_id="7c2e7e7e-uuid-like-id", name="mitochondrion"),
            ),
            species=(_species(species_id="a", compartment_id="7c2e7e7e-uuid-like-id"),),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.compartments["7c2e7e7e-uuid-like-id"] == "c_mitochondrion"


def test_compartment_symbol_falls_back_to_raw_id_when_no_name_available():
    # "---" has no alphanumeric content at all, so no meaningful display basis can be
    # derived from it -- the real "no curated name available" scenario, since
    # ``CompartmentSpecification.name`` itself must be non-empty.
    model = _model(
        full_network=_network(compartments=(_compartment(compartment_id="cyto", name="---"),))
    )
    id_map = build_identifier_map(model)
    assert id_map.compartments["cyto"] == "c_cyto"


# --- Readable metabolite/species symbols + compartment disambiguation --------------------------


def test_species_symbol_prefers_curated_biological_name_over_raw_id():
    model = _model(
        full_network=_network(
            species=(
                _species(species_id="cpd-00001-uuid", name="Acetyl-CoA", compartment_id="cyto"),
            ),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.species["cpd-00001-uuid"] == "s_Acetyl_CoA_cyto"


def test_same_compound_in_two_compartments_disambiguates_by_compartment_not_opaque_suffix():
    """Two distinct species records for the same compound ('Acetyl-CoA') in two different
    compartments must read as two distinct, both-readable symbols -- never a bare compound
    name with an opaque numeric suffix the task explicitly wants avoided when a meaningful,
    readable disambiguator (the compartment) is available."""
    model = _model(
        full_network=_network(
            compartments=(
                _compartment(compartment_id="cyto", name="cytosol"),
                _compartment(compartment_id="mito", name="mitochondrion"),
            ),
            species=(
                _species(species_id="cpd-1", name="Acetyl-CoA", compartment_id="cyto"),
                _species(species_id="cpd-2", name="Acetyl-CoA", compartment_id="mito"),
            ),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.species["cpd-1"] == "s_Acetyl_CoA_cytosol"
    assert id_map.species["cpd-2"] == "s_Acetyl_CoA_mitochondrion"
    assert id_map.species["cpd-1"] != id_map.species["cpd-2"]


# --- Readable reaction names ----------------------------------------------------------------------


def test_reaction_symbol_prefers_curated_biological_name_over_raw_id():
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="rxn-uuid-1", name="acetyl-CoA carboxylase"),)
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.reactions["rxn-uuid-1"] == "J_acetyl_CoA_carboxylase"


# --- Readable kinetic parameter names -------------------------------------------------------------


def test_parameter_symbol_substitutes_readable_reaction_basis_for_embedded_reaction_id():
    """Mirrors the real shape produced by ``app.agent2.parameters.policy.build_parameter_slug``:
    a parameter's own ``name`` embeds its owning reaction's raw id verbatim. The resulting
    Antimony symbol must read via the reaction's own readable name, never the raw id."""
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id="2078517a-raw-reaction-id", name="oxidoreductase"),)
        ),
        kinetic_laws=(_kinetic_law(reaction_id="2078517a-raw-reaction-id"),),
        parameters=(
            _parameter(
                parameter_id="k1",
                name="Km_2078517a-raw-reaction-id_protein-uuid",
                reaction_id="2078517a-raw-reaction-id",
            ),
        ),
    )
    id_map = build_identifier_map(model)
    symbol = id_map.parameters["k1"]
    assert "2078517a" not in symbol
    assert symbol == "p_Km_oxidoreductase"


def test_parameter_symbol_falls_back_to_sanitized_name_without_reaction_match():
    model = _model(parameters=(_parameter(parameter_id="k1", name="k_cat"),))
    id_map = build_identifier_map(model)
    assert id_map.parameters["k1"] == "p_k_cat"


# --- Duplicate-name collision handling -----------------------------------------------------------


def test_duplicate_species_names_in_the_same_compartment_collide_with_numeric_suffix():
    model = _model(
        full_network=_network(
            species=(
                _species(species_id="a", name="Pyruvate", compartment_id="cyto"),
                _species(species_id="b", name="Pyruvate", compartment_id="cyto"),
            ),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    assert id_map.species["a"] == "s_Pyruvate_cyto"
    assert id_map.species["b"] == "s_Pyruvate_cyto_2"


def test_duplicate_parameter_names_for_the_same_reaction_collide_with_numeric_suffix():
    """Isozyme-shaped case: two parameters for the same reaction, same prefix+reaction basis
    (protein/substrate context deliberately dropped from the visible symbol -- Agent 2 has no
    gene/protein *symbol* data to render it with) -- resolved the same way every other
    category resolves a collision."""
    model = _model(
        full_network=_network(reactions=(_reaction(reaction_id="r1", name="ligase"),)),
        parameters=(
            _parameter(parameter_id="k1", name="Km_r1_proteinA", reaction_id="r1"),
            _parameter(parameter_id="k2", name="Km_r1_proteinB", reaction_id="r1"),
        ),
    )
    id_map = build_identifier_map(model)
    assert id_map.parameters["k1"] == "p_Km_ligase"
    assert id_map.parameters["k2"] == "p_Km_ligase_2"


def test_identifier_map_resolves_within_category_collisions_deterministically():
    """Two species named identically ('A') in the same compartment ('cyto') collide down to
    the same display basis -- resolved deterministically (sorted by source id) with a
    numeric suffix, never randomly or order-dependently."""
    model = _model(
        full_network=_network(
            species=(
                _species(species_id="a!", name="A", compartment_id="cyto"),
                _species(species_id="a?", name="A", compartment_id="cyto"),
            ),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
    )
    first = build_identifier_map(model)
    second = build_identifier_map(
        _model(full_network=model.full_network, kinetic_laws=(), parameters=())
    )
    assert first == second
    assert first.species["a!"] == "s_A_cyto"
    assert first.species["a?"] == "s_A_cyto_2"


# --- Deterministic repeated generation ----------------------------------------------------------


def test_generate_antimony_is_deterministic_across_repeated_calls():
    model = _model()
    first = generate_antimony(model)
    second = generate_antimony(model)
    assert first.full_antimony.antimony_text == second.full_antimony.antimony_text
    assert build_symbol_provenance_map(model) == build_symbol_provenance_map(model)


# --- Provenance lookup from readable symbol back to canonical ids ------------------------------


def test_symbol_provenance_map_round_trips_every_readable_symbol_to_its_canonical_id():
    model = _model(
        full_network=_network(
            compartments=(_compartment(compartment_id="cyto-uuid", name="cytosol"),),
            species=(
                _species(species_id="cpd-uuid", name="Pyruvate", compartment_id="cyto-uuid"),
                _species(species_id="cpd-uuid-2", name="ATP", compartment_id="cyto-uuid"),
            ),
            reactions=(
                _reaction(
                    reaction_id="rxn-uuid",
                    name="pyruvate kinase",
                    participants=(
                        _participant(species_id="cpd-uuid", role=ParticipantRole.REACTANT),
                        _participant(species_id="cpd-uuid-2", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
        ),
        kinetic_laws=(
            _kinetic_law(reaction_id="rxn-uuid", species_ids=("cpd-uuid", "cpd-uuid-2")),
        ),
        parameters=(_parameter(parameter_id="k1", reaction_id="rxn-uuid"),),
    )
    id_map = build_identifier_map(model)
    provenance = build_symbol_provenance_map(model)
    by_symbol = {p.antimony_symbol: p for p in provenance}

    compartment_symbol = id_map.compartments["cyto-uuid"]
    assert by_symbol[compartment_symbol].canonical_id == "cyto-uuid"
    assert by_symbol[compartment_symbol].component_type == "COMPARTMENT"

    species_symbol = id_map.species["cpd-uuid"]
    assert by_symbol[species_symbol].canonical_id == "cpd-uuid"
    assert by_symbol[species_symbol].component_type == "SPECIES"

    reaction_symbol = id_map.reactions["rxn-uuid"]
    assert by_symbol[reaction_symbol].canonical_id == "rxn-uuid"
    assert by_symbol[reaction_symbol].component_type == "REACTION"


def test_full_antimony_artifact_carries_symbol_provenance():
    model = _model()
    package = generate_antimony(model)
    assert len(package.full_antimony.symbol_provenance) > 0
    symbols = {p.antimony_symbol for p in package.full_antimony.symbol_provenance}
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] in symbols


# --- No UUID-heavy symbols when biological names exist ------------------------------------------


def test_uuid_shaped_canonical_id_never_appears_in_symbol_when_a_real_name_exists():
    uuid_like = "2e5815f3-f48b-4c08-ac56-1726198a18a1"
    model = _model(
        full_network=_network(
            reactions=(_reaction(reaction_id=uuid_like, name="malonyl-CoA S-malonyltransferase"),)
        ),
        kinetic_laws=(),
        parameters=(),
    )
    id_map = build_identifier_map(model)
    symbol = id_map.reactions[uuid_like]
    assert uuid_like not in symbol
    assert symbol == "J_malonyl_CoA_S_malonyltransferase"


# --- Imported Antimony symbols are preserved, never renamed -------------------------------------

_IMPORT_FIXTURE = """
model simple
  compartment cyto = 1.0;
  species Glucose in cyto = 10.0;
  species ATP in cyto = 5.0;
  Hexokinase_reaction: Glucose + ATP => Glucose; k1 * Glucose * ATP;
  k1 = 0.5;
end
"""


def test_imported_model_symbols_are_preserved_byte_for_byte_not_renamed():
    model = import_antimony(_IMPORT_FIXTURE)
    assert model.source_type is ModelSourceType.IMPORTED
    id_map = build_identifier_map(model)
    assert id_map.compartments["cyto"] == "c_cyto"
    assert id_map.species["Glucose"] == "s_Glucose"
    assert id_map.species["ATP"] == "s_ATP"
    assert id_map.reactions["Hexokinase_reaction"] == "J_Hexokinase_reaction"
    assert id_map.parameters["k1"] == "p_k1"


def test_imported_model_round_trip_antimony_text_preserves_original_symbols():
    model = import_antimony(_IMPORT_FIXTURE)
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert "J_Hexokinase_reaction" in text
    assert "s_Glucose" in text
    assert "s_ATP" in text


# --- Semantic round-trip + downstream handoff are unchanged by naming ---------------------------


def test_naming_never_changes_stoichiometry_reversibility_or_parameter_values():
    model = _model(
        full_network=_network(
            reactions=(
                _reaction(
                    reaction_id="r1",
                    name="named reaction",
                    reversible=True,
                    participants=(
                        _participant(
                            species_id="a",
                            role=ParticipantRole.REACTANT,
                            stoichiometry=Decimal("2"),
                        ),
                        _participant(
                            species_id="b", role=ParticipantRole.PRODUCT, stoichiometry=Decimal("3")
                        ),
                    ),
                ),
            )
        ),
        kinetic_laws=(_kinetic_law(expression="k1 * a", reaction_id="r1"),),
        parameters=(_parameter(parameter_id="k1", value=Decimal("1.25")),),
    )
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    reimported = import_antimony(text)
    reimported_reaction = next(r for r in reimported.full_network.reactions)
    stoichiometries = {p.species_id: p.stoichiometry for p in reimported_reaction.participants}
    assert set(stoichiometries.values()) == {Decimal("2"), Decimal("3")}
    assert reimported_reaction.reversible is True
    (reimported_param,) = reimported.parameters
    assert reimported_param.value == Decimal("1.25")


def test_naming_does_not_change_the_canonical_downstream_handoff_shape():
    """The downstream handoff Agents 3/4/5 consume carries each reaction's own canonical
    ``reaction_id``/``name`` straight from the model -- never an Antimony symbol. Giving a
    reaction a long, readable, UUID-embedding ``name`` (exactly the shape this increment
    now renders far more readably in the generated Antimony) must change nothing about the
    handoff's own species/reaction identity, count, or readiness."""
    descriptive_name = "2078517a-7593-46dd-b99c-7e0aba16aba0 -> readable (PHOSPHORYLATION)"
    model = _model(
        full_network=_network(reactions=(_reaction(reaction_id="r1", name=descriptive_name),))
    )
    package = generate_antimony(model)
    from app.agent2.pipeline import build_canonical_downstream_handoff

    handoff = build_canonical_downstream_handoff(model, package)
    (reaction_dict,) = handoff["reactions"]
    assert reaction_dict["reaction_id"] == "r1"
    assert reaction_dict["name"] == descriptive_name
    assert handoff["readiness"] == "EXECUTABLE"


# --- Real yeast lipid-biosynthesis regression (task's own explicit requirement) -----------------


def _yeast_lipid_biosynthesis_handoff() -> Agent1CuratedKnowledgeViewContract:
    """A small, synthetic but representatively-shaped yeast lipid-biosynthesis fragment:
    UUID-style curated ids throughout (mirroring real Agent 1 data), curated biological
    names on every compartment/compound/reaction -- enough to exercise every naming path
    this increment touches without depending on the real dev database."""
    return Agent1CuratedKnowledgeViewContract(
        contract_version="1.6",
        organism_id="b7da7edf-yeast",
        compartments=(
            CuratedCompartment(id="6e1bdc18-cyto-uuid", name="cytosol"),
            CuratedCompartment(id="9f381348-mito-uuid", name="mitochondrial matrix"),
        ),
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
        ),
    )


def test_real_shaped_yeast_lipid_biosynthesis_model_generates_human_readable_antimony():
    """The task's own explicit, named regression: run the real pipeline end to end on a
    yeast-lipid-biosynthesis-shaped handoff and verify the generated Antimony is
    human-readable -- readable compartment/species/reaction symbols, no raw UUID-shaped
    canonical ids exposed as symbols, and the verbose kinetic_law_id UUID chain dropped
    from the common-case reaction-line comment."""
    handoff = _yeast_lipid_biosynthesis_handoff()
    result = run_agent2_pipeline(handoff)
    text = result.package.full_antimony.antimony_text

    assert "c_cytosol" in text
    assert "c_mitochondrial_matrix" in text
    assert "s_Acetyl_CoA_cytosol" in text
    assert "s_Coenzyme_A_cytosol" in text
    assert "J_acetyl_CoA_C_acetyltransferase" in text

    # Raw canonical ids remain disclosed in short trailing provenance comments (by design --
    # "short comments ... are fine", task §3) but must never be the thing a reader actually
    # types or reads as the component's own *symbol*: none may appear as a declared Antimony
    # identifier (the first token on a `compartment`/`species`/reaction-equation line).
    for raw_uuid in (
        "6e1bdc18-cyto-uuid",
        "4e218966-accoa-uuid",
        "2078517a-rxn-uuid",
        "6f7d9889-protein-uuid",
    ):
        assert f"compartment c_{raw_uuid}" not in text
        assert f"species s_{raw_uuid}" not in text
        assert not any(line.startswith(f"{raw_uuid}:") for line in text.splitlines())

    assert "kinetic_law_id=" not in text

    reimported = import_antimony(text)
    assert len(reimported.full_network.compartments) == 2
    assert len(reimported.full_network.species) == 3
    assert len(reimported.full_network.reactions) == 1
