"""Tests for the Model Modularization increment: a derived layer on top of the canonical
whole-network model (``ModelModularization``/``ModelModule``/``ModuleMembership``/
``ModulePort``, ``app.agent2.modularization.derive_cross_module_connections``).

Never moves a species/reaction/parameter/rule/event/observable out of the canonical
``FullNetwork``/``ModelSpecification`` -- every assertion below that touches the canonical
model confirms this directly (component counts, identity) rather than only asserting the new
types' own shape.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony import generate_antimony
from app.agent2.antimony_import import import_antimony
from app.agent2.modularization import derive_cross_module_connections
from app.agent2.pipeline import build_canonical_downstream_handoff
from app.agent2.types import (
    BoundaryLikelihood,
    CompartmentSourceScope,
    CompartmentSpecification,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ModulePort,
    ModulePortDirection,
    ModulePortRole,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "c1",
        "name": "c1",
        "source_scope": CompartmentSourceScope.MODELING_CONSTRUCT,
        "assumptions": ("test fixture",),
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "A", "name": "A", "compartment_id": "c1"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "A",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "r1",
        "participants": (
            _participant(species_id="A", role=ParticipantRole.REACTANT),
            _participant(species_id="B", role=ParticipantRole.PRODUCT),
        ),
    } | overrides
    return ReactionSpecification(**merged)


def _linear_network() -> FullNetwork:
    """A -> B -> C, a minimal two-reaction chain used throughout this file."""
    return FullNetwork(
        network_id="n1",
        name="n1",
        compartments=(_compartment(),),
        species=(_species(species_id="A"), _species(species_id="B"), _species(species_id="C")),
        reactions=(
            _reaction(
                reaction_id="r1",
                participants=(
                    _participant(species_id="A", role=ParticipantRole.REACTANT),
                    _participant(species_id="B", role=ParticipantRole.PRODUCT),
                ),
            ),
            _reaction(
                reaction_id="r2",
                participants=(
                    _participant(species_id="B", role=ParticipantRole.REACTANT),
                    _participant(species_id="C", role=ParticipantRole.PRODUCT),
                ),
            ),
        ),
    )


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "kl1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": "k1 * A",
        "parameter_ids": ("k1",),
        "species_ids": ("A",),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    merged = {
        "parameter_id": "k1",
        "name": "k1",
        "source": ParameterSource.CURATED,
        "value": Decimal("0.5"),
    } | overrides
    return ParameterSpecification(**merged)


def _model(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _linear_network(),
        "kinetic_laws": (
            _kinetic_law(
                kinetic_law_id="kl1",
                reaction_id="r1",
                expression="k1 * A",
                parameter_ids=("k1",),
                species_ids=("A",),
            ),
            _kinetic_law(
                kinetic_law_id="kl2",
                reaction_id="r2",
                expression="k2 * B",
                parameter_ids=("k2",),
                species_ids=("B",),
            ),
        ),
        "parameters": (
            _parameter(parameter_id="k1", name="k1"),
            _parameter(parameter_id="k2", name="k2"),
        ),
    } | overrides
    return ModelSpecification(**merged)


# --- Canonical model with no modularization ----------------------------------------------------


def test_canonical_model_with_no_modularization_is_unaffected():
    model = _model()
    assert model.modularizations == ()
    assert model.model_modules == ()
    assert model.module_memberships == ()
    assert model.module_ports == ()


# --- One user-defined modularization, multiple modules -----------------------------------------


def _user_defined_split():
    """modA = {r1}, modB = {r2}, with shared species B as modA's output / modB's input."""
    modularization = ModelModularization(
        modularization_id="mod1",
        name="user split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
        confidence=BoundaryLikelihood.HIGH,
    )
    modules = (
        ModelModule(module_id="modA", name="Module A", biological_function="upstream step"),
        ModelModule(module_id="modB", name="Module B", biological_function="downstream step"),
    )
    memberships = (
        ModuleMembership(
            membership_id="mem_r1",
            modularization_id="mod1",
            module_id="modA",
            component_type=ModuleComponentType.REACTION,
            component_id="r1",
        ),
        ModuleMembership(
            membership_id="mem_r2",
            modularization_id="mod1",
            module_id="modB",
            component_type=ModuleComponentType.REACTION,
            component_id="r2",
        ),
        ModuleMembership(
            membership_id="mem_b_a",
            modularization_id="mod1",
            module_id="modA",
            component_type=ModuleComponentType.SPECIES,
            component_id="B",
        ),
        ModuleMembership(
            membership_id="mem_b_b",
            modularization_id="mod1",
            module_id="modB",
            component_type=ModuleComponentType.SPECIES,
            component_id="B",
        ),
    )
    ports = (
        ModulePort(
            port_id="port_a_out",
            modularization_id="mod1",
            module_id="modA",
            species_id="B",
            direction=ModulePortDirection.OUTPUT,
            role=ModulePortRole.PRODUCT,
        ),
        ModulePort(
            port_id="port_b_in",
            modularization_id="mod1",
            module_id="modB",
            species_id="B",
            direction=ModulePortDirection.INPUT,
            role=ModulePortRole.SUBSTRATE,
        ),
    )
    return _model(
        modularizations=(modularization,),
        model_modules=modules,
        module_memberships=memberships,
        module_ports=ports,
    )


def test_one_user_defined_modularization_with_multiple_modules():
    model = _user_defined_split()
    assert len(model.modularizations) == 1
    assert model.modularizations[0].method is ModularizationMethod.USER_DEFINED
    assert len(model.model_modules) == 2
    assert {m.module_id for m in model.model_modules} == {"modA", "modB"}


# --- Shared species / multi-module membership ---------------------------------------------------


def test_one_species_shared_across_modules_remains_one_canonical_object():
    model = _user_defined_split()
    b_memberships = [m for m in model.module_memberships if m.component_id == "B"]
    assert {m.module_id for m in b_memberships} == {"modA", "modB"}
    # Exactly one canonical SpeciesSpecification named "B" -- never duplicated per module.
    species_named_b = [s for s in model.full_network.species if s.species_id == "B"]
    assert len(species_named_b) == 1


def test_one_component_belonging_to_multiple_modules():
    model = _user_defined_split()
    memberships_for_b = [m for m in model.module_memberships if m.component_id == "B"]
    assert len(memberships_for_b) == 2


# --- Explicit input/output ports -----------------------------------------------------------------


def test_explicit_input_output_ports():
    model = _user_defined_split()
    directions = {p.module_id: p.direction for p in model.module_ports}
    assert directions["modA"] is ModulePortDirection.OUTPUT
    assert directions["modB"] is ModulePortDirection.INPUT


def test_ports_never_duplicate_the_referenced_species():
    model = _user_defined_split()
    assert len({s.species_id for s in model.full_network.species}) == 3
    assert all(p.species_id == "B" for p in model.module_ports)


# --- Cross-module connection derivation -----------------------------------------------------------


def test_cross_module_connection_is_derived_from_matching_ports():
    model = _user_defined_split()
    connections = derive_cross_module_connections(model.modularizations[0], model.module_ports)
    assert len(connections) == 1
    connection = connections[0]
    assert connection.species_id == "B"
    assert connection.upstream_module_id == "modA"
    assert connection.downstream_module_id == "modB"


def test_cross_module_connection_derivation_is_never_stored():
    """Connections are always recomputed, never a field on ModelSpecification itself."""
    assert not hasattr(ModelSpecification, "module_connections")


def test_bidirectional_ports_on_the_same_species_produce_connections_both_ways():
    modularization = ModelModularization(
        modularization_id="mod2",
        name="bidirectional",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modX", "modY"),
    )
    ports = (
        ModulePort(
            port_id="px",
            modularization_id="mod2",
            module_id="modX",
            species_id="shared",
            direction=ModulePortDirection.INPUT_OUTPUT,
        ),
        ModulePort(
            port_id="py",
            modularization_id="mod2",
            module_id="modY",
            species_id="shared",
            direction=ModulePortDirection.INPUT_OUTPUT,
        ),
    )
    connections = derive_cross_module_connections(modularization, ports)
    assert len(connections) == 2
    directions = {(c.upstream_module_id, c.downstream_module_id) for c in connections}
    assert directions == {("modX", "modY"), ("modY", "modX")}


def test_no_connection_derived_within_the_same_module():
    modularization = ModelModularization(
        modularization_id="mod3",
        name="single",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modOnly",),
    )
    ports = (
        ModulePort(
            port_id="p1",
            modularization_id="mod3",
            module_id="modOnly",
            species_id="X",
            direction=ModulePortDirection.OUTPUT,
        ),
        ModulePort(
            port_id="p2",
            modularization_id="mod3",
            module_id="modOnly",
            species_id="X",
            direction=ModulePortDirection.INPUT,
        ),
    )
    assert derive_cross_module_connections(modularization, ports) == ()


def test_connection_derivation_ignores_ports_from_other_modularizations():
    model = _user_defined_split()
    unrelated_port = ModulePort(
        port_id="unrelated",
        modularization_id="some-other-modularization",
        module_id="modZ",
        species_id="B",
        direction=ModulePortDirection.INPUT,
    )
    connections = derive_cross_module_connections(
        model.modularizations[0], (*model.module_ports, unrelated_port)
    )
    assert len(connections) == 1


# --- Multiple alternative modularizations on the same canonical model ---------------------------


def test_multiple_alternative_modularizations_coexist():
    network = _linear_network()
    user_defined = ModelModularization(
        modularization_id="mod_user",
        name="user split",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("u_modA", "u_modB"),
    )
    topological = ModelModularization(
        modularization_id="mod_topo",
        name="topological split",
        method=ModularizationMethod.TOPOLOGICAL,
        module_ids=("t_modA", "t_modB"),
        description="placeholder for a future topology-driven algorithm",
    )
    model = _model(
        full_network=network,
        modularizations=(user_defined, topological),
        model_modules=(
            ModelModule(module_id="u_modA", name="U-A"),
            ModelModule(module_id="u_modB", name="U-B"),
            ModelModule(module_id="t_modA", name="T-A"),
            ModelModule(module_id="t_modB", name="T-B"),
        ),
        module_memberships=(
            ModuleMembership(
                membership_id="u_mem_r1",
                modularization_id="mod_user",
                module_id="u_modA",
                component_type=ModuleComponentType.REACTION,
                component_id="r1",
            ),
            ModuleMembership(
                membership_id="t_mem_r1",
                modularization_id="mod_topo",
                module_id="t_modA",
                component_type=ModuleComponentType.REACTION,
                component_id="r1",
            ),
        ),
    )
    assert len(model.modularizations) == 2
    assert {m.method for m in model.modularizations} == {
        ModularizationMethod.USER_DEFINED,
        ModularizationMethod.TOPOLOGICAL,
    }
    # r1 belongs to one module in EACH modularization -- never deduplicated against each other.
    r1_memberships = [m for m in model.module_memberships if m.component_id == "r1"]
    assert {m.modularization_id for m in r1_memberships} == {"mod_user", "mod_topo"}


def test_no_modularization_is_assumed_more_correct_than_another():
    """Nothing on ModelModularization itself ranks one above another -- no "is_primary" or
    similar field exists."""
    fields = set(ModelModularization.__dataclass_fields__)
    assert "is_primary" not in fields
    assert "rank" not in fields
    assert "is_canonical" not in fields


# --- Invalid references rejected -----------------------------------------------------------------


def test_membership_naming_unknown_modularization_is_rejected():
    with pytest.raises(ValueError, match="modularization_id"):
        _model(
            model_modules=(ModelModule(module_id="modA", name="Module A"),),
            module_memberships=(
                ModuleMembership(
                    membership_id="mem1",
                    modularization_id="DOES_NOT_EXIST",
                    module_id="modA",
                    component_type=ModuleComponentType.REACTION,
                    component_id="r1",
                ),
            ),
        )


def test_membership_naming_unknown_module_is_rejected():
    with pytest.raises(ValueError, match="module_id"):
        _model(
            modularizations=(
                ModelModularization(
                    modularization_id="mod1",
                    name="split",
                    method=ModularizationMethod.USER_DEFINED,
                    module_ids=(),
                ),
            ),
            module_memberships=(
                ModuleMembership(
                    membership_id="mem1",
                    modularization_id="mod1",
                    module_id="DOES_NOT_EXIST",
                    component_type=ModuleComponentType.REACTION,
                    component_id="r1",
                ),
            ),
        )


def test_membership_naming_unknown_component_is_rejected():
    with pytest.raises(ValueError, match="component_id"):
        _model(
            modularizations=(
                ModelModularization(
                    modularization_id="mod1",
                    name="split",
                    method=ModularizationMethod.USER_DEFINED,
                    module_ids=("modA",),
                ),
            ),
            model_modules=(ModelModule(module_id="modA", name="Module A"),),
            module_memberships=(
                ModuleMembership(
                    membership_id="mem1",
                    modularization_id="mod1",
                    module_id="modA",
                    component_type=ModuleComponentType.REACTION,
                    component_id="DOES_NOT_EXIST",
                ),
            ),
        )


def test_module_not_a_member_of_its_claimed_modularization_is_rejected():
    """A module that exists, and a modularization that exists, but the module is not actually
    named in that modularization's own module_ids -- a consistency violation, not a bare
    missing-id error."""
    with pytest.raises(ValueError, match="not a member of"):
        _model(
            modularizations=(
                ModelModularization(
                    modularization_id="mod1",
                    name="split",
                    method=ModularizationMethod.USER_DEFINED,
                    module_ids=("modA",),
                ),
            ),
            model_modules=(
                ModelModule(module_id="modA", name="Module A"),
                ModelModule(module_id="modB", name="Module B"),
            ),
            module_memberships=(
                ModuleMembership(
                    membership_id="mem1",
                    modularization_id="mod1",
                    module_id="modB",  # exists, but not in mod1.module_ids
                    component_type=ModuleComponentType.REACTION,
                    component_id="r1",
                ),
            ),
        )


def test_port_naming_unknown_species_is_rejected():
    with pytest.raises(ValueError, match="species_id"):
        _model(
            modularizations=(
                ModelModularization(
                    modularization_id="mod1",
                    name="split",
                    method=ModularizationMethod.USER_DEFINED,
                    module_ids=("modA",),
                ),
            ),
            model_modules=(ModelModule(module_id="modA", name="Module A"),),
            module_ports=(
                ModulePort(
                    port_id="p1",
                    modularization_id="mod1",
                    module_id="modA",
                    species_id="DOES_NOT_EXIST",
                    direction=ModulePortDirection.OUTPUT,
                ),
            ),
        )


def test_modularization_naming_unknown_module_id_is_rejected():
    with pytest.raises(ValueError, match="module_ids"):
        _model(
            modularizations=(
                ModelModularization(
                    modularization_id="mod1",
                    name="split",
                    method=ModularizationMethod.USER_DEFINED,
                    module_ids=("DOES_NOT_EXIST",),
                ),
            )
        )


def test_duplicate_modularization_id_is_rejected():
    duplicate = ModelModularization(
        modularization_id="dup", name="a", method=ModularizationMethod.USER_DEFINED
    )
    with pytest.raises(ValueError, match="modularization_id"):
        _model(modularizations=(duplicate, replace(duplicate, name="b")))


# --- No duplication of canonical species/reactions -----------------------------------------------


def test_no_duplication_of_canonical_species_or_reactions():
    model = _user_defined_split()
    assert len(model.full_network.species) == 3
    assert len(model.full_network.reactions) == 2
    # Adding module structure never grows the canonical registries.
    unmodularized = _model()
    assert model.full_network.species == unmodularized.full_network.species
    assert model.full_network.reactions == unmodularized.full_network.reactions


# --- Antimony semantic round-trip unchanged -------------------------------------------------------


def test_antimony_round_trip_is_unaffected_by_modularization_metadata():
    """Module metadata never alters executable semantics -- the generated Antimony text for a
    modularized model is byte-identical to the unmodularized one."""
    plain = generate_antimony(_model()).full_antimony.antimony_text
    modularized = generate_antimony(_user_defined_split()).full_antimony.antimony_text
    assert plain == modularized


def test_imported_model_can_carry_a_modularization_without_affecting_import_export():
    text = """
    model m
      compartment c = 1.0;
      species A in c = 10.0;
      species B in c = 0.0;
      R1: A => B; k1 * A;
      k1 = 0.5;
    end
    """
    imported = import_antimony(text)
    with_modularization = replace(
        imported,
        modularizations=(
            ModelModularization(
                modularization_id="mod1",
                name="imported split",
                method=ModularizationMethod.IMPORTED,
            ),
        ),
    )
    before = generate_antimony(imported).full_antimony.antimony_text
    after = generate_antimony(with_modularization).full_antimony.antimony_text
    assert before == after


# --- Downstream handoff unchanged -----------------------------------------------------------------


def test_downstream_handoff_is_unchanged_by_modularization_metadata():
    model = _user_defined_split()
    package = generate_antimony(model)
    handoff = build_canonical_downstream_handoff(model, package)

    plain_model = _model()
    plain_package = generate_antimony(plain_model)
    plain_handoff = build_canonical_downstream_handoff(plain_model, plain_package)

    assert set(handoff.keys()) == set(plain_handoff.keys())
    assert handoff["reactions"] == plain_handoff["reactions"]
    assert handoff["species"] == plain_handoff["species"]
