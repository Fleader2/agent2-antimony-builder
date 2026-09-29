"""Tests for Antimony Generation (Increment 9): ``app.agent2.antimony``.

Most tests build a ``ModelSpecification`` directly (mirroring
``tests/agent2/test_output_contracts.py``'s own convention) so each
kinetic-law/parameter/catalytic-context/module scenario can be pinned
exactly, since ``generate_antimony`` must reproduce the *given*
``expression``/``value`` facts verbatim, never re-derive them. A handful
of tests instead run the real upstream pipeline (mirroring
``tests/agent2/test_model_specification.py``) to confirm end-to-end
behavior on a genuinely assembled model.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.agent2.antimony import UnsupportedAntimonySerializationError, generate_antimony
from app.agent2.antimony.naming import build_identifier_map, sanitize_model_name
from app.agent2.types import (
    AntimonyArtifactReadiness,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedEnzymeState,
    EnzymeStatePool,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelSpecification,
    ModuleBoundaryInterface,
    ModuleInterfaceRole,
    ModuleSpecification,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

_ANTIMONY_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- Fixtures ----------------------------------------------------------------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "cyto",
        "name": "cytosol",
        "source_scope": CompartmentSourceScope.AGENT1_CURATED,
        "source_entity_id": "agent1-c1",
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "a", "name": "A", "compartment_id": "cyto"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "a",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "reaction 1",
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
        "species": (_species(species_id="a", name="A"), _species(species_id="b", name="B")),
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
    merged = {
        "parameter_id": "k1",
        "name": "k1",
        "source": ParameterSource.CURATED,
        "value": Decimal("0.5"),
        "reaction_id": "r1",
    } | overrides
    return ParameterSpecification(**merged)


def _module(**overrides) -> ModuleSpecification:
    merged = {
        "module_id": "mod-1",
        "name": "test module",
        "reaction_ids": ("r1",),
        "species_ids": ("a", "b"),
        "parameter_ids": ("k1",),
        "compartment_ids": ("cyto",),
        "source_boundary_ids": (),
    } | overrides
    return ModuleSpecification(**merged)


def _model(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "test model",
        "full_network": _network(),
        "kinetic_laws": (_kinetic_law(),),
        "parameters": (_parameter(),),
        "module_specifications": (_module(),),
    } | overrides
    return ModelSpecification(**merged)


# --- Public API type-safety --------------------------------------------------------------------


def test_generate_antimony_rejects_non_model_specification():
    with pytest.raises(UnsupportedAntimonySerializationError):
        generate_antimony("not a model")  # type: ignore[arg-type]


# --- Identifier mapping (Step 46) ---------------------------------------------------------------


def test_identifier_map_is_stable_across_repeated_calls():
    model = _model()
    first = build_identifier_map(model)
    second = build_identifier_map(model)
    assert first == second


def test_identifier_map_ids_are_valid_antimony_identifiers_for_hostile_input():
    model = _model(
        full_network=_network(
            compartments=(_compartment(compartment_id="cyto (external), v2!"),),
            species=(
                _species(
                    species_id="6-phosphofructokinase", compartment_id="cyto (external), v2!"
                ),
                _species(
                    species_id="glucose 6-phosphate/ätp", compartment_id="cyto (external), v2!"
                ),
            ),
            reactions=(
                _reaction(
                    participants=(
                        _participant(
                            species_id="6-phosphofructokinase", role=ParticipantRole.REACTANT
                        ),
                        _participant(
                            species_id="glucose 6-phosphate/ätp", role=ParticipantRole.PRODUCT
                        ),
                    )
                ),
            ),
        ),
        kinetic_laws=(_kinetic_law(species_ids=("6-phosphofructokinase",)),),
        module_specifications=(),
    )
    id_map = build_identifier_map(model)
    for antimony_id in (
        *id_map.compartments.values(),
        *id_map.species.values(),
        *id_map.parameters.values(),
        *id_map.reactions.values(),
    ):
        assert _ANTIMONY_IDENTIFIER.match(antimony_id), antimony_id


def test_identifier_map_resolves_within_category_collisions_deterministically():
    model = _model(
        full_network=_network(
            species=(
                _species(species_id="a!", name="A"),
                _species(species_id="a?", name="A"),
                _species(species_id="b", name="B"),
            ),
            reactions=(),
        ),
        kinetic_laws=(),
        parameters=(),
        module_specifications=(),
    )
    first = build_identifier_map(model)
    second = build_identifier_map(model)
    assert first.species == second.species
    assert len(set(first.species.values())) == len(first.species)
    # deterministic: "a!" sorts before "a?", so "a!" keeps the bare candidate
    assert first.species["a!"] == "s_a_"
    assert first.species["a?"] == "s_a__2"


def test_identifier_map_never_uses_hash_or_uuid_style_ids():
    model = _model()
    id_map = build_identifier_map(model)
    for antimony_id in id_map.species.values():
        assert antimony_id == "s_a" or antimony_id == "s_b"


def test_sanitize_model_name_handles_leading_digit_and_punctuation():
    name = sanitize_model_name("123::model!!")
    assert _ANTIMONY_IDENTIFIER.match(name)


def test_identifier_map_reused_identically_between_full_model_and_module_view():
    """Step 32: the same Agent 2 entity gets the same Antimony identifier everywhere."""
    model = _model()
    package = generate_antimony(model)
    id_map = build_identifier_map(model)
    assert f"reaction_id=r1" in package.full_antimony.antimony_text  # noqa: F541
    assert id_map.species["a"] in package.full_antimony.antimony_text
    assert id_map.species["a"] in package.module_artifacts[0].antimony_view


# --- Full model serialization (Step 47) ------------------------------------------------------


def test_empty_model_serializes_to_a_minimal_legal_model():
    model = ModelSpecification(
        model_id="empty",
        name="empty model",
        full_network=FullNetwork(network_id="n0", name="empty network"),
    )
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert text.startswith("model ")
    assert text.rstrip("\n").endswith("end")
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert package.full_antimony.unresolved_kinetic_law_ids == ()


def test_one_compartment_one_species_one_reaction_serializes():
    model = _model()
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert "compartment c_cyto" in text
    assert "species s_a in c_cyto" in text
    assert "species s_b in c_cyto" in text
    assert "J_r1: s_a -> s_b; k1 * s_a;" in text.replace("p_k1", "k1")


def test_multiple_reactions_all_serialized():
    model = _model(
        full_network=_network(
            species=(_species(species_id="a"), _species(species_id="b"), _species(species_id="c")),
            reactions=(
                _reaction(reaction_id="r1"),
                _reaction(
                    reaction_id="r2",
                    participants=(
                        _participant(species_id="b", role=ParticipantRole.REACTANT),
                        _participant(species_id="c", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
        ),
        kinetic_laws=(
            _kinetic_law(kinetic_law_id="k1", reaction_id="r1"),
            _kinetic_law(
                kinetic_law_id="k2", reaction_id="r2", parameter_ids=("k2",), species_ids=("b",),
                expression="k2 * b",
            ),
        ),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k2")),
        module_specifications=(),
    )
    text = generate_antimony(model).full_antimony.antimony_text
    assert "J_r1:" in text
    assert "J_r2:" in text


def test_reversible_reaction_disclosed_in_comment():
    model = _model(full_network=_network(reactions=(_reaction(reversible=True),)))
    text = generate_antimony(model).full_antimony.antimony_text
    assert "reversible=reversible" in text


def test_irreversible_reaction_disclosed_in_comment():
    model = _model(full_network=_network(reactions=(_reaction(reversible=False),)))
    text = generate_antimony(model).full_antimony.antimony_text
    assert "reversible=irreversible" in text


def test_unresolved_reversibility_no_longer_blocks_executable_status():
    """Agent 2 increment (Conservative Reversibility Default): motivated by Real Integration
    Pilot 2 Run 5 -- an otherwise fully-resolved law/reaction must not be blocked from
    EXECUTABLE status merely because Agent 1's own curated reversible is None; it is modeled
    as tentatively reversible instead, disclosed via the reaction's own comment."""
    model = _model(
        full_network=_network(reactions=(_reaction(reversible=None),)), module_specifications=()
    )
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert artifact.unresolved_kinetic_law_ids == ()
    assert artifact.unresolved_reaction_ids == ()
    assert "reversible=reversible(assumed)" in artifact.antimony_text


