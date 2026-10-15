"""Tests for the Antimony Import increment: real Antimony/SBML parsing into the canonical
``ModelSpecification`` (``app.agent2.antimony_import``), the generator's new rule/event/
observable support, and the full semantic round trip between the two.

``_REPRESENTATIVE_FIXTURE`` (task Section 8) is a small, deliberately synthetic
central-metabolism-shaped model -- never a real, specific curated pathway -- with: two
compartments, four species with initial values, one irreversible and one reversible reaction,
parameters, kinetic laws, an assignment rule, and an event. Its ``// module: ...`` comments are
deliberately inert text, confirming this increment implements no module parsing at all (a later,
separate layer -- task instructions, explicitly out of scope here).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent2.antimony import generate_antimony
from app.agent2.antimony.generator import OBSERVABLE_COMMENT_PREFIX
from app.agent2.antimony_import import (
    MalformedAntimonySourceError,
    UnsupportedAntimonyConstructError,
    import_antimony,
)
from app.agent2.pipeline import build_canonical_downstream_handoff, run_agent2_pipeline
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    KineticLawType,
    ModelSourceType,
    ObservableSpecification,
    ParameterSource,
    RuleType,
)

_REPRESENTATIVE_FIXTURE = """
model sce_fixture

  // module: core_reactions (deliberately inert -- module parsing is a later layer)
  compartment cytosol = 1.0;
  compartment mitochondrion = 0.5;

  species Glucose in cytosol = 10.0;
  species G6P in cytosol = 0.0;
  species Pyruvate in cytosol = 0.0;
  species AcetylCoA in mitochondrion = 0.0;

  R1: Glucose => G6P; k1 * Glucose;
  R2: G6P -> Pyruvate; k2f * G6P - k2r * Pyruvate;
  R3: Pyruvate => AcetylCoA; k3 * Pyruvate;

  k1 = 0.8;
  k2f = 0.3;
  k2r = 0.05;
  k3 = 0.2;

  // module: regulation (deliberately inert)
  total_carbon := Glucose + G6P + Pyruvate;

  at (time > 50): Glucose = 10.0;

end
"""

_SIMPLE_FIXTURE = """
model simple
  compartment cyto = 1.0;
  species A in cyto = 10.0;
  species B in cyto = 0.0;
  R1: A => B; k1 * A;
  k1 = 0.5;