def test_reversible_reaction_with_unresolved_reverse_kinetics_remains_non_executable():
    """Scenario 6/11: structural reversibility (curated True *or* assumed from None) never
    forces numerical executability -- a REVERSIBLE_MASS_ACTION law with an unresolved ``kr``
    stays a PLACEHOLDER, and the reaction/law/model all remain NON_EXECUTABLE."""
    law = _kinetic_law(
        law_type=KineticLawType.REVERSIBLE_MASS_ACTION,
        expression="kf * a - kr * b",
        parameter_ids=("kf", "kr"),
        species_ids=("a", "b"),
    )
    model = _model(
        full_network=_network(reactions=(_reaction(reversible=None),)),
        kinetic_laws=(law,),
        parameters=(
            _parameter(parameter_id="kf", value=Decimal("0.5")),
            _parameter(parameter_id="kr", value=None, source=ParameterSource.PLACEHOLDER),
        ),
        module_specifications=(),
    )
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert law.kinetic_law_id in artifact.unresolved_kinetic_law_ids
    assert not any(
        line.strip().startswith("p_kr =") for line in artifact.antimony_text.splitlines()
    )


def test_stoichiometric_coefficients_preserved_verbatim():
    model = _model(
        full_network=_network(
            reactions=(
                _reaction(
                    participants=(
                        _participant(
                            species_id="a",
                            role=ParticipantRole.REACTANT,
                            stoichiometry=Decimal("2"),
                        ),
                        _participant(
                            species_id="b",
                            role=ParticipantRole.PRODUCT,
                            stoichiometry=Decimal("3"),
                        ),
                    )
                ),
            )
        )
    )
    text = generate_antimony(model).full_antimony.antimony_text
    assert "2 s_a -> 3 s_b" in text


def test_determinism_byte_identical_across_repeated_generation():
    model = _model()
    first = generate_antimony(model)
    second = generate_antimony(model)
    assert first.full_antimony.antimony_text == second.full_antimony.antimony_text
    assert first.module_artifacts[0].antimony_view == second.module_artifacts[0].antimony_view


# --- Kinetic-law serialization (Step 48) -------------------------------------------------------


def _resolved_model(
    law: KineticLawSpecification, parameters: tuple[ParameterSpecification, ...]
) -> ModelSpecification:
    return _model(kinetic_laws=(law,), parameters=parameters, module_specifications=())


def test_mass_action_expression_rendered_with_antimony_ids():
    law = _kinetic_law(
        law_type=KineticLawType.MASS_ACTION,
        expression="k1 * a",
        parameter_ids=("k1",),
        species_ids=("a",),
    )
    model = _resolved_model(law, (_parameter(parameter_id="k1"),))
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert "s_a -> s_b; p_k1 * s_a;" in artifact.antimony_text


def test_reversible_mass_action_expression_rendered():
    law = _kinetic_law(
        law_type=KineticLawType.REVERSIBLE_MASS_ACTION,
        expression="kf * a - kr * b",
        parameter_ids=("kf", "kr"),
        species_ids=("a", "b"),
    )
    model = _resolved_model(
        law, (_parameter(parameter_id="kf"), _parameter(parameter_id="kr"))
    )
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert "p_kf * s_a - p_kr * s_b" in artifact.antimony_text


def test_michaelis_menten_single_substrate_expression_rendered():
    law = _kinetic_law(
        law_type=KineticLawType.MICHAELIS_MENTEN,
        expression="kcat * a / (km + a)",
        parameter_ids=("kcat", "km"),
        species_ids=("a",),
    )
    model = _resolved_model(law, (_parameter(parameter_id="kcat"), _parameter(parameter_id="km")))
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert "p_kcat * s_a / (p_km + s_a)" in artifact.antimony_text


def test_hill_expression_rendered():
    law = _kinetic_law(
        law_type=KineticLawType.HILL,
        expression="vmax * a^n / (km^n + a^n)",
        parameter_ids=("vmax", "km", "n"),
        species_ids=("a",),
    )
    model = _resolved_model(
        law,
        (
            _parameter(parameter_id="vmax"),
            _parameter(parameter_id="km"),
            _parameter(parameter_id="n"),
        ),
    )
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert "p_vmax * s_a^p_n / (p_km^p_n + s_a^p_n)" in artifact.antimony_text


def test_custom_law_never_serialized_as_executable():
    """Step 20: CUSTOM's curated text has no structured symbol mapping -- never guessed at."""
    law = _kinetic_law(
        law_type=KineticLawType.CUSTOM,
        expression="V_max * [S] / (K_m + [S])",
        parameter_ids=(),
        species_ids=("a", "b"),
    )
    model = _resolved_model(law, ())
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert "CUSTOM_LAW_SYMBOL_MAPPING_UNAVAILABLE" in artifact.antimony_text
    assert "V_max * [S]" not in artifact.antimony_text


def test_tentative_mass_action_serialized_normally_and_marked_heuristic():
    """Step 19: tentative mass action is not blocked merely because it is tentative."""
    law = _kinetic_law(
        law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.HEURISTIC,
        expression="k1 * a",
        parameter_ids=("k1",),
        species_ids=("a",),
    )
    model = _resolved_model(law, (_parameter(parameter_id="k1"),))
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert "p_k1 * s_a;" in artifact.antimony_text


def test_unassigned_law_never_serialized_as_executable():
    law = _kinetic_law(
        law_type=KineticLawType.UNASSIGNED,
        assignment_source=KineticLawAssignmentSource.UNASSIGNED,
        expression=None,
        parameter_ids=(),
        species_ids=(),
    )
    model = _resolved_model(law, ())
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert "UNASSIGNED_KINETIC_LAW" in artifact.antimony_text


def test_assigned_law_with_expression_none_never_fabricates_algebra():
    law = _kinetic_law(
        law_type=KineticLawType.MICHAELIS_MENTEN,
        expression=None,
        parameter_ids=("kcat", "km_a", "km_b"),
        species_ids=("a", "b"),
    )
    model = _resolved_model(
        law,
        (
            _parameter(parameter_id="kcat"),
            _parameter(parameter_id="km_a"),
            _parameter(parameter_id="km_b"),
        ),
    )
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert "UNRESOLVED_KINETIC_EXPRESSION" in artifact.antimony_text
    # No fabricated equation of any kind appears.
    assert "kcat" not in artifact.antimony_text.split("//")[0]


def test_no_unresolved_law_ever_emitted_with_a_trailing_rate_expression():
    """Structural guarantee: an unresolved reaction line must never contain a second
    semicolon-terminated rate clause -- only the bare stoichiometric equation plus a comment."""
    law = _kinetic_law(
        law_type=KineticLawType.UNASSIGNED, expression=None, parameter_ids=(), species_ids=()
    )
    model = _resolved_model(law, ())
    artifact = generate_antimony(model).full_antimony
    reaction_line = next(
        line for line in artifact.antimony_text.splitlines() if line.startswith("J_r1:")
    )
    equation_and_rest = reaction_line.split("//", 1)[0]
    assert equation_and_rest.count(";") == 1


# --- Multi-substrate Michaelis-Menten (Step 49) -------------------------------------------------


def test_multi_substrate_michaelis_menten_unresolved_never_invents_algebra():
    law = _kinetic_law(
        kinetic_law_id="mm-multi",
        law_type=KineticLawType.MICHAELIS_MENTEN,
        expression=None,
        parameter_ids=("kcat", "km_a", "km_b"),
        species_ids=("a", "b"),
    )
    model = _resolved_model(
        law,
        (
            _parameter(parameter_id="kcat"),
            _parameter(parameter_id="km_a"),
            _parameter(parameter_id="km_b"),
        ),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )
    assert package.full_antimony.unresolved_kinetic_law_ids == ("mm-multi",)
    assert "law_type=MICHAELIS_MENTEN" in package.full_antimony.antimony_text
    law_type = package.model_specification.kinetic_laws[0].law_type
    assert law_type is KineticLawType.MICHAELIS_MENTEN


# --- Catalytic context (Step 50) -----------------------------------------------------------------


def test_protein_general_catalyst_serializes_normally():
    law = _kinetic_law(protein_id="p1")
    model = _resolved_model(law, (_parameter(parameter_id="k1"),))
    artifact = generate_antimony(model).full_antimony
    assert "catalytic_context=p1" in artifact.antimony_text