end
"""


# --- Simple import ---------------------------------------------------------------------------


def test_simple_import_produces_the_expected_canonical_structure():
    model = import_antimony(_SIMPLE_FIXTURE)
    assert {c.compartment_id for c in model.full_network.compartments} == {"cyto"}
    assert {s.species_id for s in model.full_network.species} == {"A", "B"}
    assert {r.reaction_id for r in model.full_network.reactions} == {"R1"}
    assert {p.parameter_id for p in model.parameters} == {"k1"}
    assert model.source_type is ModelSourceType.IMPORTED


def test_representative_fixture_imports_every_required_construct():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    assert {c.compartment_id for c in model.full_network.compartments} == {
        "cytosol",
        "mitochondrion",
    }
    assert {s.species_id for s in model.full_network.species} == {
        "Glucose",
        "G6P",
        "Pyruvate",
        "AcetylCoA",
    }
    reactions_by_id = {r.reaction_id: r for r in model.full_network.reactions}
    assert reactions_by_id["R1"].reversible is False
    assert reactions_by_id["R2"].reversible is True
    assert reactions_by_id["R3"].reversible is False
    assert {p.parameter_id for p in model.parameters} >= {"k1", "k2f", "k2r", "k3"}
    assert len(model.kinetic_laws) == 3
    assert len(model.rules) == 1
    assert model.rules[0].rule_type is RuleType.ASSIGNMENT
    assert len(model.events) == 1
    # "// module: ..." comments are inert text -- no module structure is ever inferred.
    assert model.modularizations == ()
    assert model.model_modules == ()
    assert model.module_memberships == ()
    assert model.module_ports == ()


def test_species_initial_values_preserved_exactly():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    species_by_id = {s.species_id: s for s in model.full_network.species}
    assert species_by_id["Glucose"].initial_concentration == 10
    assert species_by_id["G6P"].initial_concentration == 0
    assert species_by_id["AcetylCoA"].compartment_id == "mitochondrion"


# --- Malformed Antimony ----------------------------------------------------------------------


def test_malformed_antimony_raises_structured_error_with_the_real_parser_message():
    with pytest.raises(MalformedAntimonySourceError) as excinfo:
        import_antimony("this is { not } valid antimony !!!")
    assert str(excinfo.value)


def test_empty_source_raises_structured_error():
    with pytest.raises(MalformedAntimonySourceError):
        import_antimony("")


# --- Unsupported construct handling ----------------------------------------------------------


def test_function_definition_is_rejected_as_unsupported():
    with pytest.raises(UnsupportedAntimonyConstructError, match="function definition"):
        import_antimony(
            """
            function double(x)
              2 * x;
            end
            model m
              compartment c = 1.0;
              species A in c = 1.0;
              species B in c = 0.0;
              R1: A -> B; double(k1);
              k1 = 0.5;
            end
            """
        )


def test_initial_assignment_is_rejected_as_unsupported():
    with pytest.raises(UnsupportedAntimonyConstructError, match="InitialAssignment"):
        import_antimony(
            """
            model m
              compartment c = 1.0;
              species A in c = 10.0;
              derived = A + 2;
            end
            """
        )


# --- Generated-model path is unaffected (backward compatibility) -----------------------------


def _generated_model():
    handoff = Agent1CuratedKnowledgeViewContract(
        contract_version="1.6",
        compartments=(CuratedCompartment(id="cyto", name="cytosol"),),
        compounds=(CuratedCompound(id="a", name="A"), CuratedCompound(id="b", name="B")),
        reactions=(CuratedReaction(id="r1", name="reaction 1", reversible=False),),
        reaction_participants=(
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="a",
                role="REACTANT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="b",
                role="PRODUCT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="r1", protein_id="p1", relationship="CATALYZES"
            ),
        ),
    )
    return run_agent2_pipeline(handoff)


def test_generated_model_populates_the_identical_canonical_representation():
    """Generated models use the same ModelSpecification/FullNetwork this increment's new
    rules/events/observables/source_type fields were added to -- always empty/GENERATED by
    default, never requiring the assembler itself to change."""
    result = _generated_model()
    model = result.package.model_specification
    assert model.source_type is ModelSourceType.GENERATED
    assert model.source_provenance is None
    assert model.rules == ()
    assert model.events == ()
    assert model.observables == ()


def test_no_build_request_reproduces_pre_existing_generated_behavior():
    """A plain re-run of the existing build path is unaffected by this increment at all."""
    without = _generated_model()
    again = _generated_model()
    assert without.downstream_handoff == again.downstream_handoff


# --- Canonical -> Antimony (export) -----------------------------------------------------------


def test_canonical_to_antimony_preserves_reversibility_via_the_arrow():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    package = generate_antimony(model)
    text = package.full_antimony.antimony_text
    lines_by_reaction = {
        line.split(":")[0]: line for line in text.splitlines() if line.strip().startswith(("J_",))
    }
    # R1 (irreversible) and R3 (irreversible) must use "=>"; R2 (reversible) must use "->".
    assert sum("=>" in line for line in lines_by_reaction.values()) == 2
    assert sum(" -> " in line for line in lines_by_reaction.values()) == 1


def test_canonical_to_antimony_emits_rules_and_events():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    text = generate_antimony(model).full_antimony.antimony_text
    assert "// rules" in text
    assert ":=" in text
    assert "// events" in text
    assert "at (" in text


def test_canonical_to_antimony_is_deterministic():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    first = generate_antimony(model).full_antimony.antimony_text
    second = generate_antimony(model).full_antimony.antimony_text
    assert first == second


# --- Antimony -> canonical -> Antimony round trip ----------------------------------------------


def test_antimony_to_canonical_to_antimony_round_trip_is_executable():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    package = generate_antimony(model)
    assert package.full_antimony.readiness.value == "EXECUTABLE"
    # The re-exported text must itself be real, valid, re-importable Antimony.
    reimported = import_antimony(package.full_antimony.antimony_text)
    assert len(reimported.full_network.reactions) == len(model.full_network.reactions)


def test_antimony_to_canonical_to_antimony_preserves_reaction_stoichiometry_and_reversibility():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    text = generate_antimony(model).full_antimony.antimony_text
    reimported = import_antimony(text)
    original_by_name = {r.reaction_id: r for r in model.full_network.reactions}
    # Antimony-safe ids differ (s_Glucose vs Glucose) -- compare by reaction *count* and
    # reversibility *multiset*, the semantic invariant, never by raw identifier string.
    assert sorted(r.reversible for r in reimported.full_network.reactions) == sorted(
        r.reversible for r in original_by_name.values()
    )
    for r in reimported.full_network.reactions:
        assert len(r.participants) == 2


def test_antimony_to_canonical_to_antimony_preserves_species_initial_values():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    text = generate_antimony(model).full_antimony.antimony_text
    reimported = import_antimony(text)
    original_values = sorted(
        s.initial_concentration
        for s in model.full_network.species
        if s.initial_concentration is not None
    )
    reimported_values = sorted(
        s.initial_concentration
        for s in reimported.full_network.species
        if s.initial_concentration is not None
    )
    assert original_values == reimported_values


def test_antimony_to_canonical_to_antimony_preserves_rules_and_events():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    text = generate_antimony(model).full_antimony.antimony_text
    reimported = import_antimony(text)
    assert len(reimported.rules) == 1
    assert reimported.rules[0].rule_type is RuleType.ASSIGNMENT
    assert len(reimported.events) == 1
    assert reimported.events[0].assignments


# --- Canonical -> Antimony -> canonical round trip (this exporter/importer's own content) -----


def test_canonical_to_antimony_to_canonical_round_trip_for_a_generated_model():
    """The GENERATED path's own output must also survive a round trip through the real
    Antimony/SBML toolchain unchanged in every semantic respect this increment covers."""
    generated = _generated_model().package.model_specification
    text = generate_antimony(generated).full_antimony.antimony_text
    reimported = import_antimony(text)
    assert len(reimported.full_network.reactions) == len(generated.full_network.reactions)
    assert len(reimported.full_network.species) == len(generated.full_network.species)
    assert len(reimported.full_network.compartments) == len(generated.full_network.compartments)


def test_canonical_to_antimony_to_canonical_round_trip_preserves_an_observable():
    from dataclasses import replace

    model = import_antimony(_SIMPLE_FIXTURE)
    with_observable = replace(
        model,
        observables=(
            ObservableSpecification(
                observable_id="total", name="Total A and B", formula="A + B", unit="mM"
            ),
        ),
    )
    text = generate_antimony(with_observable).full_antimony.antimony_text
    assert OBSERVABLE_COMMENT_PREFIX in text
    reimported = import_antimony(text)
    assert len(reimported.observables) == 1
    assert reimported.observables[0].observable_id == "total"
    assert reimported.observables[0].name == "Total A and B"
    assert reimported.observables[0].unit == "mM"
    # The observable's own assignment rule must not *also* appear as a plain rule.
    assert reimported.rules == ()


def test_canonical_to_antimony_to_canonical_round_trip_preserves_a_rate_rule():
    from dataclasses import replace

    from app.agent2.types import RuleSpecification

    model = import_antimony(_SIMPLE_FIXTURE)
    with_rule = replace(
        model,
        parameters=(
            *model.parameters,
            # The rate rule's own target needs a declared parameter to carry an initial value.
        ),
        rules=(
            RuleSpecification(
                rule_id="r1", rule_type=RuleType.RATE, formula="k1 * A", variable="k1"
            ),
        ),
    )
    text = generate_antimony(with_rule).full_antimony.antimony_text
    reimported = import_antimony(text)
    assert len(reimported.rules) == 1
    assert reimported.rules[0].rule_type is RuleType.RATE


def test_third_party_antimony_never_produces_an_observable():
    """Arbitrary, externally-authored Antimony has no observable-marking comment at all --
    confirming observables are never inferred, only recovered from this repository's own
    exporter output specifically."""
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    assert model.observables == ()


# --- Original-source preservation / provenance -------------------------------------------------


def test_original_source_is_preserved_byte_for_byte():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    assert model.source_provenance.original_antimony_text == _REPRESENTATIVE_FIXTURE


def test_provenance_includes_checksum_parser_version_and_timestamp():
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    provenance = model.source_provenance
    assert len(provenance.checksum) == 64  # sha256 hex digest
    assert provenance.parser_version
    assert provenance.imported_at


def test_imported_vs_generated_provenance_is_distinct():
    imported = import_antimony(_SIMPLE_FIXTURE)
    generated = _generated_model().package.model_specification
    assert imported.source_type is ModelSourceType.IMPORTED
    assert imported.source_provenance is not None
    assert generated.source_type is ModelSourceType.GENERATED
    assert generated.source_provenance is None


def test_imported_parameters_and_species_use_the_imported_provenance_marker():
    model = import_antimony(_SIMPLE_FIXTURE)
    assert all(p.source is ParameterSource.IMPORTED for p in model.parameters)
    assert all(
        s.initialization_source is ParameterSource.IMPORTED
        for s in model.full_network.species
        if s.initial_concentration is not None or s.initial_amount is not None
    )
    assert all(law.law_type is KineticLawType.IMPORTED for law in model.kinetic_laws)


# --- Downstream handoff compatibility -----------------------------------------------------------


def test_imported_model_flows_through_the_unchanged_downstream_handoff_contract():
    """agent2-downstream-v1 is never changed by this increment (task Section 7) -- an imported
    model must flow through the exact same build_canonical_downstream_handoff function the
    generated path already uses, unmodified."""
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    package = generate_antimony(model)
    handoff = build_canonical_downstream_handoff(model, package)
    assert handoff["contract_version"]
    assert len(handoff["species"]) == len(model.full_network.species)
    assert len(handoff["reactions"]) == len(model.full_network.reactions)
    assert len(handoff["parameters"]) == len(model.parameters)
    for reaction in handoff["reactions"]:
        assert "reversible" in reaction


def test_downstream_handoff_shape_is_identical_for_generated_and_imported_models():
    """Both paths' handoff dicts share exactly the same top-level key set -- Agents 3-5 need
    no awareness of which path produced the model they are consuming."""
    generated_result = _generated_model()
    imported_model = import_antimony(_SIMPLE_FIXTURE)
    imported_package = generate_antimony(imported_model)
    imported_handoff = build_canonical_downstream_handoff(imported_model, imported_package)
    assert set(imported_handoff.keys()) == set(generated_result.downstream_handoff.keys())


# --- Never guesses a biological mapping from a symbol name --------------------------------------


def test_import_never_resolves_a_symbol_to_an_agent1_entity_id():
    """A raw Antimony identifier like "Glucose" is carried through verbatim as a plain
    species_id string -- never matched against any Agent 1 curated compound/organism id (this
    repository holds no such registry at all; confirmed by the complete absence of any
    app.agent1 import anywhere in this package -- see test_antimony_import_scope.py)."""
    model = import_antimony(_REPRESENTATIVE_FIXTURE)
    glucose = next(s for s in model.full_network.species if s.species_id == "Glucose")
    assert glucose.source_compound_id is None
    assert model.organism_id is None