def test_complex_general_catalyst_serializes_normally():
    law = _kinetic_law(complex_id="cplx1")
    model = _resolved_model(law, (_parameter(parameter_id="k1"),))
    artifact = generate_antimony(model).full_antimony
    assert "catalytic_context=cplx1" in artifact.antimony_text


# --- Biochemical reaction identity vs. kinetic contribution (Steps 25-28) -----------------------


def test_single_context_reaction_produces_exactly_one_antimony_reaction():
    """Step 25: one reaction, one kinetic-law context -- exactly one Antimony reaction, id
    derived from reaction_id, with the expected rate expression."""
    model = _model()
    package = generate_antimony(model)
    id_map = build_identifier_map(model)
    text = package.full_antimony.antimony_text
    assert id_map.reactions["r1"] == "J_r1"
    assert text.count("J_r1:") == 1
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert package.full_antimony.unresolved_reaction_ids == ()


def _two_context_model(**law_overrides) -> ModelSpecification:
    law_e = _kinetic_law(
        kinetic_law_id="k-E",
        enzyme_state_id="E",
        parameter_ids=("k_e",),
        expression="k_e * a",
        **law_overrides,
    )
    law_ep = _kinetic_law(
        kinetic_law_id="k-EP",
        enzyme_state_id="E_P",
        parameter_ids=("k_ep",),
        expression="k_ep * a",
        **law_overrides,
    )
    return _model(
        full_network=_network(
            enzyme_states=(
                CuratedEnzymeState(id="E", state_type="unmodified"),
                CuratedEnzymeState(id="E_P", state_type="phosphorylated"),
            )
        ),
        kinetic_laws=(law_e, law_ep),
        parameters=(_parameter(parameter_id="k_e"), _parameter(parameter_id="k_ep")),
        module_specifications=(),
    )


def test_multiple_kinetic_contexts_never_duplicate_the_biochemical_reaction():
    """Step 26: one reaction, two catalytic contexts (E, E_P), no simultaneous-composition
    evidence -- exactly one biochemical reaction identity, no J_r1_E/J_r1_EP duplicates, no
    summed rate, reaction marked unresolved, both law ids preserved in unresolved metadata,
    full artifact not EXECUTABLE."""
    model = _two_context_model()
    id_map = build_identifier_map(model)
    assert id_map.reactions["r1"] == "J_r1"
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert text.count("J_r1:") == 1
    assert "J_r1_E" not in text
    assert "k_e * a" not in text.split("//")[0]
    assert "k_ep * a" not in text.split("//")[0]
    readiness = package.full_antimony.readiness
    assert readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert package.full_antimony.unresolved_reaction_ids == ("r1",)
    assert set(package.full_antimony.unresolved_kinetic_law_ids) == {"k-E", "k-EP"}
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED" in text
    assert "multiple catalytic contexts" in text


def test_isozymes_with_independent_resolved_contexts_compose_additively():
    """Multi-Context Catalytic Rate Composition increment (Stage 1): two isozyme-style
    protein-general catalytic contexts, each independently resolved, with no curated basis
    for mutual exclusivity -- no duplicate reactions, no arbitrary law selection, never
    merged into one shared law, but now genuinely, additively composed (never a naive,
    unparenthesized concatenation) rather than left unconditionally unresolved."""
    law_1 = _kinetic_law(
        kinetic_law_id="k-iso1", protein_id="p1", parameter_ids=("k1",), expression="k1 * a"
    )
    law_2 = _kinetic_law(
        kinetic_law_id="k-iso2", protein_id="p2", parameter_ids=("k2",), expression="k2 * a"
    )
    model = _model(
        kinetic_laws=(law_1, law_2),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k2")),
        module_specifications=(),
    )
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert text.count("J_r1:") == 1
    assert "k1 * a + k2 * a" not in text
    assert "(p_k1 * s_a) + (p_k2 * s_a)" in text
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY" in text
    readiness = package.full_antimony.readiness
    assert readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert package.full_antimony.unresolved_reaction_ids == ()


def test_isozymes_with_different_law_types_compose_additively():
    """Composition never requires the contexts to share the same kinetic-law type -- MCT1/
    FAS1-shaped: one context MASS_ACTION, the other MICHAELIS_MENTEN, both independently
    resolved, both real, distinct catalyst identities."""
    law_1 = _kinetic_law(
        kinetic_law_id="k-iso1",
        protein_id="p1",
        law_type=KineticLawType.MASS_ACTION,
        parameter_ids=("k1",),
        expression="k1 * a",
    )
    law_2 = _kinetic_law(
        kinetic_law_id="k-iso2",
        protein_id="p2",
        law_type=KineticLawType.MICHAELIS_MENTEN,
        parameter_ids=("kcat2", "km2"),
        expression="kcat2 * a / (km2 + a)",
        species_ids=("a",),
    )
    model = _model(
        kinetic_laws=(law_1, law_2),
        parameters=(
            _parameter(parameter_id="k1"),
            _parameter(parameter_id="kcat2", value=Decimal("1")),
            _parameter(parameter_id="km2", value=Decimal("10")),
        ),
        module_specifications=(),
    )
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    reaction_line = next(line for line in text.splitlines() if line.startswith("J_r1:"))
    assert "law_types=(MASS_ACTION,MICHAELIS_MENTEN)" in reaction_line


def _two_complex_model(**law_overrides) -> ModelSpecification:
    law_c1 = _kinetic_law(
        kinetic_law_id="k-c1", complex_id="c1", parameter_ids=("k_c1",), expression="k_c1 * a",
        **law_overrides,
    )
    law_c2 = _kinetic_law(
        kinetic_law_id="k-c2", complex_id="c2", parameter_ids=("k_c2",), expression="k_c2 * a",
        **law_overrides,
    )
    return _model(
        kinetic_laws=(law_c1, law_c2),
        parameters=(_parameter(parameter_id="k_c1"), _parameter(parameter_id="k_c2")),
        module_specifications=(),
    )


def test_two_complexes_compose_additively():
    """Generalization beyond isozymes: two distinct, independently-resolved complex-general
    contexts compose exactly like two protein-general ones."""
    model = _two_complex_model()
    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    assert "(p_k_c1 * s_a) + (p_k_c2 * s_a)" in reaction_line
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY" in reaction_line


def test_protein_and_complex_contexts_never_composed():
    """A whole enzyme complex and an independently-catalyzing protein are never composed --
    nothing curated confirms that pairing is not double-counting (e.g. the protein could be
    one of the complex's own subunits)."""
    law_protein = _kinetic_law(
        kinetic_law_id="k-p1", protein_id="p1", parameter_ids=("k1",), expression="k1 * a"
    )
    law_complex = _kinetic_law(
        kinetic_law_id="k-c1", complex_id="c1", parameter_ids=("k_c1",), expression="k_c1 * a"
    )
    model = _model(
        kinetic_laws=(law_protein, law_complex),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k_c1")),
        module_specifications=(),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )
    assert package.full_antimony.unresolved_reaction_ids == ("r1",)
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED" in reaction_line


def test_enzyme_state_and_protein_context_mix_never_composed():
    """A protein-general context alongside a distinct enzyme-state context of some other
    (or the same) protein is never composed -- mixing granularities is exactly as
    unestablished as mixing protein-general with complex-general."""
    law_protein = _kinetic_law(
        kinetic_law_id="k-p1", protein_id="p1", parameter_ids=("k1",), expression="k1 * a"
    )
    law_state = _kinetic_law(
        kinetic_law_id="k-E", enzyme_state_id="E", parameter_ids=("k_e",), expression="k_e * a"
    )
    model = _model(
        full_network=_network(
            enzyme_states=(CuratedEnzymeState(id="E", protein_id="p2", state_type="unmodified"),)
        ),
        kinetic_laws=(law_protein, law_state),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k_e")),
        module_specifications=(),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )


def _pool(**overrides) -> EnzymeStatePool:
    merged = {
        "protein_id": "p1",
        "state_ids": ("E", "E_P"),
        "transition_ids": (),
        "policy_version": "test-policy",
    } | overrides
    return EnzymeStatePool(**merged)


def test_enzyme_states_in_a_modeled_pool_compose_additively():
    """Multi-Context Catalytic Rate Composition increment, Stage 2: two enzyme-state
    contexts of the *same* protein's dynamically-modeled, conserved pool are now
    composable -- the exact restriction Stage 1 deliberately left in place."""
    law_e = _kinetic_law(
        kinetic_law_id="k-E", enzyme_state_id="E", parameter_ids=("k_e",), expression="k_e * a"
    )
    law_ep = _kinetic_law(
        kinetic_law_id="k-EP", enzyme_state_id="E_P", parameter_ids=("k_ep",), expression="k_ep * a"
    )
    model = _model(
        full_network=_network(
            enzyme_states=(
                CuratedEnzymeState(id="E", protein_id="p1", state_type="unmodified"),
                CuratedEnzymeState(id="E_P", protein_id="p1", state_type="phosphorylated"),
            )
        ),
        kinetic_laws=(law_e, law_ep),
        parameters=(_parameter(parameter_id="k_e"), _parameter(parameter_id="k_ep")),
        module_specifications=(),
        enzyme_state_pools=(_pool(),),
    )
    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    expression = reaction_line.split(";")[1].strip()
    assert expression == "(p_k_e * s_a) + (p_k_ep * s_a)"
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY" in reaction_line


def test_enzyme_states_without_a_modeled_pool_are_still_unresolved():
    """Preserves Stage 1 behavior exactly: two enzyme-state contexts with no
    ``EnzymeStatePool`` at all (no curated transition ever established a conservation
    basis) are never composed."""
    law_e = _kinetic_law(
        kinetic_law_id="k-E", enzyme_state_id="E", parameter_ids=("k_e",), expression="k_e * a"
    )
    law_ep = _kinetic_law(
        kinetic_law_id="k-EP", enzyme_state_id="E_P", parameter_ids=("k_ep",), expression="k_ep * a"
    )
    model = _model(
        full_network=_network(
            enzyme_states=(
                CuratedEnzymeState(id="E", protein_id="p1", state_type="unmodified"),
                CuratedEnzymeState(id="E_P", protein_id="p1", state_type="phosphorylated"),
            )
        ),
        kinetic_laws=(law_e, law_ep),
        parameters=(_parameter(parameter_id="k_e"), _parameter(parameter_id="k_ep")),
        module_specifications=(),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED" in reaction_line


def test_enzyme_states_from_two_different_pools_are_never_composed():
    """Distinct parent proteins never share a conservation pool -- even if, by
    construction error, two states from two different pools ended up on the same
    reaction, they must never be composed."""
    law_e = _kinetic_law(
        kinetic_law_id="k-E", enzyme_state_id="E", parameter_ids=("k_e",), expression="k_e * a"
    )
    law_f = _kinetic_law(
        kinetic_law_id="k-F", enzyme_state_id="F", parameter_ids=("k_f",), expression="k_f * a"
    )
    model = _model(
        full_network=_network(
            enzyme_states=(
                CuratedEnzymeState(id="E", protein_id="p1", state_type="unmodified"),
                CuratedEnzymeState(id="E_P", protein_id="p1", state_type="phosphorylated"),
                CuratedEnzymeState(id="F", protein_id="p2", state_type="unmodified"),
                CuratedEnzymeState(id="F_P", protein_id="p2", state_type="phosphorylated"),
            )
        ),
        kinetic_laws=(law_e, law_f),
        parameters=(_parameter(parameter_id="k_e"), _parameter(parameter_id="k_f")),
        module_specifications=(),
        enzyme_state_pools=(
            _pool(protein_id="p1", state_ids=("E", "E_P")),
            _pool(protein_id="p2", state_ids=("F", "F_P")),
        ),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )


def test_enzyme_state_composition_is_deterministically_ordered():
    law_ep = _kinetic_law(
        kinetic_law_id="k-EP", enzyme_state_id="E_P", parameter_ids=("k_ep",), expression="k_ep * a"
    )
    law_e = _kinetic_law(
        kinetic_law_id="k-E", enzyme_state_id="E", parameter_ids=("k_e",), expression="k_e * a"
    )
    network = _network(
        enzyme_states=(
            CuratedEnzymeState(id="E", protein_id="p1", state_type="unmodified"),
            CuratedEnzymeState(id="E_P", protein_id="p1", state_type="phosphorylated"),
        )
    )
    params = (_parameter(parameter_id="k_e"), _parameter(parameter_id="k_ep"))
    pools = (_pool(),)
    model_forward = _model(
        full_network=network,
        kinetic_laws=(law_e, law_ep),
        parameters=params,
        module_specifications=(),
        enzyme_state_pools=pools,
    )
    model_reversed = _model(
        full_network=network,
        kinetic_laws=(law_ep, law_e),
        parameters=params,
        module_specifications=(),
        enzyme_state_pools=pools,
    )
    text_forward = generate_antimony(model_forward).full_antimony.antimony_text
    text_reversed = generate_antimony(model_reversed).full_antimony.antimony_text
    assert text_forward == text_reversed


def test_three_isozymes_compose_in_deterministic_order_regardless_of_input_order():
    """Deterministic expression ordering: the composed expression is always sorted by
    ``kinetic_law_id``, never by construction/input order."""
    law_a = _kinetic_law(
        kinetic_law_id="k-zzz", protein_id="p3", parameter_ids=("k3",), expression="k3 * a"
    )
    law_b = _kinetic_law(
        kinetic_law_id="k-aaa", protein_id="p1", parameter_ids=("k1",), expression="k1 * a"
    )
    law_c = _kinetic_law(
        kinetic_law_id="k-mmm", protein_id="p2", parameter_ids=("k2",), expression="k2 * a"
    )
    params = (
        _parameter(parameter_id="k1"),
        _parameter(parameter_id="k2"),
        _parameter(parameter_id="k3"),
    )
    model_forward = _model(
        kinetic_laws=(law_a, law_b, law_c), parameters=params, module_specifications=()
    )
    model_reversed = _model(
        kinetic_laws=(law_c, law_b, law_a), parameters=params, module_specifications=()
    )
    text_forward = generate_antimony(model_forward).full_antimony.antimony_text
    text_reversed = generate_antimony(model_reversed).full_antimony.antimony_text
    assert text_forward == text_reversed
    reaction_line = next(
        line for line in text_forward.splitlines() if line.startswith("J_r1:")
    )
    expression = reaction_line.split(";")[1].strip()
    assert expression == "(p_k1 * s_a) + (p_k2 * s_a) + (p_k3 * s_a)"


def test_one_unresolved_isozyme_contribution_does_not_contaminate_the_other():
    """One unresolved contribution (a PLACEHOLDER parameter, no numeric value) must never be
    silently dropped from the sum, and must never corrupt its sibling's own, independently
    computed resolution -- the reaction stays conservatively unresolved as a whole, but the
    resolved contribution's own law/parameters are completely untouched."""
    law_resolved = _kinetic_law(
        kinetic_law_id="k-iso1", protein_id="p1", parameter_ids=("k1",), expression="k1 * a"
    )
    law_unresolved = _kinetic_law(
        kinetic_law_id="k-iso2", protein_id="p2", parameter_ids=("k2",), expression="k2 * a"
    )
    model = _model(
        kinetic_laws=(law_resolved, law_unresolved),
        parameters=(
            _parameter(parameter_id="k1"),
            _parameter(parameter_id="k2", source=ParameterSource.PLACEHOLDER, value=None),
        ),
        module_specifications=(),
    )
    package = generate_antimony(model)
    assert (
        package.full_antimony.readiness
        is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )
    assert package.full_antimony.unresolved_reaction_ids == ("r1",)
    # Both law ids are still named -- the resolved one's own identity/context is preserved
    # in the disclosure, never omitted just because a sibling is unresolved.
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    assert "k-iso1[p1]" in reaction_line
    assert "k-iso2[p2]" in reaction_line
    assert "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSABLE_BUT_UNRESOLVED" in reaction_line
    # k-iso1's own unresolved_kinetic_law_ids status: neither law is individually flagged
    # missing a value (unresolved_kinetic_law_ids exists at the reaction level here, since
    # the reaction as a whole withholds its rate) -- but only k2 is the genuinely missing
    # parameter, never k1.
    assert package.full_antimony.unresolved_kinetic_law_ids == ("k-iso1", "k-iso2")


def test_single_catalyst_behavior_unchanged_by_composition_gate():
    """Single-context reactions are completely unaffected by this increment."""
    model = _model()
    package = generate_antimony(model)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    reaction_line = next(
        line for line in package.full_antimony.antimony_text.splitlines()
        if line.startswith("J_r1:")
    )
    assert "COMPOSED" not in reaction_line


def test_enzyme_state_specific_contexts_preserved_but_composition_unresolved():
    """Step 28: E and E_P remain individually inspectable (kinetic_law_id, enzyme_state_id,
    parameter_ids all still visible in the unresolved comment) even though the reaction
    itself is one biochemical identity with an unresolved composed rate."""
    model = _two_context_model()
    text = generate_antimony(model).full_antimony.antimony_text
    reaction_line = next(line for line in text.splitlines() if line.startswith("J_r1:"))
    assert "k-E[E]" in reaction_line
    assert "k-EP[E_P]" in reaction_line
    equation_and_rest = reaction_line.split("//", 1)[0]
    assert equation_and_rest.count(";") == 1  # no rate clause, only the stoichiometric equation


def test_multiple_tentative_contexts_are_not_automatically_composed():
    """Step 20 (revision): multiple tentative mass-action contexts on one reaction are
    treated like any other unresolved multi-context case -- never summed just because both
    happen to be tentative."""
    model = _two_context_model(
        law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.HEURISTIC,
    )
    package = generate_antimony(model)
    readiness = package.full_antimony.readiness
    assert readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert package.full_antimony.unresolved_reaction_ids == ("r1",)


# --- Parameter serialization (Step 51) ------------------------------------------------------------


def test_curated_parameter_value_and_unit_preserved_as_comment():
    law = _kinetic_law()
    param = _parameter(
        parameter_id="k1", source=ParameterSource.CURATED, value=Decimal("2.5"), unit="1/s"
    )
    model = _resolved_model(law, (param,))
    text = generate_antimony(model).full_antimony.antimony_text
    assert "p_k1 = 2.5;" in text
    assert "source=CURATED" in text
    assert "unit=1/s" in text


def test_literature_derived_parameter_serialized_with_source_disclosed():
    law = _kinetic_law()
    param = _parameter(
        parameter_id="k1", source=ParameterSource.LITERATURE_DERIVED, value=Decimal("1")
    )
    model = _resolved_model(law, (param,))
    text = generate_antimony(model).full_antimony.antimony_text
    assert "source=LITERATURE_DERIVED" in text


def test_placeholder_parameter_never_gets_a_fabricated_numeric_value():
    law = _kinetic_law()
    param = _parameter(parameter_id="k1", source=ParameterSource.PLACEHOLDER, value=None)
    model = _resolved_model(law, (param,))
    artifact = generate_antimony(model).full_antimony
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert "1.0" not in artifact.antimony_text
    assert "PARAMETER_VALUE_UNRESOLVED" in artifact.antimony_text
    assert "UNRESOLVED (parameter_id=k1 source=PLACEHOLDER)" in artifact.antimony_text


def test_parameter_value_never_mutated_by_generation():
    law = _kinetic_law()
    param = _parameter(parameter_id="k1", value=Decimal("2.5"))
    model = _resolved_model(law, (param,))
    generate_antimony(model)
    assert model.parameters[0].value == Decimal("2.5")
    assert model.parameters[0].source is ParameterSource.CURATED


# --- Module views (Step 52) -----------------------------------------------------------------------


def test_module_view_contains_only_module_reactions_and_species():
    model = _model(
        full_network=_network(
            species=(_species(species_id="a"), _species(species_id="b"), _species(species_id="c")),
            reactions=(
                _reaction(reaction_id="r1"),
                _reaction(
                    reaction_id="r2",
                    participants=(
                        _participant(species_id="b", role=ParticipantRole.REACTANT),
                        _participant(species_id="c", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
        ),
        kinetic_laws=(
            _kinetic_law(kinetic_law_id="k1", reaction_id="r1"),
            _kinetic_law(
                kinetic_law_id="k2", reaction_id="r2", parameter_ids=("k2",), species_ids=("b",),
                expression="k2 * b",
            ),
        ),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k2")),
        module_specifications=(
            _module(
                module_id="mod-1",
                reaction_ids=("r1",),
                species_ids=("a", "b"),
                parameter_ids=("k1",),
            ),
        ),
    )
    view = generate_antimony(model).module_artifacts[0].antimony_view
    assert "J_r1" in view
    assert "J_r2" not in view
    assert "species s_a" in view
    assert "species s_c" not in view


def test_multiple_modules_each_get_their_own_artifact():
    model = _model(
        full_network=_network(
            species=(_species(species_id="a"), _species(species_id="b"), _species(species_id="c")),
            reactions=(
                _reaction(reaction_id="r1"),
                _reaction(
                    reaction_id="r2",
                    participants=(
                        _participant(species_id="b", role=ParticipantRole.REACTANT),
                        _participant(species_id="c", role=ParticipantRole.PRODUCT),
                    ),
                ),
            ),
        ),
        kinetic_laws=(
            _kinetic_law(kinetic_law_id="k1", reaction_id="r1"),
            _kinetic_law(
                kinetic_law_id="k2", reaction_id="r2", parameter_ids=("k2",), species_ids=("b",),
                expression="k2 * b",
            ),
        ),
        parameters=(_parameter(parameter_id="k1"), _parameter(parameter_id="k2")),
        module_specifications=(
            _module(
                module_id="mod-a",
                reaction_ids=("r1",),
                species_ids=("a", "b"),
                parameter_ids=("k1",),
            ),
            _module(
                module_id="mod-b",
                reaction_ids=("r2",),
                species_ids=("b", "c"),
                parameter_ids=("k2",),
                compartment_ids=("cyto",),
            ),
        ),
    )
    package = generate_antimony(model)
    assert {a.module_id for a in package.module_artifacts} == {"mod-a", "mod-b"}


def test_module_view_never_invents_a_source_or_sink_reaction():
    model = _model()
    view = generate_antimony(model).module_artifacts[0].antimony_view
    assert view.count("->") == 1


def test_module_marked_view_only_without_boundary_interfaces():
    model = _model()
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.readiness is AntimonyArtifactReadiness.VIEW_ONLY
    assert artifact.standalone_antimony is None


def test_module_view_preserves_unresolved_composition_without_duplicating_reaction():
    """Step 30: a module view containing a multi-context reaction still has exactly one
    reaction line for it, reuses the full-model Antimony reaction id, and preserves the
    unresolved state -- never duplicated by kinetic-law context."""
    base = _two_context_model()
    model = _model(
        full_network=base.full_network,
        kinetic_laws=base.kinetic_laws,
        parameters=base.parameters,
        module_specifications=(
            _module(reaction_ids=("r1",), species_ids=("a", "b"), parameter_ids=("k_e", "k_ep")),
        ),
    )
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.antimony_view is not None
    assert artifact.antimony_view.count("J_r1:") == 1
    assert artifact.readiness is AntimonyArtifactReadiness.VIEW_ONLY


# --- Standalone module eligibility (Step 53) ----------------------------------------------------


def test_standalone_withheld_without_explicit_boundary_interfaces():
    model = _model()
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.standalone_antimony is None
    assert artifact.readiness is AntimonyArtifactReadiness.VIEW_ONLY


def test_standalone_generated_when_boundary_interfaces_explicit_and_resolved():
    interface = ModuleBoundaryInterface(
        species_id="a",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="held constant externally",
        externally_controlled=True,
        initial_value=Decimal("5"),
    )
    model = _model(module_specifications=(_module(boundary_interfaces=(interface,)),))
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert artifact.standalone_antimony is not None
    assert "const s_a;" in artifact.standalone_antimony
    assert "s_a = 5;" in artifact.standalone_antimony


def test_standalone_withheld_when_interfaces_explicit_but_kinetics_unresolved():
    interface = ModuleBoundaryInterface(
        species_id="a",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="held constant externally",
        externally_controlled=True,
    )
    law = _kinetic_law(
        law_type=KineticLawType.UNASSIGNED, expression=None, parameter_ids=(), species_ids=()
    )
    model = _model(
        kinetic_laws=(law,),
        parameters=(),
        module_specifications=(
            _module(boundary_interfaces=(interface,), parameter_ids=(), kinetic_law_ids=()),
        ),
    )
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert artifact.standalone_antimony is None
    assert artifact.unresolved_kinetic_law_ids == ("k1",)
    assert artifact.antimony_view is not None


def test_standalone_withheld_when_unresolved_catalytic_composition_blocks_it():
    """Step 31: unresolved multi-context composition blocks standalone executable module
    generation even though the module's own boundary interfaces are fully explicit."""
    interface = ModuleBoundaryInterface(
        species_id="a",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="held constant externally",
        externally_controlled=True,
    )
    base = _two_context_model()
    model = _model(
        full_network=base.full_network,
        kinetic_laws=base.kinetic_laws,
        parameters=base.parameters,
        module_specifications=(
            _module(
                reaction_ids=("r1",),
                species_ids=("a", "b"),
                parameter_ids=("k_e", "k_ep"),
                boundary_interfaces=(interface,),
            ),
        ),
    )
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.standalone_antimony is None
    assert artifact.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    assert artifact.unresolved_reaction_ids == ("r1",)
    assert set(artifact.unresolved_kinetic_law_ids) == {"k-E", "k-EP"}


def test_standalone_never_invents_a_boundary_condition_value():
    """No initial_value declared on the interface -- standalone must not fabricate one."""
    interface = ModuleBoundaryInterface(
        species_id="a",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="externally controlled, value unspecified",
        externally_controlled=True,
    )
    model = _model(module_specifications=(_module(boundary_interfaces=(interface,)),))
    artifact = generate_antimony(model).module_artifacts[0]
    assert artifact.standalone_antimony is not None
    assert "const s_a;" in artifact.standalone_antimony
    assert "s_a = " not in artifact.standalone_antimony.split("const s_a;")[1].split("\n")[1]


# --- Determinism and immutability (Step 54-55) --------------------------------------------------


def test_full_and_module_artifacts_are_byte_identical_across_two_runs():
    model = _model()
    first = generate_antimony(model)
    second = generate_antimony(model)
    assert first.full_antimony == second.full_antimony
    assert first.module_artifacts == second.module_artifacts


def test_generation_does_not_mutate_full_network_or_parameters():
    model = _model()
    network_before = model.full_network
    parameters_before = model.parameters
    generate_antimony(model)
    assert model.full_network == network_before
    assert model.parameters == parameters_before


def test_multi_context_reaction_resolution_is_order_independent():
    """Step 32: permuting the order of a reaction's multiple kinetic-law contexts must not
    change the Antimony reaction id, unresolved metadata, comment, or overall text."""
    forward = _two_context_model()
    reversed_order = _model(
        full_network=forward.full_network,
        kinetic_laws=tuple(reversed(forward.kinetic_laws)),
        parameters=forward.parameters,
        module_specifications=(),
    )
    first = generate_antimony(forward)
    second = generate_antimony(reversed_order)
    assert first.full_antimony.antimony_text == second.full_antimony.antimony_text
    assert first.full_antimony.readiness == second.full_antimony.readiness
    assert (
        first.full_antimony.unresolved_reaction_ids
        == second.full_antimony.unresolved_reaction_ids
    )
    assert (
        first.full_antimony.unresolved_kinetic_law_ids
        == second.full_antimony.unresolved_kinetic_law_ids
    )
